"""Tests of review tooling only. Synthetic failures are NOT application findings."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/review_pipeline.py'
spec = importlib.util.spec_from_file_location('review_pipeline', SCRIPT)
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.save('REVIEW_SCOPE.json', {'pinned_commits': {'source': 'a' * 40},
                                       'organizer_freeze_verified': True})
        self.save('pipeline/tasks.json', [{'id': 'C02', 'goal': 'synthetic tooling fixture'}])
        (self.root / 'source').mkdir()
        (self.root / 'source/main.py').write_text('pass\n')
        self.base = pipeline.initialize(self.root, 'C02')
        self.input = self.root / 'repro/C02/fixture.py'
        self.input.parent.mkdir(parents=True)
        self.input.write_text('# Synthetic tooling fixture, not a PR defect\n')
        self.evidence = self.root / 'evidence/C02/observed.md'
        self.evidence.parent.mkdir(parents=True)
        self.evidence.write_text('Synthetic test of pipeline validation only.\n')

    def save(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def run_receipt(self, actor, code='raise SystemExit(1)', timeout=3):
        with patch.object(pipeline, 'baseline'):
            pipeline.record(self.root, 'C02', actor, [sys.executable, '-c', code],
                            timeout, ['repro/C02/fixture.py'])
        files = list((self.base / 'runs').glob('*.json'))
        return str(max(files, key=lambda p: p.stat().st_mtime_ns).relative_to(self.root))

    def complete(self, manual=False):
        d = pipeline.read(self.base / 'discovery.json')
        d.update(actor='worker-A', status='reproduced', title='Synthetic pipeline test',
                 requirement={'source': 'fixture contract', 'basis': 'fixture expectation'},
                 source_locations=[{'file': 'source/main.py', 'line': 1}],
                 expected='synthetic expected', actual='synthetic actual', impact='fixture only',
                 pr_relation={'classification': 'introduced', 'evidence': 'synthetic comparison'},
                 limitations='No application behavior tested')
        d['reproduction'].update(instructions='Run synthetic fixture', artifacts=['evidence/C02/observed.md'])
        v = pipeline.read(self.base / 'verification.json')
        v.update(actor='worker-B', status='confirmed', artifacts=['evidence/C02/observed.md'])
        for key in ['requirement_check', 'failure_reason_check', 'base_check', 'objection',
                    'objection_result', 'independence']:
            v[key] = 'Synthetic reviewer attestation'
        if manual:
            d['reproduction'].update(kind='scenario', manual_observation=True, observed_steps='synthetic steps A')
            v.update(manual_observation=True, observed_steps='synthetic steps B')
        else:
            d['reproduction']['receipt'] = self.run_receipt('worker-A')
            v['receipt'] = self.run_receipt('worker-B')
        c = {'task_id': 'C02', 'status': 'accepted', 'coordinator': 'coordinator',
             'reason': 'Synthetic tooling test', 'evidence_reviewed': True,
             'sanitized': True, 'deduplicated': True}
        for name, doc in [('discovery', d), ('verification', v), ('decision', c)]:
            self.save(f'scratch/pipeline/C02/{name}.json', doc)
        (self.base / 'REVIEW.md').write_text('Synthetic fixture, never a submitted PR finding.\n')
        return d, v, c

    def test_blank_packet_is_rejected(self):
        self.assertTrue(pipeline.validate(self.root, 'C02'))

    def test_init_preserves_existing_work(self):
        path = self.base / 'discovery.json'
        path.write_text('{"note": "user work"}')
        pipeline.initialize(self.root, 'C02')
        self.assertEqual(pipeline.read(path)['note'], 'user work')

    def test_valid_regression_receipts_and_bundle(self):
        self.complete()
        self.assertEqual(pipeline.validate(self.root, 'C02'), [])
        self.assertIn('Synthetic fixture', pipeline.bundle(self.root).read_text())

    def test_manual_scenario_is_supported_as_attestation(self):
        self.complete(manual=True)
        self.assertEqual(pipeline.validate(self.root, 'C02'), [])

    def test_manual_scenario_without_observations_rejected(self):
        d, _, _ = self.complete(manual=True)
        del d['reproduction']['observed_steps']
        self.save('scratch/pipeline/C02/discovery.json', d)
        self.assertTrue(any('observed_steps' in e for e in pipeline.validate(self.root, 'C02')))

    def test_same_actor_rejected(self):
        _, v, _ = self.complete(manual=True)
        v['actor'] = 'worker-A'
        self.save('scratch/pipeline/C02/verification.json', v)
        self.assertTrue(any('different actor' in e for e in pipeline.validate(self.root, 'C02')))

    def test_successful_bug_presence_test_is_not_failed_regression(self):
        d, _, _ = self.complete()
        d['reproduction']['receipt'] = self.run_receipt('worker-A', 'print("bug present")')
        self.save('scratch/pipeline/C02/discovery.json', d)
        self.assertTrue(any('expected exit 1' in e for e in pipeline.validate(self.root, 'C02')))

    def test_collection_error_not_regression_failure(self):
        d, _, _ = self.complete()
        d['reproduction']['receipt'] = self.run_receipt('worker-A', 'raise SystemExit(2)')
        self.save('scratch/pipeline/C02/discovery.json', d)
        self.assertTrue(any('expected exit 1' in e for e in pipeline.validate(self.root, 'C02')))

    def test_changed_reproduction_input_invalidates_receipts(self):
        self.complete()
        self.input.write_text('changed\n')
        self.assertTrue(any('input changed' in e for e in pipeline.validate(self.root, 'C02')))

    def test_changed_output_log_invalidates_receipt(self):
        d, _, _ = self.complete()
        receipt = pipeline.read(self.root / d['reproduction']['receipt'])
        (self.root / receipt['log']).write_text('replacement output')
        self.assertTrue(any('log changed' in e for e in pipeline.validate(self.root, 'C02')))

    def test_timeout_is_recorded(self):
        name = self.run_receipt('worker-A', 'import time; time.sleep(10)', timeout=0.05)
        receipt = pipeline.read(self.root / name)
        self.assertTrue(receipt['timed_out'])
        self.assertEqual(receipt['exit_code'], 124)

    def test_inherited_issue_not_accepted(self):
        d, _, _ = self.complete(manual=True)
        d['pr_relation']['classification'] = 'inherited'
        self.save('scratch/pipeline/C02/discovery.json', d)
        self.assertTrue(any('introduced' in e for e in pipeline.validate(self.root, 'C02')))

    def test_artifact_escape_and_source_output_rejected(self):
        for name in ['../outside', '/tmp/outside', 'source/main.py']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                pipeline.artifact(self.root, name)

    def test_freeze_blocks_final_bundle(self):
        self.complete(manual=True)
        s = pipeline.scope(self.root)
        s['organizer_freeze_verified'] = False
        self.save('REVIEW_SCOPE.json', s)
        with self.assertRaisesRegex(ValueError, 'freeze'):
            pipeline.bundle(self.root)

    def test_no_empty_success_report(self):
        with self.assertRaisesRegex(ValueError, 'No accepted'):
            pipeline.bundle(self.root)


if __name__ == '__main__':
    unittest.main()
