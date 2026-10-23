import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'deploy/macos'))
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'deploy/macos'/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
scheduler=load('scheduler');actions=load('actions')


class SchedulingIntegrity(unittest.TestCase):
    def test_drive_restore_rejects_traversal_and_tier_mismatch_before_io(self):
        for archive,tier in [('../../secret','canary'),('medtrack-prod-canary-20261023T120614Z.tar.age','daily'),(None,None)]:
            with patch.object(actions,'command') as run,self.assertRaises(ValueError):actions.drive_download(archive,tier)
            run.assert_not_called()

    def test_drive_triplet_binds_bytes_marker_and_checksum(self):
        import hashlib
        archive='medtrack-prod-pre-deployment-20261023T180000Z.tar.age'
        data=b'synthetic encrypted fixture';digest=hashlib.sha256(data).hexdigest()
        def download(args,**kwargs):
            target=Path(args[-1])
            if target.name.endswith('.complete'):
                target.write_text(f'archive={archive}\nsha256={digest}\ndrive_verified=1\nsource_commit='+('a'*40)+'\n')
            elif target.name.endswith('.sha256'):target.write_text(digest+'  '+archive+'\n')
            else:target.write_bytes(data)
        with tempfile.TemporaryDirectory() as folder,patch.object(actions,'ROOT',Path(folder)),patch.object(actions,'command',side_effect=download):
            receipt=actions.drive_download(archive,'pre-deployment')
            self.assertEqual(receipt['sha256'],digest)
            self.assertTrue(receipt['read_only'])

    def test_old_success_cannot_hide_a_newer_failure_or_interruption(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);now=int(time.time())
            success={'run_id':'old','outcome':'success','started_epoch':now-30,'completed_epoch':now-20}
            scheduler.atomic(root/'restore-success.json',success)
            for outcome in ('failed','running'):
                scheduler.atomic(root/'restore-attempt.json',{'run_id':'new','outcome':outcome,'started_epoch':now-5})
                self.assertFalse(scheduler.current(root,'restore',now)['healthy'])
            scheduler.atomic(root/'restore-attempt.json',success)
            self.assertTrue(scheduler.current(root,'restore',now)['healthy'])
            self.assertFalse(scheduler.current(root,'restore',now+9*86400)['healthy'])

    def test_preflight_failure_records_attempt_and_invokes_alert(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(scheduler,'notify',return_value={'accepted':True}) as alert:
                result=scheduler.run_job(root,{'path':'/usr/bin:/bin','commands':{}},'restore',True)
            self.assertEqual(result['outcome'],'failed');alert.assert_called_once()
            self.assertFalse(scheduler.current(root/'state','restore')['healthy'])
            self.assertEqual(scheduler.read(root/'state/restore-attempt.json')['alert']['accepted'],True)

    def test_real_child_failure_never_publishes_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            config={'path':'/usr/bin:/bin','commands':{'restore':['/usr/bin/false']}}
            with patch.object(scheduler,'notify',return_value={'accepted':True}):
                self.assertEqual(scheduler.run_job(root,config,'restore')['exit_code'],1)
            self.assertFalse((root/'state/restore-success.json').exists())

    def test_restore_contract_binds_success_and_rejects_later_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            config={'path':'/usr/bin:/bin','commands':{'restore':['/usr/bin/true']}}
            result=scheduler.run_job(root,config,'restore')
            state=root/'state'
            receipt=(state/'scratch-restore.receipt').read_bytes()
            attempt=dict(line.split('=',1) for line in (state/'scratch-restore.receipt.attempt').read_text().splitlines())
            self.assertEqual(attempt['receipt_sha256'],__import__('hashlib').sha256(receipt).hexdigest())
            self.assertEqual(attempt['attempt_id'],result['contract_id'])
            sys.path.insert(0,str(ROOT/'scripts'))
            from verify_scratch_attempt import verify
            verify(str(state/'scratch-restore.receipt.attempt'),str(state/'scratch-restore.receipt'),int(time.time()))
            config['commands']['restore']=['/usr/bin/false']
            with patch.object(scheduler,'notify',return_value={'accepted':True}):
                scheduler.run_job(root,config,'restore')
            self.assertIn('status=failure',(state/'scratch-restore.receipt.attempt').read_text())
            self.assertEqual(receipt,(state/'scratch-restore.receipt').read_bytes())
            self.assertFalse(scheduler.current(state,'restore')['healthy'])
            with self.assertRaises(ValueError):
                verify(str(state/'scratch-restore.receipt.attempt'),str(state/'scratch-restore.receipt'),int(time.time()))

    def test_timeout_terminates_child_and_marks_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            config={'path':'/usr/bin:/bin','commands':{'health':['/bin/sleep','30']},'timeout_seconds':0.1}
            with patch.object(scheduler,'notify',return_value={'accepted':True}):
                result=scheduler.run_job(root,config,'health')
            self.assertEqual(result['exit_code'],124)
            self.assertFalse(scheduler.current(root/'state','health')['healthy'])

    def test_action_timeout_kills_orphan_holding_inherited_pipes(self):
        with tempfile.TemporaryDirectory() as folder:
            pidfile=Path(folder)/'child.pid'
            script='sleep 30 & echo $! > '+__import__('shlex').quote(str(pidfile))+'; exit 0'
            with self.assertRaises(subprocess.TimeoutExpired):
                actions.command(['/bin/sh','-c',script],timeout=0.2)
            pid=int(pidfile.read_text())
            for _ in range(50):
                state=subprocess.run(['/bin/ps','-p',str(pid),'-o','stat='],capture_output=True,text=True).stdout.strip()
                if not state or state.startswith('Z'):break
                time.sleep(0.02)
            self.assertTrue(not state or state.startswith('Z'),state)

    def test_scheduler_timeout_kills_term_ignoring_descendant(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pidfile=root/'descendant.pid';worker=root/'worker.py'
            worker.write_text('import os,signal,time,sys\nfrom pathlib import Path\n'
                'child=os.fork()\nif child==0:\n signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
                ' Path(sys.argv[1]).write_text(str(os.getpid()))\n while True:time.sleep(.02)\n'
                'signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))\nwhile True:time.sleep(.02)\n')
            with (root/'log').open('w') as output:
                code=scheduler.execute([sys.executable,str(worker),str(pidfile)],dict(os.environ),output,0.5)
            self.assertEqual(code,124)
            state=subprocess.run(['/bin/ps','-p',pidfile.read_text(),'-o','stat='],capture_output=True,text=True).stdout.strip()
            self.assertTrue(not state or state.startswith('Z'),state)

    def test_scheduler_sigterm_keeps_lock_until_worker_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);root.chmod(0o700);pidfile=root/'worker.pid';worker=root/'worker.py'
            worker.write_text('import os,signal,time,sys\nfrom pathlib import Path\n'
                'def stop(*_):\n time.sleep(1.2)\n sys.exit(0)\n'
                'signal.signal(signal.SIGTERM,stop)\nPath(sys.argv[1]).write_text(str(os.getpid()))\ntime.sleep(30)\n')
            config={'path':'/usr/bin:/bin','commands':{'health':[sys.executable,str(worker),str(pidfile)]}}
            (root/'config.json').write_text(json.dumps(config))
            args=[sys.executable,str(ROOT/'deploy/macos/scheduler.py'),'--root',str(root),'health']
            parent=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                deadline=time.monotonic()+5
                while not pidfile.exists() and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(pidfile.exists());parent.terminate()
                config['commands']['health']=['/usr/bin/true'];(root/'config.json').write_text(json.dumps(config))
                second=subprocess.run(args,capture_output=True,text=True,timeout=5)
                self.assertEqual(second.returncode,75)
                parent.communicate(timeout=10)
                self.assertFalse(scheduler.current(root/'state','health')['healthy'])
                self.assertEqual(scheduler.read(root/'state/health-attempt.json')['exit_code'],143)
                self.assertFalse(scheduler.live(int(pidfile.read_text())))
            finally:
                if parent.poll() is None:parent.kill();parent.communicate()

    def test_ambiguous_delivery_is_not_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            scheduler.atomic(root/'state/health-alert.json',{'status':'ambiguous','epoch':int(time.time())})
            with patch.object(scheduler.subprocess,'run') as send:
                result=scheduler.notify(root,{'alert_command':['/usr/bin/false']},'health','new')
            self.assertTrue(result['suppressed']);send.assert_not_called()

    def test_weekly_schedule_uses_detroit_time_across_dst(self):
        zone=ZoneInfo('America/Detroit')
        before=dt.datetime(2026,11,1,3,29,tzinfo=zone).timestamp()
        after=dt.datetime(2026,11,1,3,31,tzinfo=zone).timestamp()
        self.assertEqual(dt.datetime.fromtimestamp(scheduler.slot('restore',before),zone).day,25)
        self.assertEqual(dt.datetime.fromtimestamp(scheduler.slot('restore',after),zone).day,1)
        self.assertEqual(dt.datetime.fromtimestamp(scheduler.slot('restore',after),zone).hour,3)

    @unittest.skipUnless(sys.platform=='darwin','Mac Docker acceptance requires Homebrew and Docker Desktop')
    def test_scratch_configuration_cannot_publish_ports_or_use_live_secrets(self):
        with tempfile.TemporaryDirectory(prefix='medtrack test ') as folder:
            work=Path(folder)
            production={'commit':'a'*40,'services':{name:{'image':'sha256:'+str(i)*64} for i,name in enumerate(('web','db','caddy'),1)}}
            shell=actions.environment(work,production,'medtrack_mac_test_only')
            subprocess.run(['/opt/homebrew/bin/bash','-n',str(shell)],check=True)
            envscript='source '+__import__('shlex').quote(str(shell))+'\nprintf "%s\\n%s\\n" "$MEDTRACK_ENV_FILE" "$MEDTRACK_RESTORE_SCRATCH_ROOT"'
            result=subprocess.check_output(['/opt/homebrew/bin/bash','-c',envscript],text=True)
            self.assertEqual(result.splitlines(),[str(work/'scratch.env'),str(work)])
            compose='source '+__import__('shlex').quote(str(shell))+'\ndocker compose -f "$1/docker-compose.yml" -f "$1/docker-compose.prod.yml" config --format json'
            result=subprocess.run(['/opt/homebrew/bin/bash','-c',compose,'test',str(ROOT)],capture_output=True,text=True,check=True)
            config=json.loads(result.stdout)
            self.assertFalse(config['services']['web'].get('ports'))
            self.assertTrue(all(n.get('internal') for n in config['networks'].values()))
            self.assertEqual(config['services']['web']['restart'],'no')
            self.assertEqual(config['services']['web']['environment']['FCM_ENABLED'],'False')
            for service in ('web','db'):
                self.assertEqual(config['services'][service]['platform'],'linux/amd64')
            self.assertNotIn('production',(work/'scratch.env').read_text())


if __name__=='__main__':unittest.main()
