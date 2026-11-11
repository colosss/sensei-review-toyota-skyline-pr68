#!/usr/bin/env python3
"""Local review packets and execution receipts. No model API or GitHub writes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation preserves existing work and receipts.
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def scope(root):
    return read(root / 'REVIEW_SCOPE.json')


def pinned(root):
    return scope(root)['pinned_commits']['source']


def packet(root, ident):
    if not re.fullmatch(r'[A-Z][A-Z0-9]*[0-9]+', ident):
        raise ValueError('Invalid task ID')
    return root / 'scratch/pipeline' / ident


def local(root, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError('Artifact paths must be relative to review root')
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Artifact escapes review root')
    return path


def artifact(root, relative):
    path = local(root, relative)
    if path.is_relative_to((root / 'source').resolve()):
        raise ValueError('Review artifacts must be outside source/')
    if not path.is_file():
        raise ValueError(f'Missing artifact: {relative}')
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def baseline(root):
    subprocess.run([sys.executable, str(root / 'scripts/verify_baseline.py')],
                   cwd=root, check=True)


def initialize(root, ident):
    task = next((t for t in read(root / 'pipeline/tasks.json') if t['id'] == ident), None)
    if task is None:
        raise ValueError('Unknown ID; coordinator must first add a scoped task to pipeline/tasks.json')
    base = packet(root, ident)
    common = {'task_id': ident, 'sha': pinned(root), 'actor': '', 'status': 'blocked'}
    discovery = dict(common, title='', requirement={'source': '', 'basis': ''},
                     source_locations=[], expected='', actual='', impact='',
                     pr_relation={'classification': 'unknown', 'evidence': ''},
                     reproduction={'kind': 'regression', 'instructions': '',
                                   'receipt': '', 'artifacts': []}, limitations='')
    verification = dict(common, receipt='', artifacts=[], requirement_check='',
                        failure_reason_check='', base_check='', objection='',
                        objection_result='', independence='')
    decision = {'task_id': ident, 'status': 'blocked', 'coordinator': '',
                'reason': '', 'duplicate_of': '', 'evidence_reviewed': False,
                'sanitized': False, 'deduplicated': False}
    for name, value in [('task.json', task), ('discovery.json', discovery),
                        ('verification.json', verification), ('decision.json', decision)]:
        path = base / name
        if not path.exists():
            write(path, value)
    return base


def prompt(root, ident, role):
    base = packet(root, ident)
    task = read(base / 'task.json')
    return ((root / f'pipeline/prompts/{role}.md').read_text() + '\n\n'
            + json.dumps(task, ensure_ascii=False, indent=2)
            + f'\nSHA: {pinned(root)}\n'
            + f'Packet: {base.relative_to(root)}\n'
            + f'Writable artifacts: repro/{ident}/, evidence/{ident}/\n'
            + 'Координатор до запуска назначает actor ID, fixture и runtime; '
              'без назначения общего хранилища мутации не выполняй.\n')


def record(root, ident, actor, command, timeout, artifacts):
    if not actor.strip() or not command or not 0 < timeout <= 900:
        raise ValueError('Actor, command and timeout in (0, 900] required')
    base = packet(root, ident)
    if not (base / 'task.json').exists():
        raise ValueError('Initialize packet first')
    inputs = {a: digest(artifact(root, a)) for a in artifacts}
    baseline(root)
    ident_run = uuid.uuid4().hex
    receipts = base / 'runs'
    receipts.mkdir(exist_ok=True)
    log = receipts / f'{ident_run}.log'
    started = datetime.now(timezone.utc).isoformat()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    timed_out = False
    # argv only; this is an execution recorder, NOT a command sandbox.
    with log.open('xb') as output:
        proc = subprocess.Popen(command, cwd=root, env=env, stdout=output,
                                stderr=subprocess.STDOUT, start_new_session=True)
        try:
            exit_code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            exit_code = 124
    clean = True
    try:
        baseline(root)
    except subprocess.CalledProcessError:
        clean = False
    receipt = {'task_id': ident, 'actor': actor, 'sha': pinned(root),
               'started_utc': started, 'finished_utc': datetime.now(timezone.utc).isoformat(),
               'command': command, 'cwd': '.', 'exit_code': exit_code,
               'timed_out': timed_out, 'baseline_clean_after': clean,
               'inputs': inputs, 'log': str(log.relative_to(root)), 'log_sha256': digest(log)}
    path = receipts / f'{ident_run}.json'
    write(path, receipt)
    print(f'Receipt: {path.relative_to(root)}; target exit={exit_code}; '
          f'timeout={timed_out}; this is not a defect verdict')
    return exit_code if clean and 0 <= exit_code <= 125 else 1


def meaningful(value):
    return (isinstance(value, str) and bool(value.strip())
            and not re.search(r'\b(TODO|TBD|REPLACE)\b|^\.\.\.$|^<.*>$', value, re.I))


def validate(root, ident):
    """Structural gates + explicit reviewer attestations; no semantic proof."""
    base = packet(root, ident)
    d, v, c = [read(base / name) for name in
               ['discovery.json', 'verification.json', 'decision.json']]
    errors = []

    def need(condition, message):
        if not condition:
            errors.append(message)

    for name, doc in [('discovery', d), ('verification', v)]:
        need(doc.get('task_id') == ident and doc.get('sha') == pinned(root), f'{name}: task/SHA mismatch')
        need(meaningful(doc.get('actor')), f'{name}: actor missing')
    need(d.get('status') == 'reproduced', 'Discovery must be reproduced')
    need(v.get('status') == 'confirmed', 'Independent verification must be confirmed')
    need(d.get('actor') != v.get('actor'), 'Verifier must have a different actor ID')
    for key in ['title', 'expected', 'actual', 'impact', 'limitations']:
        need(meaningful(d.get(key)), f'Discovery missing {key}')
    for key in ['source', 'basis']:
        need(meaningful(d.get('requirement', {}).get(key)), f'Requirement missing {key}')
    relation = d.get('pr_relation', {})
    need(relation.get('classification') == 'introduced', 'Not established as introduced by PR')
    need(meaningful(relation.get('evidence')), 'Base comparison evidence missing')
    locations = d.get('source_locations')
    need(isinstance(locations, list) and bool(locations), 'Source locations missing')
    for loc in locations if isinstance(locations, list) else []:
        try:
            path = local(root, loc['file'])
            count = len(path.read_text().splitlines())
            need(path.is_relative_to((root / 'source').resolve()), 'Source location outside source/')
            need(type(loc['line']) is int and 1 <= loc['line'] <= count, 'Invalid source line')
        except (ValueError, OSError, KeyError, TypeError):
            errors.append('Invalid source location')
    repro = d.get('reproduction', {})
    need(meaningful(repro.get('instructions')), 'Reproduction instructions missing')
    kind = repro.get('kind')
    need(kind in ['regression', 'scenario'], 'Unknown reproduction kind')
    for key in ['requirement_check', 'failure_reason_check', 'base_check',
                'objection', 'objection_result', 'independence']:
        need(meaningful(v.get(key)), f'Verification missing {key}')
    for stage, doc, actor in [('discovery', repro, d.get('actor')), ('verification', v, v.get('actor'))]:
        artifacts = doc.get('artifacts')
        need(isinstance(artifacts, list) and bool(artifacts), f'{stage}: evidence artifacts missing')
        for a in artifacts if isinstance(artifacts, list) else []:
            try:
                artifact(root, a)
            except (ValueError, TypeError):
                errors.append(f'{stage}: invalid artifact')
        receipt_name = doc.get('receipt')
        if receipt_name:
            try:
                path = artifact(root, receipt_name)
                need(path.is_relative_to((base / 'runs').resolve()), f'{stage}: receipt outside packet')
                r = read(path)
                need(r['task_id'] == ident and r['sha'] == pinned(root) and r['actor'] == actor,
                     f'{stage}: receipt identity mismatch')
                need(not r['timed_out'] and r['baseline_clean_after'], f'{stage}: timeout or dirty baseline')
                expected_exit = 1 if kind == 'regression' else 0
                need(type(r['exit_code']) is int and r['exit_code'] == expected_exit,
                     f'{stage}: expected exit {expected_exit}, got {r["exit_code"]}')
                need(digest(artifact(root, r['log'])) == r['log_sha256'], f'{stage}: log changed')
                need(bool(r.get('inputs')), f'{stage}: no hashed reproduction inputs')
                for a, checksum in r.get('inputs', {}).items():
                    need(digest(artifact(root, a)) == checksum, f'{stage}: reproduction input changed')
            except (ValueError, KeyError, TypeError, OSError):
                errors.append(f'{stage}: invalid receipt')
        else:
            need(kind == 'scenario', f'{stage}: regression requires execution receipt')
            # Manual browser scenarios are attestations, never machine-verified executions.
            if kind == 'scenario':
                need(doc.get('manual_observation') is True and meaningful(doc.get('observed_steps')),
                     f'{stage}: manual scenario requires observed_steps and manual_observation=true')
    need(c.get('task_id') == ident and c.get('status') == 'accepted', 'Coordinator has not accepted')
    need(meaningful(c.get('coordinator')) and meaningful(c.get('reason')), 'Coordinator/reason missing')
    for key in ['evidence_reviewed', 'sanitized', 'deduplicated']:
        need(c.get(key) is True, f'Coordinator must attest {key}')
    review = base / 'REVIEW.md'
    need(review.is_file() and bool(review.read_text().strip()), 'Self-contained REVIEW.md missing')
    return errors


def bundle(root):
    if scope(root).get('organizer_freeze_verified') is not True:
        raise ValueError('Official freeze not verified in REVIEW_SCOPE.json; research can continue, final bundle blocked')
    ready = []
    for path in sorted((root / 'scratch/pipeline').glob('*/decision.json')):
        if read(path).get('status') != 'accepted':
            continue
        ident = path.parent.name
        errors = validate(root, ident)
        if errors:
            raise ValueError(f'{ident}: ' + '; '.join(errors))
        ready.append(f'## {ident}\n\n' + (path.parent / 'REVIEW.md').read_text())
    if not ready:
        raise ValueError('No accepted findings; no empty success report generated')
    output = root / 'scratch/pipeline' / f'REVIEW-{uuid.uuid4().hex[:8]}.md'
    output.write_text('# Локальный черновик GitHub Review PR #68\n\n' + '\n\n'.join(ready))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='action', required=True)
    subs.add_parser('preflight')
    subs.add_parser('status')
    subs.add_parser('bundle')
    for name in ['init', 'prompt', 'run', 'check']:
        sub = subs.add_parser(name)
        sub.add_argument('id')
        if name == 'prompt':
            sub.add_argument('--role', choices=['discover', 'verify'], default='discover')
        if name == 'run':
            sub.add_argument('--actor', required=True)
            sub.add_argument('--timeout', type=float, default=120)
            sub.add_argument('--artifact', action='append', default=[])
    arguments = sys.argv[1:]
    command = []
    if arguments[:1] == ['run'] and '--' in arguments:
        split = arguments.index('--')
        command, arguments = arguments[split + 1:], arguments[:split]
    args = parser.parse_args(arguments)
    try:
        if args.action == 'preflight':
            baseline(ROOT)
            print('Official freeze verified:', scope(ROOT).get('organizer_freeze_verified') is True)
            print('No model/provider/browser readiness claimed; see PIPELINE.md stage 0.')
        elif args.action == 'status':
            for task in sorted(read(ROOT / 'pipeline/tasks.json'), key=lambda t: (t['wave'], t['id'])):
                path = packet(ROOT, task['id']) / 'decision.json'
                state = read(path).get('status', 'blocked') if path.exists() else 'not-started'
                print(f'{task["id"]:4} wave={task["wave"]} {task["area"]:12} {state}')
        elif args.action == 'init':
            baseline(ROOT)
            print(initialize(ROOT, args.id).relative_to(ROOT))
        elif args.action == 'prompt':
            print(prompt(ROOT, args.id, args.role))
        elif args.action == 'run':
            return record(ROOT, args.id, args.actor, command, args.timeout, args.artifact)
        elif args.action == 'check':
            baseline(ROOT)
            errors = validate(ROOT, args.id)
            print('\n'.join(errors) if errors else 'Packet complete. Semantic acceptance is a reviewer attestation, not automatic proof.')
            return int(bool(errors))
        elif args.action == 'bundle':
            baseline(ROOT)
            print(bundle(ROOT).relative_to(ROOT))
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(f'Pipeline stopped: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
