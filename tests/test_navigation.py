import json
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT.parent/'Kenny---Automotive-self-driving-trash-can'))
from backend.navigation import models,simulate


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.environment=json.loads((ROOT/'fixtures/sample-room.json').read_text())
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        runs=Path(temp.name)
        for name,stage in [('server-mixed-v3-planner-finetune/seed_3/best.zip','mixed'),('smoke/final.zip','empty')]:
            p=runs/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fixture checkpoint')
            (p.parent/'config.json').write_text(json.dumps({'environment':{'stage':stage}}))
            (p.parent/'contract.json').write_text('{}')
        patcher=patch('backend.navigation.RUNS',runs);patcher.start();self.addCleanup(patcher.stop)
        python=patch.dict('os.environ',{'KENNY_SIM_PYTHON':sys.executable});python.start();self.addCleanup(python.stop)
    def test_model_inventory_contains_existing_runs(self):
        inventory=models();self.assertTrue(inventory)
        self.assertTrue(any(m['id']=='server-mixed-v3-planner-finetune/seed_3/best.zip' for m in inventory))
        self.assertTrue(all(not m['id'].startswith('/') and '..' not in m['id'] for m in inventory))
    def test_invalid_selection_and_limits(self):
        with self.assertRaisesRegex(ValueError,'checkpoint'):simulate({'environment':self.environment,'model':'../../anything.zip'})
        mid=models()[0]['id']
        with self.assertRaisesRegex(ValueError,'Steps'):simulate({'environment':self.environment,'model':mid,'steps':3001})
        with self.assertRaisesRegex(ValueError,'Seed'):simulate({'environment':self.environment,'model':mid,'seed':-1})
        with self.assertRaisesRegex(ValueError,'controller'):simulate({'environment':self.environment,'model':mid,'controller':'unsafe'})
    def test_worker_result_and_argument_safety(self):
        mid=models()[0]['id']
        def run(args,**kwargs):
            output=Path(args[args.index('--output')+1]);output.write_text(json.dumps({'frames':[],'info':{'event':'timeout'}}))
            self.assertIn('kenny_rl.replay',args);self.assertNotIn('shell',kwargs)
            self.assertEqual(args[args.index('--controller')+1],'marker-sweep')
            return type('Process',(),{'returncode':0})()
        with patch('backend.navigation.subprocess.run',side_effect=run):
            result=simulate({'environment':self.environment,'model':mid,'steps':5,'controller':'marker-sweep'})
        self.assertEqual(result['model'],mid);self.assertEqual(result['info']['event'],'timeout')

if __name__=='__main__':unittest.main()
