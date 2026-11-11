#!/usr/bin/env python3
"""Bounded DeepSeek tool smoke; credentials stay in the local Secret Service."""
import json
from pathlib import Path
import secrets
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = 'https://ru.cheapvibecode.ru/v1'
MODEL = 'deepseek-v4.1-flash-1017'


def main():
    import secretstorage
    connection = secretstorage.dbus_init()
    collection = secretstorage.get_default_collection(connection)
    if collection.is_locked():
        raise RuntimeError('Secret Service is locked; unlock it locally')
    matches = list(collection.search_items({'url': BASE_URL, 'username': 'Bearer'}))
    if len(matches) != 1:
        raise RuntimeError('Expected one existing Zed CheapVibeCode credential')
    key = matches[0].get_secret().decode()
    folder = ROOT / 'scratch/setup-smoke'
    folder.mkdir(parents=True, exist_ok=True)
    nonce = secrets.token_hex(8)
    fixture = {'nonce': nonce, 'values': [13, 29]}
    (folder / 'fixture.json').write_text(json.dumps(fixture))
    tools = [
        {'type': 'function', 'function': {'name': 'read_fixture', 'description': 'Read the local synthetic fixture.',
         'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}},
        {'type': 'function', 'function': {'name': 'run_check', 'description': 'Run a local Python assertion for the sum.',
         'parameters': {'type': 'object', 'properties': {'total': {'type': 'integer'}}, 'required': ['total'], 'additionalProperties': False}}},
        {'type': 'function', 'function': {'name': 'write_result', 'description': 'Save the nonce and checked sum to the local result file.',
         'parameters': {'type': 'object', 'properties': {'nonce': {'type': 'string'}, 'total': {'type': 'integer'}},
                        'required': ['nonce', 'total'], 'additionalProperties': False}}},
    ]
    messages = [{'role': 'system', 'content': 'This is a bounded tool smoke, not a code review. Use tools in order: read_fixture, run_check, write_result. Do not guess fixture data. Keep responses short.'},
                {'role': 'user', 'content': 'Read the synthetic local fixture, calculate the sum of values, run_check with the sum, then save its nonce and sum through write_result.'}]
    events = []
    checked = False
    written = False
    for turn in range(4):
        payload = {'model': MODEL, 'messages': messages, 'tools': tools,
                   'tool_choice': 'auto', 'max_tokens': 2048, 'reasoning_effort': 'medium', 'stream': False}
        request = urllib.request.Request(BASE_URL + '/chat/completions',
                    data=json.dumps(payload).encode(),
                    headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f'Provider HTTP {error.code}; response body intentionally withheld') from None
        message = data['choices'][0]['message']
        calls = message.get('tool_calls', [])
        events.append({'turn': turn + 1, 'model': data.get('model'),
                       'tools': [c['function']['name'] for c in calls],
                       'usage': data.get('usage', {}), 'finish_reason': data['choices'][0].get('finish_reason')})
        messages.append(message)
        for call in calls:
            name = call['function']['name']
            args = json.loads(call['function']['arguments'])
            if name == 'read_fixture':
                result = json.loads((folder / 'fixture.json').read_text())
            elif name == 'run_check':
                total = args.get('total')
                if type(total) is not int:
                    raise RuntimeError('Tool supplied a non-integer total')
                process = subprocess.run([sys.executable, '-c',
                         'import sys; assert int(sys.argv[1]) == 13 + 29; print("synthetic check passed")', str(total)],
                         cwd=ROOT, capture_output=True, text=True, timeout=10)
                checked = process.returncode == 0
                result = {'exit_code': process.returncode, 'stdout': process.stdout}
            elif name == 'write_result':
                if not checked or args != {'nonce': nonce, 'total': 42}:
                    raise RuntimeError('Worker result failed local validation')
                (folder / 'worker-result.json').write_text(json.dumps(args, indent=2))
                written = True
                result = {'saved': True}
            else:
                raise RuntimeError('Unexpected tool name')
            messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(result)})
        if written:
            summary = {'passed': True, 'requested_model': MODEL, 'api_calls': turn + 1,
                       'local_check_passed': checked, 'result_file': 'scratch/setup-smoke/worker-result.json',
                       'scope': 'direct API tool harness; NOT native Zed delegation', 'events': events}
            (folder / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
            print(json.dumps({k: v for k, v in summary.items() if k != 'events'}, ensure_ascii=False))
            return 0
        if not calls:
            raise RuntimeError('No tool calls received; smoke incomplete')
    raise RuntimeError('Four-call smoke limit reached without a validated result')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        # Never include request headers, credentials, or raw provider responses.
        print(f'Worker smoke failed: {type(error).__name__}: {error}', file=sys.stderr)
        raise SystemExit(1)
