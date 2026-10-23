#!/usr/bin/python3
"""Root-owned, fixed-scope MEDTRACK operations exposed to the Mac SSH operator.

Install outside the checkout. Never execute a user-supplied shell command, path,
environment, image tag, or Git remote. Existing guarded deployment gates remain
authoritative. stdout from export-image/evidence is a binary archive.
"""
import argparse
import base64
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

ROOT = Path('/srv/medtrack/app')
EVIDENCE = Path('/srv/medtrack/deploy-evidence')
BACKUP = Path('/srv/medtrack/offsite-backups/state/latest-pre-deployment.receipt')
PROOFS = EVIDENCE/'mac-release-proofs'
REMOTE = 'https://github.com/nmpraveen/patient-registry.git'
ENV = {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
       'HOME': '/root', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}
COMPOSE = ['docker', 'compose', '-f', str(ROOT/'docker-compose.yml'),
           '-f', str(ROOT/'docker-compose.prod.yml')]
SHA = re.compile(r'[a-f0-9]{40}\Z')
DIGEST = re.compile(r'sha256:[a-f0-9]{64}\Z')
REQUIRED_CHECKS=frozenset(('Django tests','Migration integrity','Strict OpenAPI',
    'Supply-chain scans','Compose and shell','Container integrity','Frontend no-overflow'))


def github_json(path):
    # This repository is public. No credential forwarding or caller URL allowed.
    request=urllib.request.Request('https://api.github.com/repos/nmpraveen/patient-registry/'+path,
        headers={'Accept':'application/vnd.github+json','User-Agent':'MEDTRACK-Mac-Operations',
                 'X-GitHub-Api-Version':'2026-03-10'})
    with urllib.request.urlopen(request,timeout=30) as response:
        if response.geturl()!=request.full_url:raise ValueError('unexpected-github-redirect')
        data=response.read(4*1024*1024+1)
        if len(data)>4*1024*1024:raise ValueError('github-response-too-large')
        return json.loads(data)


def verify_ci(target):
    if not SHA.fullmatch(target):raise ValueError('invalid-target')
    data=github_json('actions/workflows/ci.yml/runs?head_sha='+target+'&event=push&branch=main&per_page=100')
    runs=data['workflow_runs']
    if not runs or data['total_count']>100:raise ValueError('missing-or-ambiguous-main-ci')
    latest=max(runs,key=lambda item:(int(item['run_number']),int(item['run_attempt'])))
    if (latest['head_sha']!=target or latest['head_branch']!='main' or latest['event']!='push' or
        latest['path']!='.github/workflows/ci.yml' or latest['repository']['full_name']!='nmpraveen/patient-registry' or
        latest['status']!='completed' or latest['conclusion']!='success'):
        raise ValueError('main-ci-not-successful')
    run_id=int(latest['id']);attempt=int(latest['run_attempt'])
    jobs=github_json(f'actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100')
    if jobs['total_count']>100:raise ValueError('too-many-ci-jobs')
    selected={}
    for job in jobs['jobs']:
        # Require every job in this exact CI run, including future additions
        # such as PR145's Windows verifier, and never accept skipped work.
        if (job['name'] in selected or job['head_sha']!=target or job['run_id']!=run_id or
            job['status']!='completed' or job['conclusion']!='success' or
            'self-hosted' in job.get('labels',[])):
            raise ValueError('required-ci-job-not-successful')
        selected[job['name']]=job['id']
    if not REQUIRED_CHECKS.issubset(selected):raise ValueError('required-ci-job-missing')
    return {'run_id':run_id,'attempt':attempt,'source_commit':target,
            'checks':selected,'verified_epoch':int(time.time())}


def run(args, capture=False, extra_env=None):
    return subprocess.run(args, cwd=ROOT, env=ENV | (extra_env or {}),
                          check=True, stdout=subprocess.PIPE if capture else None,
                          text=capture).stdout


def git(*args):
    return run(['git', '-c', f'safe.directory={ROOT}', *args], True).strip()


def trusted(path):
    """Every existing component must be root-owned, non-symlink, non-writable."""
    for item in [path, *path.parents]:
        s = item.lstat()
        if stat.S_ISLNK(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o022:
            raise ValueError('untrusted-operation-path')


def clean_source():
    trusted(ROOT)
    trusted(ROOT/'.git')
    for name in ('.git/config','.git/HEAD','.env','docker-compose.yml','docker-compose.prod.yml'):
        trusted(ROOT/name)
    for name in ('/root/.gitconfig','/etc/gitconfig'):
        if Path(name).exists():trusted(Path(name))
    if git('status', '--porcelain=v1', '--untracked-files=no'):
        raise ValueError('modified-production-source')
    if git('remote', 'get-url', 'origin').removesuffix('.git') != REMOTE.removesuffix('.git'):
        raise ValueError('unexpected-production-remote')
    # Git-object-only builds plus the runtime .env cover all executable inputs.
    for name in run(['git','-c',f'safe.directory={ROOT}','ls-files','-z'],True).split('\0'):
        if name:trusted(ROOT/name)


def reviewed_target(target, fetch=False):
    if not SHA.fullmatch(target):
        raise ValueError('invalid-target')
    clean_source()
    if fetch:
        run(['git', '-c', f'safe.directory={ROOT}', 'fetch', '--no-tags', 'origin', 'main'])
    run(['git','-c',f'safe.directory={ROOT}','merge-base','--is-ancestor',target,'refs/remotes/origin/main'])


def require_proof(target):
    path=PROOFS/target/'approved.json';trusted(path)
    proof=json.loads(path.read_text())
    if (proof.get('format')!='medtrack-verified-release-v2' or proof.get('source_commit')!=target or
        not 0<=time.time()-proof.get('verified_epoch',0)<=7200):
        raise ValueError('missing-reviewed-release-proof')
    # A later queued/failed rerun must invalidate an earlier green receipt.
    verify_ci(target)
    return proof


def authorize_release(target):
    reviewed_target(target,fetch=True)
    ci=verify_ci(target)
    raw=sys.stdin.buffer.read(4*1024*1024+1)
    if len(raw)>4*1024*1024:raise ValueError('release-proof-too-large')
    payload=json.loads(raw)
    if set(payload)!= {'manifest','provenance','sbom'}:raise ValueError('invalid-release-proof-members')
    binary=Path(shutil.which('gh',path=ENV['PATH']) or '/missing-gh');trusted(binary)
    PROOFS.mkdir(mode=0o700,exist_ok=True);trusted(PROOFS)
    destination=PROOFS/target;destination.mkdir(mode=0o700,exist_ok=True);trusted(destination)
    with tempfile.TemporaryDirectory(prefix='verify-',dir=destination) as folder:
        work=Path(folder)
        for name,value in payload.items():
            data=base64.b64decode(value,validate=True)
            if not data or len(data)>3*1024*1024:raise ValueError('invalid-release-proof-size')
            (work/(name if name=='manifest' else name+'.jsonl')).write_bytes(data)
        manifest=json.loads((work/'manifest').read_bytes())
        if manifest.get('schemaVersion')!=2 or 'config' not in manifest or 'layers' not in manifest:
            raise ValueError('invalid-oci-manifest')
        for bundle,predicate in [('provenance','https://slsa.dev/provenance/v1'),('sbom','https://cyclonedx.org/bom')]:
            run([str(binary),'attestation','verify',str(work/'manifest'),'--bundle',str(work/(bundle+'.jsonl')),
                 '--repo','nmpraveen/patient-registry','--source-ref','refs/heads/main',
                 '--source-digest',target,'--signer-digest',target,
                 '--cert-identity','https://github.com/nmpraveen/patient-registry/.github/workflows/attest-release.yml@refs/heads/main',
                 '--cert-oidc-issuer','https://token.actions.githubusercontent.com',
                 '--deny-self-hosted-runners','--predicate-type',predicate,'--format','json'],capture=True)
        proof={'format':'medtrack-verified-release-v2','source_commit':target,'ci':ci,
               'manifest_digest':'sha256:'+hashlib.sha256((work/'manifest').read_bytes()).hexdigest(),
               'provenance_sha256':hashlib.sha256((work/'provenance.jsonl').read_bytes()).hexdigest(),
               'sbom_sha256':hashlib.sha256((work/'sbom.jsonl').read_bytes()).hexdigest(),
               'verified_epoch':int(time.time())}
        (work/'approved.json').write_text(json.dumps(proof)+'\n')
        for name in ('manifest','provenance.jsonl','sbom.jsonl','approved.json'):
            os.chmod(work/name,0o600);os.replace(work/name,destination/name)
    print(json.dumps(proof))


@contextlib.contextmanager
def lock(path):
    if path.exists() or path.is_symlink():trusted(path)
    trusted(path.parent)
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'w') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


def evidence_dir(slug):
    if not re.fullmatch(r'mac-[a-z0-9][a-z0-9-]{0,70}', slug):
        raise ValueError('invalid-evidence-id')
    trusted(EVIDENCE)
    path = EVIDENCE/slug
    if path.exists() or path.is_symlink():
        trusted(path)
    return path


def services():
    result = {}
    for service in ('web', 'db', 'caddy'):
        container = run(COMPOSE + ['ps', '-q', service], True).strip()
        if not re.fullmatch(r'[a-f0-9]{12,64}', container):
            raise ValueError('missing-production-service')
        value = json.loads(run(['docker', 'inspect', '--format',
            '{"image":{{json .Image}},"health":{{json .State.Health.Status}},'
            '"running":{{json .State.Running}}}', container], True))
        if not DIGEST.fullmatch(value['image']):
            raise ValueError('invalid-production-image')
        result[service] = value
    return result


def running_identity(service_state):
    image=service_state['web']['image']
    labels=json.loads(run(['docker','image','inspect','--format','{{json .Config.Labels}}',image],True))
    revision=labels.get('org.opencontainers.image.revision','')
    if not SHA.fullmatch(revision):raise ValueError('running-image-source-missing')
    version=git('show',revision+':VERSION')
    return {'source_commit':revision,'version':version,'image_id':image,'labels':labels}


def parse(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    for name in ('status', 'authenticated-check', 'evidence'):
        sub.add_parser(name)
    export = sub.add_parser('export-image')
    export.add_argument('service', choices=('web', 'db', 'caddy'))
    export.add_argument('expected_image')
    sub.add_parser('build-receipt')
    backup = sub.add_parser('backup')
    backup.add_argument('target')
    prepare = sub.add_parser('prepare')
    prepare.add_argument('target')
    authorize=sub.add_parser('authorize-release')
    authorize.add_argument('target')
    for name in ('plan', 'apply'):
        action = sub.add_parser(name)
        action.add_argument('target')
        action.add_argument('evidence_id')
        if name == 'apply':
            action.add_argument('plan_sha256')
    return parser.parse_args(argv)


def perform(args):
    if os.geteuid() != 0:
        raise ValueError('requires-installed-root-helper')
    os.umask(0o077)
    clean_source()
    if args.operation == 'authorize-release':
        authorize_release(args.target)
    elif args.operation == 'status':
        service_state=services();identity=running_identity(service_state)
        print(json.dumps({'format':'medtrack-mac-ops-v2','commit':identity['source_commit'],
                          'running_commit':identity['source_commit'],'checkout_commit':git('rev-parse','HEAD'),
                          'version':identity['version'],'services':service_state,'checked_epoch':int(time.time())}))
    elif args.operation == 'authenticated-check':
        trusted(Path('/root/medtrack-authenticated-login-smoke'))
        run(['/root/medtrack-authenticated-login-smoke'],
            extra_env={'MEDTRACK_SMOKE_BASE_URL':'https://book.naveenhospital.net'})
    elif args.operation == 'export-image':
        if not DIGEST.fullmatch(args.expected_image):
            raise ValueError('invalid-image-digest')
        if services()[args.service]['image'] != args.expected_image:
            raise ValueError('production-image-changed')
        run(['docker','image','save',args.expected_image])
    elif args.operation == 'build-receipt':
        identity=running_identity(services());labels=identity['labels']
        selected = {k:v for k,v in labels.items() if k.startswith('org.opencontainers.image.')
                    or k.startswith('org.medtrack.')}
        print(json.dumps({'image_id':identity['image_id'],'source_commit':identity['source_commit'],
                          'checkout_commit':git('rev-parse','HEAD'),'labels':selected}))
    elif args.operation == 'evidence':
        evidence=Path('/srv/medtrack/security-evidence')
        trusted(evidence)
        digest=hashlib.sha256();size=0
        class Sink:
            def write(self,data):
                nonlocal size
                size+=len(data)
                if size>200*1024*1024:raise ValueError('evidence-too-large')
                digest.update(data);sys.stdout.buffer.write(data);return len(data)
            def flush(self):sys.stdout.buffer.flush()
        with (evidence/'export.lock').open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_SH)
            for item in (evidence/'segments').rglob('*'):
                if item.is_symlink() or not (item.is_file() or item.is_dir()):
                    raise ValueError('unsafe-evidence-object')
            with tarfile.open(fileobj=Sink(),mode='w|gz') as archive:
                archive.add(evidence/'segments',arcname='segments')
                for name in ('checkpoint.env','anchor.env'):
                    item=evidence/'state'/name
                    if item.is_file() and not item.is_symlink():
                        archive.add(item,arcname='state/'+name)
        print(json.dumps({'sha256':digest.hexdigest(),'bytes':size}),file=sys.stderr)
    elif args.operation == 'backup':
        reviewed_target(args.target, fetch=True)
        require_proof(args.target)
        trusted(Path('/etc/medtrack-backup/backup.env'))
        trusted(Path('/srv/medtrack/backup-secrets/rclone.conf'))
        trusted(Path('/srv/medtrack/backup-secrets/age-recipient.txt'))
        run([str(ROOT/'scripts/backup-offsite.sh'),'--tier','pre-deployment',
             '--target-commit',args.target],extra_env={'MEDTRACK_BACKUP_CONFIG':'/etc/medtrack-backup/backup.env'})
        run(['systemctl','start','medtrack-nas-export.service'])
        if run(['systemctl','show','medtrack-nas-export.service','--property=Result','--value'],True).strip() != 'success':
            raise ValueError('nas-export-failed')
    elif args.operation == 'prepare':
        reviewed_target(args.target, fetch=True)
        require_proof(args.target)
        # Backup requires the target checkout while recording the still-running
        # source image. Preparation changes Git only; plan/apply retain the
        # fresh target-bound backup gates before any application activation.
        run(['git','-c',f'safe.directory={ROOT}','merge-base','--is-ancestor','HEAD',args.target])
        changed=git('rev-parse','HEAD')!=args.target
        if changed:run(['git','-c',f'safe.directory={ROOT}','checkout','--detach',args.target])
        print(json.dumps({'source_prepared':args.target,'checkout_changed':changed,'application_changed':False}))
    elif args.operation in ('plan','apply'):
        reviewed_target(args.target)
        require_proof(args.target)
        trusted(BACKUP)
        trusted(Path('/root/medtrack-authenticated-login-smoke'))
        if git('rev-parse','HEAD') != args.target:
            raise ValueError('source-not-prepared')
        path = evidence_dir(args.evidence_id)
        command = [str(ROOT/'scripts/deploy-production.sh'),args.operation,args.target,
                   '--backup-receipt',str(BACKUP),'--evidence-dir',str(path)]
        if args.operation == 'apply':
            if not re.fullmatch(r'[a-f0-9]{64}',args.plan_sha256):
                raise ValueError('invalid-plan-hash')
            trusted(path/'migration-plan.txt')
            if hashlib.sha256((path/'migration-plan.txt').read_bytes()).hexdigest() != args.plan_sha256:
                raise ValueError('plan-hash-mismatch')
            command += ['--approve-plan-sha256',args.plan_sha256,
                        '--login-smoke-hook','/root/medtrack-authenticated-login-smoke']
        run(command)


def main(argv=None):
    args=parse(argv)
    mutable=args.operation in ('authorize-release','backup','prepare','plan','apply')
    if mutable:
        # Serialize Mac requests; existing apply acquires the global operation
        # lock itself and revalidates source, backup, plan and image receipts.
        with lock(Path('/run/medtrack-mac-operations.lock')):
            if args.operation=='apply':perform(args)
            else:
                with lock(Path('/run/medtrack-operations.lock')):perform(args)
    else:perform(args)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError):
        # Deliberately exclude raw exceptions, command environments and stdout.
        print('MEDTRACK_MAC_OPERATION_FAILED',file=sys.stderr)
        sys.exit(1)
