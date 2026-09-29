import unittest,sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from analyze_study import validate,summarize,expected_tasks,paired_effect

def fixture(pid='P001'):
    # Explicit synthetic fixture for software tests only; not a participant.
    rows=[]
    for task,condition,period,taskset in expected_tasks(pid):
        t=30 if condition=='enhanced' else 60
        rows.append(dict(taskId=task,condition=condition,period=period,set=taskset,outcome='success',elapsedSeconds=t,effectiveSeconds=t,actions=[]))
    return dict(schemaVersion=1,dataKind='practice',participant=pid,group=(int(pid[1:])-1)%4+1,limitSeconds=180,datasetAsOf='2026-09-29',datasetSha256='a'*64,complete=True,records=rows)
class AnalysisTests(unittest.TestCase):
    def test_no_human_data(self):self.assertEqual(summarize([])['status'],'no_data')
    def test_practice_not_observed(self):
        with self.assertRaises(ValueError):validate(fixture())
    def test_known_paired_difference(self):
        d=summarize([validate(fixture(),'practice'),validate(fixture('P002'),'practice')]);self.assertEqual(d['effects']['effective_seconds']['mean_difference'],-30);self.assertEqual(d['effects']['success_rate']['mean_difference'],0)
    def test_failure_penalty(self):
        d=fixture();d['records'][0].update(outcome='failure',elapsedSeconds=20,effectiveSeconds=180);validate(d,'practice');r=summarize([d]);self.assertAlmostEqual(r['participant_summaries'][0]['enhanced']['success_rate'],2/3);self.assertEqual(r['participant_summaries'][0]['enhanced']['effective_seconds'],80)
    def test_duplicate_participant(self):
        with self.assertRaises(ValueError):summarize([fixture(),fixture()])
    def test_mismatched_version(self):
        d=fixture('P002');d['datasetSha256']='b'*64
        with self.assertRaises(ValueError):summarize([fixture(),d])
    def test_partial_excluded(self):
        d=fixture();d['records']=d['records'][:2];d['complete']=False;validate(d,'practice');self.assertEqual(summarize([d])['excluded_incomplete'],['P001'])
    def test_nan_negative_inconsistent_rejected(self):
        for change in [lambda r:r.update(elapsedSeconds=float('nan')),lambda r:r.update(elapsedSeconds=-3),lambda r:r.update(effectiveSeconds=999),lambda r:r.update(taskId='Y3')]:
            d=fixture();change(d['records'][0])
            with self.assertRaises(ValueError):validate(d,'practice')
    def test_bootstrap_reproducible(self):self.assertEqual(paired_effect([1,2,4]),paired_effect([1,2,4]))
if __name__=='__main__':unittest.main(verbosity=2)
