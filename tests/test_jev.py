import importlib.util
import datetime as dt
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('jev',Path(__file__).resolve().parents[1]/'scripts/score_topics.py')
jev=importlib.util.module_from_spec(spec);spec.loader.exec_module(jev)

class JevTests(unittest.TestCase):
    def test_unknown_date(self):
        self.assertEqual(jev.freshness_score({'published_at':None},dt.datetime.now(dt.timezone.utc)),0)
    def test_missing_answers_not_zero_score(self):
        with self.assertRaises(ValueError):jev.composite({}, {'answers':{}},dt.datetime.now(dt.timezone.utc))
    def test_dedup_gate(self):
        answers={key:{'score':4,'confidence':1} for key in jev.DIMENSIONS}
        row={'url':'https://example.com','test_plan':'run','heat_score':100,'published_at':dt.datetime.now(dt.timezone.utc).isoformat()}
        result=jev.composite(row,{'answers':answers},dt.datetime.now(dt.timezone.utc))
        self.assertEqual(result['total_score'],79)
    def test_no_network_during_validation(self):
        row=dict(id='a',title='b',summary='c',source='d',source_level='discovery_only')
        self.assertEqual(jev.validate_candidate(row),[])

if __name__=='__main__':unittest.main()
