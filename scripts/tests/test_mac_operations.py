import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('mac_ops', ROOT/'deploy/macos/medtrack_mac_ops.py')
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)


class OperationsBoundaryTests(unittest.TestCase):
    def ci_fixture(self):
        target='a'*40
        workflow={'id':123,'run_number':4,'run_attempt':1,'head_sha':target,'head_branch':'main',
                  'event':'push','path':'.github/workflows/ci.yml','repository':{'full_name':'nmpraveen/patient-registry'},
                  'status':'completed','conclusion':'success'}
        jobs=[{'id':i,'run_id':123,'head_sha':target,'name':name,'status':'completed','conclusion':'success',
               'labels':['ubuntu-latest']} for i,name in enumerate(ops.REQUIRED_CHECKS)]
        return target,{'total_count':1,'workflow_runs':[workflow]},{'total_count':len(jobs),'jobs':jobs}

    def test_ci_requires_exact_main_workflow_and_all_seven_jobs(self):
        target,runs,jobs=self.ci_fixture()
        with patch.object(ops,'github_json',side_effect=[runs,jobs]):
            self.assertEqual(set(ops.verify_ci(target)['checks']),ops.REQUIRED_CHECKS)
        for field,value in [('head_sha','b'*40),('conclusion','failure'),('status','queued'),('event','pull_request')]:
            target,runs,jobs=self.ci_fixture();runs['workflow_runs'][0][field]=value
            with patch.object(ops,'github_json',side_effect=[runs,jobs]),self.assertRaises(ValueError):ops.verify_ci(target)
        for modification in ('missing','failed','wrong_sha','self_hosted'):
            target,runs,jobs=self.ci_fixture()
            if modification=='missing':jobs['jobs'].pop()
            if modification=='failed':jobs['jobs'][0]['conclusion']='failure'
            if modification=='wrong_sha':jobs['jobs'][0]['head_sha']='b'*40
            if modification=='self_hosted':jobs['jobs'][0]['labels']=['self-hosted']
            with patch.object(ops,'github_json',side_effect=[runs,jobs]),self.assertRaises(ValueError):ops.verify_ci(target)

    def test_latest_failed_rerun_invalidates_previous_green_run(self):
        import copy
        target,runs,jobs=self.ci_fixture()
        newer=copy.deepcopy(runs['workflow_runs'][0]);newer.update(run_number=5,conclusion='failure')
        runs['workflow_runs'].append(newer)
        with patch.object(ops,'github_json',return_value=runs),self.assertRaisesRegex(ValueError,'main-ci-not-successful'):
            ops.verify_ci(target)

    def test_rejects_shell_and_arbitrary_image_inputs(self):
        with patch('sys.stderr', new=io.StringIO()):
            for argv in [['shell'],['status',';id'],['export-image','../web','abc']]:
                with self.assertRaises(SystemExit):
                    ops.parse(argv)
        with patch.object(os, 'geteuid', return_value=0), patch.object(ops,'clean_source'):
            with self.assertRaisesRegex(ValueError,'invalid-image-digest'):
                ops.main(['export-image','web','test;id'])

    def test_rejects_traversal_and_symlink_evidence(self):
        for value in ['../root','mac-../../etc','mac-x/y','other','mac-$(id)']:
            with self.assertRaisesRegex(ValueError,'invalid-evidence-id'):
                ops.evidence_dir(value)
        with tempfile.TemporaryDirectory() as d:
            link=Path(d)/'link'; link.symlink_to('/etc')
            with self.assertRaisesRegex(ValueError,'untrusted-operation-path'):
                ops.trusted(link)

    def test_rejects_unreviewed_source_and_modified_tree(self):
        with patch.object(ops,'trusted'), patch.object(ops,'git',return_value=' M scripts/restore.sh'):
            with self.assertRaisesRegex(ValueError,'modified-production-source'):
                ops.clean_source()
        with patch.object(ops,'clean_source'), patch.object(ops,'run',side_effect=ops.subprocess.CalledProcessError(1,['git'])):
            with self.assertRaises(ops.subprocess.CalledProcessError):
                ops.reviewed_target('a'*40)

    def test_mutation_requires_installed_release_proof(self):
        with patch.object(ops,'PROOFS',Path('/nonexistent/medtrack-proof')):
            with self.assertRaises(FileNotFoundError):ops.require_proof('a'*40)

    def test_exports_only_the_requested_current_production_image(self):
        digest='sha256:'+'1'*64
        with patch.object(os,'geteuid',return_value=0), patch.object(ops,'clean_source'), \
             patch.object(ops,'services',return_value={'web':{'image':digest}}), patch.object(ops,'run') as run:
            with self.assertRaisesRegex(ValueError,'production-image-changed'):
                ops.main(['export-image','web','sha256:'+'2'*64])
            run.assert_not_called()
            ops.main(['export-image','web',digest])
            run.assert_called_once_with(['docker','image','save',digest])

    def test_subprocess_environment_drops_caller_overrides(self):
        with patch.dict(os.environ,{'DOCKER_HOST':'tcp://malicious:2375','BASH_ENV':'/tmp/inject'}), \
             patch.object(ops.subprocess,'run') as run:
            ops.run(['docker','info'])
            env=run.call_args.kwargs['env']
            self.assertNotIn('DOCKER_HOST',env)
            self.assertNotIn('BASH_ENV',env)
            self.assertNotIn('shell',run.call_args.kwargs)


if __name__=='__main__':
    unittest.main()
