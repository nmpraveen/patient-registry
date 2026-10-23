#!/usr/bin/env python3
"""Install the owner-scoped Mac scheduler; secrets must already be provisioned."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

LABEL='org.nmpraveen.medtrack.recovery'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path.home()/'Library/Application Support/MEDTRACK/operations')
    p.add_argument('--enable',action='store_true',help='Enable scheduled work after acceptance')
    args=p.parse_args();root=args.root.resolve()
    if sys.platform!='darwin' or os.geteuid()==0:raise ValueError('run-as-mac-owner')
    os.umask(0o077)
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    if root.stat().st_uid!=os.getuid() or root.stat().st_mode & 0o077:raise ValueError('private-root-required')
    for name in ('bin','secrets','state','logs','receipts','cache','runtime','scratch'):
        (root/name).mkdir(mode=0o700,exist_ok=True)
    install_lock=(root/'state/execution.lock').open('a')
    fcntl.flock(install_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    for name in ('scheduler.py','actions.py','pushover_alert.py','deploy.py','process_groups.py'):
        shutil.copy2(Path(__file__).parent/name,root/'bin'/name);(root/'bin'/name).chmod(0o700)
    path='/opt/homebrew/opt/findutils/libexec/gnubin:/opt/homebrew/opt/coreutils/libexec/gnubin:/opt/homebrew/opt/gnu-tar/libexec/gnubin:/opt/homebrew/bin:'+str(Path.home()/'.docker/bin')+':/usr/bin:/bin:/usr/sbin:/sbin'
    config_path=root/'config.json'
    config=json.loads(config_path.read_text()) if config_path.exists() else {}
    config.update(enabled=args.enable,timezone='America/Detroit',path=path,timeout_seconds=7200)
    config['commands']={job:['/opt/homebrew/bin/python3.12',str(root/'bin/actions.py'),job]
                        for job in ('restore','scrub','health')}
    # Delivery requires explicit user authorization; preserve the configured hook.
    config.setdefault('alert_command',[])
    if args.enable:
        if not config['alert_command']:raise ValueError('authorized-alert-hook-required')
        for name in ('backup.agekey','rclone.conf','ssh_config','ssh-key','known_hosts'):
            file=root/'secrets'/name
            if not file.is_file() or file.is_symlink() or file.stat().st_mode & 0o077:
                raise ValueError('private-secret-required')
        if not (root/'settings.json').is_file():raise ValueError('settings-required')
    config_path.write_text(json.dumps(config,indent=2)+'\n');config_path.chmod(0o600)
    plist=Path.home()/'Library/LaunchAgents'/(LABEL+'.plist')
    plist.parent.mkdir(parents=True,exist_ok=True)
    value={'Label':LABEL,'ProgramArguments':['/opt/homebrew/bin/python3.12',str(root/'bin/scheduler.py'),
           '--root',str(root),'schedule'],'RunAtLoad':True,
           'StartCalendarInterval':[{'Minute':minute} for minute in (0,15,30,45)],
           'WorkingDirectory':str(root),'ProcessType':'Background','ExitTimeOut':60,
           'StandardOutPath':str(root/'logs/launchd.log'),'StandardErrorPath':str(root/'logs/launchd.err')}
    with plist.open('wb') as f:plistlib.dump(value,f)
    plist.chmod(0o600)
    domain='gui/'+str(os.getuid())
    loaded=subprocess.run(['launchctl','print',domain+'/'+LABEL],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    if loaded:
        # Do not interrupt an in-flight verifier when refreshing installation.
        state=subprocess.check_output(['launchctl','print',domain+'/'+LABEL],text=True)
        if '\n\tpid = ' in state:raise ValueError('scheduled-job-running')
        subprocess.run(['launchctl','bootout',domain+'/'+LABEL],check=True)
    subprocess.run(['plutil','-lint',str(plist)],check=True)
    # RunAtLoad can acquire the lock after all files and configuration are ready.
    fcntl.flock(install_lock,fcntl.LOCK_UN);install_lock.close()
    subprocess.run(['launchctl','bootstrap',domain,str(plist)],check=True)
    print(json.dumps({'label':LABEL,'enabled':args.enable,'plist':str(plist),'root':str(root)}))


if __name__=='__main__':main()
