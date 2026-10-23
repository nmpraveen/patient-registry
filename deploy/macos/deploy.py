#!/usr/bin/env python3
"""Mac client for fixed production operations; no general sudo or shell."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import uuid


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path.home()/'Library/Application Support/MEDTRACK/operations')
    p.add_argument('operation',choices=('status','authenticated-check','build-receipt','authorize-release','backup','prepare','plan','apply'))
    p.add_argument('--target');p.add_argument('--evidence-id');p.add_argument('--plan-sha256')
    p.add_argument('--manifest',type=Path);p.add_argument('--provenance',type=Path);p.add_argument('--sbom',type=Path)
    args=p.parse_args();root=args.root.resolve();os.umask(0o077)
    command=[args.operation];payload=None
    if args.operation in ('authorize-release','backup','prepare','plan','apply'):
        if not args.target or not re.fullmatch('[a-f0-9]{40}',args.target):p.error('exact full --target required')
        command.append(args.target)
    if args.operation in ('plan','apply'):
        if not args.evidence_id or not re.fullmatch(r'mac-[a-z0-9][a-z0-9-]{0,70}',args.evidence_id):p.error('valid --evidence-id required')
        command.append(args.evidence_id)
    if args.operation=='apply':
        if not args.plan_sha256 or not re.fullmatch('[a-f0-9]{64}',args.plan_sha256):p.error('reviewed --plan-sha256 required')
        command.append(args.plan_sha256)
    if args.operation=='authorize-release':
        payload={}
        for name in ('manifest','provenance','sbom'):
            path=getattr(args,name)
            if path is None or not path.is_file() or not 0<path.stat().st_size<=3*1024*1024:p.error('bounded proof files required')
            payload[name]=base64.b64encode(path.read_bytes()).decode('ascii')
        payload=json.dumps(payload)
        if len(payload)>4*1024*1024:p.error('proof exceeds 4 MiB')
    ssh=['/usr/bin/ssh','-F',str(root/'secrets/ssh_config'),'nnh-mac-operations',
         'sudo -n /usr/local/sbin/medtrack-mac-ops '+shlex.join(command)]
    run_id=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:8]
    log=root/'logs'/('deployment-'+run_id+'.log')
    with log.open('x') as output:
        result=subprocess.run(ssh,input=payload,text=True,stdout=output,stderr=subprocess.STDOUT,
            env={'HOME':str(Path.home()),'PATH':'/usr/bin:/bin'},timeout=7200)
    receipt={'operation':args.operation,'target':args.target,'exit_code':result.returncode,
             'completed_epoch':int(time.time()),'log':str(log),'run_id':run_id}
    (root/'receipts'/('deployment-'+run_id+'.json')).write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt));raise SystemExit(result.returncode)


if __name__=='__main__':main()
