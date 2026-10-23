#!/usr/bin/env python3
"""Independent Mac recovery scheduling with durable attempt and alert state."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import signal
import sys
import time
import uuid
from zoneinfo import ZoneInfo

JOBS = ('restore', 'scrub', 'health')
MAX_AGE = {'restore': 8*86400, 'scrub':8*86400, 'health':8*3600}


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
    with temp.open('x') as f:
        os.chmod(temp,0o600);json.dump(data,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


def read(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def slot(job, now):
    local=dt.datetime.fromtimestamp(now,ZoneInfo('America/Detroit'))
    if job=='health':
        candidates=[local.replace(hour=h,minute=15,second=0,microsecond=0) for h in (1,7,13,19)]
        candidates += [x-dt.timedelta(days=1) for x in candidates]
    else:
        weekday,hour,minute=(6,3,30) if job=='restore' else (5,8,0)
        day=local-dt.timedelta(days=(local.weekday()-weekday)%7)
        candidate=day.replace(hour=hour,minute=minute,second=0,microsecond=0)
        candidates=[candidate,candidate-dt.timedelta(days=7)]
    return max(x.timestamp() for x in candidates if x.timestamp()<=now)


def current(state, job, now=None):
    now=time.time() if now is None else now
    attempt=read(state/(job+'-attempt.json'))
    success=read(state/(job+'-success.json'))
    good=(attempt.get('outcome')=='success' and attempt.get('run_id')==success.get('run_id')
          and 0<=now-success.get('completed_epoch',0)<=MAX_AGE[job])
    return {'healthy':good,'attempt':attempt,'success':success}


def due(state,job,now):
    c=current(state,job,now)
    return not c['healthy'] or c['success'].get('started_epoch',0)<slot(job,now)


def restore_contract(root, record):
    """Publish the shared shell verifier contract under the scheduler's lock."""
    state=root/'state'
    attempt_id=record['contract_id']
    now=int(time.time())
    outcome=record['outcome']
    checksum='none'
    if outcome=='success':
        raw=('receipt_format=medtrack-independent-scratch-restore-v1\n'
             f'completed_epoch={now}\nattempt_id={attempt_id}\nalert_contract=required\n')
        atomic_text(state/'scratch-restore.receipt',raw)
        checksum=hashlib.sha256(raw.encode('ascii')).hexdigest()
    status={'success':'success','running':'running','failed':'failure'}[outcome]
    stage={'success':'complete','running':'restore','failed':'restore'}[outcome]
    alert='not-needed' if outcome!='failed' else ('delivered' if record.get('alert',{}).get('accepted') else 'failed')
    atomic_text(state/'scratch-restore.receipt.attempt',
        'attempt_format=medtrack-independent-scratch-attempt-v1\n'
        f'attempt_id={attempt_id}\nstatus={status}\nstarted_epoch={record["started_epoch"]}\n'
        f'updated_epoch={now}\nstage={stage}\nalert_delivery={alert}\nreceipt_sha256={checksum}\n')


def atomic_text(path, content):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
    with temp.open('x') as output:
        os.chmod(temp,0o600);output.write(content);output.flush();os.fsync(output.fileno())
    os.replace(temp,path)


def execute(command, env, output, timeout):
    """Terminate the entire child group, allowing the restore cleanup to run."""
    child=subprocess.Popen(command,env=env,stdin=subprocess.DEVNULL,
        stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
    try:
        return child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid,signal.SIGTERM)
        try:
            child.wait(timeout=45)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid,signal.SIGKILL);child.wait()
        return 124


def notify(root,config,job,run_id,test=False):
    hook=config.get('alert_command')
    if not isinstance(hook,list) or not hook or not Path(hook[0]).is_absolute():
        return {'accepted':False,'reason':'alert-not-configured'}
    previous=read(root/'state'/(job+'-alert.json'))
    success=read(root/'state'/(job+'-success.json'))
    if (not test and previous.get('status')=='ambiguous' and
        previous.get('epoch',0)>success.get('completed_epoch',0)):
        return {'accepted':False,'suppressed':True,'reason':'ambiguous-delivery-needs-review'}
    if (not test and previous.get('accepted') and
        previous.get('epoch',0)>success.get('completed_epoch',0) and
        0<=time.time()-previous.get('epoch',0)<21600):
        return {'accepted':False,'suppressed':True,'prior_accepted_epoch':previous['epoch']}
    message={'title':'MEDTRACK recovery test' if test else 'MEDTRACK recovery failed',
             'message':('Intentional migration test: Mac Studio recovery monitoring detected the simulated failure'
                        if test else f'Mac Studio {job} check failed. The latest attempt is marked failed; inspect the private recovery report.'),
             'idempotency_key':'medtrack-mac-'+job+'-'+run_id}
    # Only bounded operational text is passed; exceptions/logs never leave host.
    try:
        r=subprocess.run(hook,input=json.dumps(message),capture_output=True,text=True,timeout=45)
        answer=json.loads(r.stdout)
        result={'accepted':r.returncode==0 and answer.get('status') in ('provider_accepted','duplicate'),
                'status':answer.get('status','unknown'),'epoch':int(time.time())}
        atomic(root/'state'/(job+'-alert.json'),result)
        return result
    except (OSError,ValueError,subprocess.TimeoutExpired):
        result={'accepted':False,'status':'ambiguous','epoch':int(time.time())}
        atomic(root/'state'/(job+'-alert.json'),result)
        return result


def run_job(root,config,job,test=False):
    state=root/'state';logs=root/'logs'
    logs.mkdir(parents=True,exist_ok=True,mode=0o700)
    run_id=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:8]
    record={'format':'medtrack-mac-attempt-v1','job':job,'run_id':run_id,
            'started_epoch':int(time.time()),'outcome':'running','pid':os.getpid(),
            'parent_pid':os.getppid(),'uid':os.getuid(),'test':test}
    record['contract_id']=f'{record["started_epoch"]}-{os.getpid()}-{uuid.uuid4().int}'
    atomic(state/(job+'-attempt.json'),record)
    if job=='restore':restore_contract(root,record)
    log=logs/(job+'-'+run_id+'.log')
    code=1
    try:
        command=config['commands'][job]
        if not isinstance(command,list) or not command or not Path(command[0]).is_absolute():
            raise ValueError('invalid-command')
        with log.open('x') as output:
            os.chmod(log,0o600)
            env={'HOME':str(Path.home()),'PATH':config['path'],'LANG':'en_US.UTF-8',
                 'LC_ALL':'en_US.UTF-8','MEDTRACK_OPERATIONS_ROOT':str(root)}
            code=execute(command,env,output,config.get('timeout_seconds',7200))
    except (OSError,ValueError,KeyError,subprocess.TimeoutExpired):
        code=1
    record.update(completed_epoch=int(time.time()),exit_code=code,outcome='success' if code==0 else 'failed')
    if code:
        record['alert']=notify(root,config,job,run_id,test)
    else:
        atomic(state/(job+'-success.json'),record)
    if job=='restore':restore_contract(root,record)
    atomic(state/(job+'-attempt.json'),record)
    atomic(root/'receipts'/(run_id+'-'+job+'.json'),record)
    return record


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('action',choices=('schedule','status',*JOBS))
    p.add_argument('--test',action='store_true')
    args=p.parse_args(argv);root=args.root.resolve()
    if not root.is_absolute() or root.stat().st_uid!=os.getuid() or root.stat().st_mode & 0o077:
        raise ValueError('private-owner-root-required')
    os.umask(0o077);state=root/'state';state.mkdir(mode=0o700,exist_ok=True)
    if args.action=='status':
        result={job:current(state,job) for job in JOBS}
        print(json.dumps(result,indent=2));return 0 if all(v['healthy'] for v in result.values()) else 1
    with (state/'execution.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('MEDTRACK_MAC_JOB_ALREADY_RUNNING');return 75
        config=read(root/'config.json')
        if args.action=='schedule':
            if config.get('enabled') is not True:
                print('MEDTRACK_MAC_SCHEDULE_NOT_ENABLED');return 0
            jobs=[job for job in JOBS if due(state,job,time.time())]
        else:
            jobs=[args.action]
        failed=False
        for job in jobs:
            record=run_job(root,config,job,args.test)
            print(json.dumps({k:record[k] for k in ('job','run_id','outcome','exit_code')}),flush=True)
            failed|=record['exit_code']!=0
            if failed:break
        return int(failed)


if __name__=='__main__':
    try:
        sys.exit(main())
    except (OSError,ValueError):
        print('MEDTRACK_MAC_SCHEDULER_FAILED',file=sys.stderr);sys.exit(1)
