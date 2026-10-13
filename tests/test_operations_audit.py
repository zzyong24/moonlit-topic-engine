import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('ops', Path(__file__).parents[1]/'scripts/operations_audit.py')
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='unfamiliar creator space ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root/'research/douyin/main'
        self.save(self.data/'_account.json', {'accountId': 'main'})
        self.save(self.data/'_index.json', {'accountId': 'main', 'works': [
            {'awemeId': '123', 'publishedAt': '2026-10-01T00:00:00Z', 'path': 'broken'}]})
        self.work = self.root/'works/2026/W-example'
        self.save(self.work/'work.json', {'id': 'W-example', 'status': 'published',
                                        'platformIds': {'douyin': ['123']}})
        self.sample = {'awemeId': '123', 'capturedAt': '2026-10-02T00:00:00Z',
                       'source': 'creator-center-work-list', 'metrics': {'views': 100, 'favorites': 0}}
        self.path = self.work/'distribution/douyin/main/123/metrics.json'
        self.save(self.path, {'awemeId': '123', 'history': [self.sample], 'latest': self.sample})

    def save(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def run_audit(self):
        return ops.audit(self.root, 'main', self.data, '2026-10-02T06:00:00+00:00')

    def test_real_zero_and_missing_are_distinct(self):
        row = self.run_audit()['publications'][0]
        self.assertEqual(row['favorites_per_view']['value'], 0)
        self.assertIsNone(row['shares_per_view'])
        self.assertIsNone(ops.rate({'views': 0, 'favorites': 1}, 'favorites'))

    def test_old_cumulative_does_not_create_missing_early_windows(self):
        self.sample['capturedAt'] = '2026-10-10T00:00:00Z'
        self.save(self.path, {'awemeId': '123', 'history': [self.sample]})
        report = ops.audit(self.root, 'main', self.data, '2026-10-11T00:00:00Z')
        self.assertEqual(report['window_coverage'], {'24': 0, '72': 0, '168': 0})

    def test_deduplicates_same_account_and_records_broken_link(self):
        self.save(self.data/'_unassigned/123/metrics.json', {'awemeId': '123', 'history': [self.sample]})
        report = self.run_audit()
        self.assertEqual(report['publication_count'], 1)
        self.assertEqual(report['publications'][0]['snapshot_count'], 1)
        self.assertEqual(report['gap_counts']['broken_index_path'], 1)
        self.assertEqual(report['window_coverage']['24'], 1)

    def test_foreign_account_root_is_rejected(self):
        self.save(self.data/'_account.json', {'accountId': 'other'})
        with self.assertRaises(ValueError):
            self.run_audit()

    def test_future_and_timezone_free_capture_are_excluded(self):
        self.sample['capturedAt'] = '2026-10-03T00:00:00Z'
        self.save(self.path, {'awemeId': '123', 'history': [self.sample]})
        self.assertIsNone(self.run_audit()['publications'][0]['latest'])
        with self.assertRaises(ValueError):
            ops.audit(self.root, 'main', self.data, '2026-10-02T00:00:00')

    def test_ambiguous_stable_id_is_not_arbitrarily_assigned(self):
        self.save(self.root/'works/2026/W-second/work.json', {'id': 'W-second',
            'status': 'draft', 'platformIds': {'douyin': ['123']}})
        self.assertIsNone(self.run_audit()['publications'][0]['work_id'])

    def test_conflicting_duplicate_snapshot_is_excluded(self):
        changed = {**self.sample, 'metrics': {'views': 200}}
        self.save(self.data/'_unassigned/123/metrics.json', {'awemeId': '123', 'history': [changed]})
        report = self.run_audit()
        self.assertIsNone(report['publications'][0]['latest'])
        self.assertIn('conflicting_snapshot', report['gap_counts'])

    def test_release_platform_id_maps_even_without_root_platform_ids(self):
        self.save(self.work/'work.json', {'id':'W-example', 'status':'producing'})
        self.save(self.work/'distribution/releases.json', {'workId':'W-example','records':[
            {'channel':'douyin', 'platformPostId':'123', 'status':'published'},
            {'channel':'bilibili', 'platformPostId':'999', 'status':'published'}]})
        self.path.unlink()
        self.save(self.data/'_unassigned/123/metrics.json', {'awemeId':'123','history':[self.sample]})
        # Remove the account-specific directory evidence, leaving only the release ID.
        self.path.parent.rmdir()
        row=self.run_audit()['publications'][0]
        self.assertEqual(row['work_id'], 'W-example')
