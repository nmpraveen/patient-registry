#!/usr/bin/env python3
"""Mac-local MEDTRACK recovery; production data is used only in private scratch."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
import uuid
from process_groups import terminate as terminate_group

ROOT=Path(os.environ.get('MEDTRACK_OPERATIONS_ROOT',str(Path.home()/'Library/Application Support/MEDTRACK/operations')))
PATH='/opt/homebrew/opt/findutils/libexec/gnubin:/opt/homebrew/opt/coreutils/libexec/gnubin:/opt/homebrew/opt/gnu-tar/libexec/gnubin:/opt/homebrew/bin:'+str(Path.home()/'.docker/bin')+':/usr/bin:/bin:/usr/sbin:/sbin'
ENV={'HOME':str(Path.home()),'PATH':PATH,'LANG':'en_US.UTF-8','LC_ALL':'en_US.UTF-8',
     'DOCKER_CONTEXT':'desktop-linux','PYTHON_COMMAND':'/opt/homebrew/bin/python3.12'}
SHA=re.compile(r'[a-f0-9]{40}\Z')
DIGEST=re.compile(r'sha256:[a-f0-9]{64}\Z')
TIERS=('rapid','daily','weekly','monthly','pre-deployment','canary')
ARCHIVE=re.compile(r'medtrack-prod-(rapid|daily|weekly|monthly|pre-deployment|canary)-[0-9]{8}T[0-9]{6}Z\.tar\.age\Z')
MARKER_FIELDS={'archive','sha256','completed_utc','drive_verified','drive_verified_epoch',
               'source_commit','intended_target_commit','security_evidence_chain_sha256'}


def command(args,*,capture=True,cwd=None,env=None,timeout=1800,stdin=None):
    process=subprocess.Popen(args,cwd=cwd,env=ENV|(env or {}),stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                          stdout=subprocess.PIPE if capture else None,stderr=subprocess.PIPE,
                          text=True,start_new_session=True)
    try:
        output,error=process.communicate(input=stdin,timeout=timeout)
    except BaseException:
        try:terminate_group(process)
        finally:
            for stream in (process.stdin,process.stdout,process.stderr):
                if stream is not None:stream.close()
        raise
    if process.returncode:
        diagnostic=ROOT/'logs/last-command-error.log'
        diagnostic.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        diagnostic.write_text(error[-32768:]);diagnostic.chmod(0o600)
        raise RuntimeError('recovery-command-failed:'+Path(args[0]).name)
    return output


def settings():
    return json.loads((ROOT/'settings.json').read_text())


def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2)+'\n');os.chmod(temp,0o600);os.replace(temp,path)


def ssh_args(*args):
    return ['/usr/bin/ssh','-F',str(ROOT/'secrets/ssh_config'),'nnh-mac-operations',
            'sudo -n /usr/local/sbin/medtrack-mac-ops '+' '.join(shlex.quote(x) for x in args)]


def status():
    value=json.loads(command(ssh_args('status'),timeout=45))
    if not SHA.fullmatch(value['commit']):raise ValueError('invalid-production-source')
    for item in value['services'].values():
        if not DIGEST.fullmatch(item['image']) or not item['running'] or item['health']!='healthy':
            raise ValueError('production-not-healthy')
    return value


def download_binary(args,target,maximum,timeout=600):
    temp=target.with_suffix(target.suffix+'.partial');digest=hashlib.sha256();count=0
    process=subprocess.Popen(['/opt/homebrew/bin/gtimeout','--kill-after=30s',str(timeout),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,start_new_session=True)
    try:
        with temp.open('wb') as out:
            os.chmod(temp,0o600)
            while chunk:=process.stdout.read(1024*1024):
                count+=len(chunk)
                if count>maximum:raise ValueError('transfer-size-limit')
                out.write(chunk);digest.update(chunk)
        error=process.stderr.read().decode('utf-8','replace')
        if process.wait(timeout=timeout):raise RuntimeError('remote-export-failed')
        os.replace(temp,target)
        return {'sha256':digest.hexdigest(),'bytes':count},error
    finally:
        if process.poll() is None:terminate_group(process)
        if temp.exists():temp.unlink()


def source(commit):
    if not SHA.fullmatch(commit):raise ValueError('invalid-source-commit')
    destination=ROOT/'runtime/sources'/commit
    if not destination.exists():
        destination.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        command(['git','clone','--no-hardlinks','--no-checkout',settings()['seed_repository'],str(destination)])
        command(['git','remote','set-url','origin','https://github.com/nmpraveen/patient-registry.git'],cwd=destination)
        if subprocess.run(['git','cat-file','-e',commit+'^{commit}'],cwd=destination,env=ENV,
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
            command(['git','fetch','origin','main'],cwd=destination)
        command(['git','checkout','--detach',commit],cwd=destination)
    if command(['git','rev-parse','HEAD'],cwd=destination).strip()!=commit:
        raise ValueError('source-checkout-mismatch')
    if command(['git','status','--porcelain','--untracked-files=no'],cwd=destination).strip():
        raise ValueError('modified-recovery-source')
    return destination


def ensure_images(production):
    for service,item in production['services'].items():
        image=item['image']
        inspected=subprocess.run(['docker','--context','desktop-linux','image','inspect','--format','{{.Id}}',image],
                                 env=ENV,capture_output=True,text=True)
        if inspected.returncode:
            target=ROOT/'cache'/('image-'+service+'-'+image[7:19]+'.tar')
            receipt,_=download_binary(ssh_args('export-image',service,image),target,2*1024**3)
            command(['docker','--context','desktop-linux','image','load','--input',str(target)],timeout=1200)
            receipt.update(service=service,image=image)
            write_json(ROOT/'receipts'/('image-'+image[7:]+'.json'),receipt)
        loaded=command(['docker','--context','desktop-linux','image','inspect','--format','{{.Id}}',image]).strip()
        if loaded!=image:raise ValueError('source-image-identity-mismatch')


def evidence():
    production=status();repo=source(production['commit'])
    run_id=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:8]
    work=ROOT/'scratch'/('evidence-'+run_id);work.mkdir(mode=0o700)
    try:
        target=work/'snapshot.tar.gz'
        receipt,error=download_binary(ssh_args('evidence'),target,200*1024**2)
        if json.loads(error.strip())!=receipt:raise ValueError('evidence-transfer-hash-mismatch')
        tree=work/'tree';tree.mkdir(mode=0o700)
        with tarfile.open(target) as archive:
            members=archive.getmembers();size=0
            for member in members:
                path=Path(member.name)
                if (path.is_absolute() or '..' in path.parts or not path.parts or
                    path.parts[0] not in ('segments','state') or not (member.isdir() or member.isfile())):
                    raise ValueError('unsafe-evidence-archive')
                size+=member.size
            if size>1024**3:raise ValueError('evidence-expansion-limit')
            archive.extractall(tree,members=members,filter='data')
        result=command(['/opt/homebrew/bin/bash',str(repo/'scripts/verify-security-evidence.sh'),'--root',str(tree)],
                       env={'MEDTRACK_BACKUP_CONFIG':'/nonexistent/medtrack-mac',
                            'MEDTRACK_SECURITY_EVIDENCE_MAX_AGE_SECONDS':'7200',
                            'MEDTRACK_SECURITY_EVIDENCE_ALLOW_STALE':'0'}).strip()
        if not re.fullmatch(r'SECURITY_EVIDENCE_HEALTH_OK segments=\d+ chain_sha256=[a-f0-9]{64} age_seconds=\d+',result):
            raise ValueError('invalid-evidence-receipt')
        receipt.update(completed_epoch=int(time.time()),verification=result,source_commit=production['commit'])
        write_json(ROOT/'receipts/latest-evidence.json',receipt)
        print(result)
    finally:
        shutil.rmtree(work)


def nas_download(archive=None,tier=None):
    folder=ROOT/'cache/nas'/('restore-'+uuid.uuid4().hex[:12]);folder.mkdir(parents=True,mode=0o700)
    args=['/opt/homebrew/bin/pwsh','-NoProfile','-File',settings()['nas_download_helper'],'-Destination',str(folder)]
    if archive:args+=['-Archive',archive]
    if tier:args+=['-Tier',tier]
    result=json.loads(command(args,timeout=300))
    verified=verify_triplet(Path(result['archive']))
    if result['sha256']!=verified['sha256'] or result['marker']!=verified['marker']:
        raise ValueError('nas-download-metadata-mismatch')
    result.update(verified)
    write_json(folder/'download.json',result)
    return result


def verify_triplet(ciphertext):
    archive=ciphertext.name
    if not ARCHIVE.fullmatch(archive):raise ValueError('invalid-backup-name')
    for suffix in ('','.sha256','.complete'):
        path=Path(str(ciphertext)+suffix)
        maximum=2*1024**3 if not suffix else 65536
        if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=maximum:
            raise ValueError('invalid-backup-file')
    marker={}
    for line in Path(str(ciphertext)+'.complete').read_text(encoding='ascii').splitlines():
        if '=' not in line:raise ValueError('invalid-completion-marker')
        key,value=line.split('=',1)
        if key in marker or key not in MARKER_FIELDS or not value:
            raise ValueError('invalid-completion-marker')
        marker[key]=value
    if set(marker)!=MARKER_FIELDS:raise ValueError('incomplete-completion-marker')
    stamp=archive[-24:-8]
    completed=dt.datetime.strptime(stamp,'%Y%m%dT%H%M%SZ').replace(tzinfo=dt.timezone.utc)
    if (completed.strftime('%Y%m%dT%H%M%SZ')!=stamp or marker['completed_utc']!=stamp or
        marker['archive']!=archive or marker['drive_verified']!='1' or
        not re.fullmatch('[1-9][0-9]{0,11}',marker['drive_verified_epoch']) or
        not completed.timestamp()<=int(marker['drive_verified_epoch'])<=int(time.time())+300 or
        not SHA.fullmatch(marker['source_commit']) or not SHA.fullmatch(marker['intended_target_commit']) or
        not re.fullmatch('[a-f0-9]{64}',marker['security_evidence_chain_sha256'])):
        raise ValueError('invalid-completion-marker-values')
    with ciphertext.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    checksum=Path(str(ciphertext)+'.sha256').read_text(encoding='ascii').strip().split()
    if checksum!=[digest,archive] or marker['sha256']!=digest:
        raise ValueError('backup-triplet-verification-failed')
    return {'archive':str(ciphertext),'sha256':digest,'bytes':ciphertext.stat().st_size,'marker':marker}


def bind_backup(downloaded,production,verification=None):
    marker=downloaded['marker'];archive=Path(downloaded['archive']).name
    tier=ARCHIVE.fullmatch(archive).group(1)
    target=production.get('checkout_commit',production['commit']) if tier=='pre-deployment' else production['commit']
    if marker['source_commit']!=production['commit'] or marker['intended_target_commit']!=target:
        raise ValueError('backup-source-or-target-mismatch')
    if verification is not None:
        expected={'archive':archive,'ciphertext_sha256':downloaded['sha256'],
                  'git_commit':marker['source_commit'],'intended_target_commit':marker['intended_target_commit'],
                  'security_evidence_chain_sha256':marker['security_evidence_chain_sha256']}
        if any(verification.get(key)!=value for key,value in expected.items()):
            raise ValueError('restore-receipt-binding-mismatch')


def drive_download(archive,tier):
    if not archive or not tier or not ARCHIVE.fullmatch(archive) or ARCHIVE.fullmatch(archive).group(1)!=tier:
        raise ValueError('exact-drive-archive-and-tier-required')
    folder=ROOT/'cache/drive'/('restore-'+uuid.uuid4().hex[:12]);folder.mkdir(parents=True,mode=0o700)
    remote='medtrack-drive:Naveen-Hospital-Backups/MEDTRACK/production/'+tier+'/'+archive
    for suffix in ('.complete','.sha256',''):
        command(['/opt/homebrew/bin/rclone','--config',str(ROOT/'secrets/rclone.conf'),
                 'copyto',remote+suffix,str(folder/(archive+suffix))],timeout=600)
    result={'format':'medtrack-drive-download-v1','source':remote,'read_only':True,**verify_triplet(folder/archive)}
    write_json(folder/'download.json',result);return result


def environment(work,production,project):
    values={'COMPOSE_PROJECT_NAME':project,'MEDTRACK_APP_IMAGE':production['services']['web']['image'],
            'MEDTRACK_BUILD_REVISION':production['commit'],'SECRET_KEY':secrets.token_hex(48),
            'DEBUG':'False','ALLOWED_HOSTS':'localhost,127.0.0.1','MEDTRACK_DOMAIN':'localhost',
            'CSRF_TRUSTED_ORIGINS':'http://localhost','POSTGRES_DB':'patient_registry',
            'POSTGRES_USER':'patient_registry','POSTGRES_PASSWORD':secrets.token_hex(32),
            'POSTGRES_HOST':'db','POSTGRES_PORT':'5432','GUNICORN_WORKERS':'1',
            'SECURE_SSL_REDIRECT':'False','SECURE_HSTS_SECONDS':'31536000',
            'SECURE_HSTS_INCLUDE_SUBDOMAINS':'True','SECURE_HSTS_PRELOAD':'False',
            'SESSION_COOKIE_SECURE':'True','CSRF_COOKIE_SECURE':'True','USE_X_FORWARDED_PROTO':'False',
            'ALLOW_MOCK_DATA_SEEDING':'False','FCM_ENABLED':'False','FCM_CREDENTIALS_FILE':'','FCM_PROJECT_ID':''}
    env_file=work/'scratch.env'
    env_file.write_text(''.join(k+'='+shlex.quote(v)+'\n' for k,v in values.items()));os.chmod(env_file,0o600)
    overlay=work/'compose.yml'
    overlay.write_text('''services:
  db:
    image: DB_IMAGE
    platform: linux/amd64
    pull_policy: never
    restart: "no"
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
  web:
    platform: linux/amd64
    pull_policy: never
    restart: "no"
    ports: !reset []
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    volumes: !override
      - mac_backups:/app/backups
      - mac_logs:/var/log/medtrack
  migrate:
    platform: linux/amd64
    pull_policy: never
    volumes: !override
      - mac_backups:/app/backups
  caddy:
    profiles: [unused-verifier-edge]
    networks:
      medtrack_edge:
        ipv4_address: !reset null
networks:
  default:
    internal: true
  medtrack_edge:
    internal: true
    ipam:
      config: !reset []
volumes:
  mac_backups:
  mac_logs:
'''.replace('DB_IMAGE',production['services']['db']['image']))
    shell=work/'environment.sh'
    shell.write_text('''set -Eeuo pipefail
umask 077
export PATH=OPS_PATH
export DOCKER_CONTEXT=desktop-linux
unset DOCKER_HOST DOCKER_TLS_VERIFY DOCKER_CERT_PATH MEDTRACK_ALLOW_PRODUCTION_RESTORE
export MEDTRACK_ENV_FILE=__ENV_FILE__
set -a
source "$MEDTRACK_ENV_FILE"
set +a
export PYTHON_COMMAND=/opt/homebrew/bin/python3.12
export MEDTRACK_RESTORE_SCRATCH_ROOT=__SCRATCH_ROOT__
export MEDTRACK_REQUIRE_AUDIT_EVENT_SCHEMA=1
export OPS_OVERLAY=__OVERLAY__
export OPS_CADDY_IMAGE=__CADDY_IMAGE__
docker() {
  local arg injected=0
  local -a rewritten=()
  for arg in "$@"; do
    if [[ "$arg" == medtrack-caddy:2.11.4-ratelimit ]]; then arg="$OPS_CADDY_IMAGE"; fi
    rewritten+=("$arg")
    if [[ "${1:-}" == compose && "$arg" == */docker-compose.prod.yml ]]; then
      rewritten+=(-f "$OPS_OVERLAY")
      injected=1
    fi
    if [[ "${1:-}" == run && "$arg" == run ]]; then rewritten+=(--network none --platform linux/amd64); fi
  done
  if [[ "${1:-}" == compose && "$injected" != 1 ]]; then
    echo 'Refusing Compose outside the isolated verifier' >&2; return 1
  fi
  command docker --context desktop-linux "${rewritten[@]}"
}
export -f docker
'''.replace('OPS_PATH',shlex.quote(PATH)).replace('__ENV_FILE__',shlex.quote(str(env_file)))
       .replace('__SCRATCH_ROOT__',shlex.quote(str(work))).replace('__OVERLAY__',shlex.quote(str(overlay)))
       .replace('__CADDY_IMAGE__',shlex.quote(production['services']['caddy']['image'])))
    return shell


def restore(archive=None,tier=None,backup_source='nas'):
    production=status();repo=source(production['commit']);ensure_images(production)
    downloaded=drive_download(archive,tier) if backup_source=='drive' else nas_download(archive,tier)
    bind_backup(downloaded,production)
    run_id=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:8]
    project='medtrack_mac_restore_'+uuid.uuid4().hex[:12]
    work=ROOT/'scratch'/project;work.mkdir(mode=0o700)
    receipts=ROOT/'receipts'/('restore-'+run_id);receipts.mkdir(mode=0o700)
    shell=environment(work,production,project)
    prefix='source '+shlex.quote(str(shell))+'\ncd '+shlex.quote(str(repo))+'\n'
    compose='docker compose -f "$PWD/docker-compose.yml" -f "$PWD/docker-compose.prod.yml"'
    labels=json.loads(command(['docker','image','inspect','--format','{{json .Config.Labels}}',production['services']['web']['image']]))
    context=labels.get('org.medtrack.build-context.sha256') or labels.get('io.medtrack.build-context.sha256')
    if not context:
        matches=[v for k,v in labels.items() if 'context' in k and re.fullmatch(r'sha256:[a-f0-9]{64}',v)]
        if len(matches)!=1:raise ValueError('missing-source-context-label')
        context=matches[0]
    attestation=work/'source.attestation'
    attestation.write_text('attestation_format=medtrack-build-receipt-v1\nrevision='+production['commit']+
        '\nbuild_context_schema=medtrack.build-context/v1\nbuild_context_sha256='+context+
        '\nimage_ref='+production['services']['web']['image']+'\nimage_id='+production['services']['web']['image']+'\n')
    existing=command(['docker','ps','-aq','--filter','label=com.docker.compose.project='+project]).strip()
    if existing:raise ValueError('scratch-project-already-exists')
    try:
        # Named volumes contain all restored records/logs and are removed by label.
        setup=prefix+compose+' create --no-build db web\n'+compose+' run --rm --no-deps --user 0:0 --cap-add CHOWN --entrypoint sh web -c '+shlex.quote('chown 10001:10001 /app/backups /var/log/medtrack')+'\n'+compose+' up -d --no-build db web\n'
        command(['/opt/homebrew/bin/bash','-c',setup],capture=False,cwd=repo)
        args=[str(repo/'scripts/restore.sh'),'verify','--archive',downloaded['archive'],
              '--checksum',downloaded['archive']+'.sha256','--identity',str(ROOT/'secrets/backup.agekey'),
              '--expected-commit',production['commit'],'--image-attestation',str(attestation),'--receipt-dir',str(receipts)]
        command(['/opt/homebrew/bin/bash','-c',prefix+shlex.join(args)],capture=False,cwd=repo,timeout=7200)
        values=dict(line.split('=',1) for line in (receipts/'verification.receipt').read_text().splitlines() if '=' in line)
        bind_backup(downloaded,production,values)
        # Exercise authentication on the restored database. Synthetic writes are
        # rolled back, and the whole isolated database volume is then removed.
        database='medtrack_restore_auth_'+uuid.uuid4().hex[:12]
        auth_code='''import json,uuid
from django.contrib.auth import get_user_model
from django.db import transaction
from patients.test_client import AuthVersionTestClient
User=get_user_model()
assert User.objects.filter(is_active=True,is_superuser=True).exists()
before=User.objects.count()
with transaction.atomic():
 name='macrestore_'+uuid.uuid4().hex
 password=uuid.uuid4().hex
 actor=User.objects.create_superuser(username=name,password=password)
 client=AuthVersionTestClient(HTTP_HOST='localhost',REMOTE_ADDR='127.0.0.92')
 assert client.login(username=name,password=password)
 client.force_login(actor)
 pages=['/patients/','/staff/directory/','/staff/reminders/','/staff/announcements/']
 for page in pages:
  assert client.get(page,secure=True).status_code==200
 existing=User.objects.filter(is_active=True,is_superuser=True).exclude(username=name).first()
 client.force_login(existing)
 assert client.get('/patients/',secure=True).status_code==200
 client.logout()
 assert client.get('/patients/',secure=True).status_code==302
 transaction.set_rollback(True)
assert User.objects.count()==before and not User.objects.filter(username=name).exists()
print('MAC_RESTORED_AUTHENTICATION_OK')
'''
        auth_script=prefix+compose+' exec -T db createdb --username="$POSTGRES_USER" '+database+'\n'
        auth_script+='age --decrypt -i '+shlex.quote(str(ROOT/'secrets/backup.agekey'))+' '+shlex.quote(downloaded['archive'])
        auth_script+=' | tar -xzOf - ./database.dump | '+compose+' exec -T db pg_restore --exit-on-error --no-owner --no-privileges --username="$POSTGRES_USER" --dbname='+database+'\n'
        auth_script+=compose+' run --rm --no-deps -T -e DATABASE_URL= -e POSTGRES_DB='+database+' web python manage.py shell <<\'MEDTRACK_AUTH_PY\'\n'+auth_code+'MEDTRACK_AUTH_PY\n'
        result=command(['/opt/homebrew/bin/bash','-c',auth_script],cwd=repo)
        if result.count('MAC_RESTORED_AUTHENTICATION_OK')!=1:raise ValueError('restored-authentication-failed')
        values['restored_authenticated_behavior']='PASS'
        values['synthetic_transaction_rolled_back']='true'
        print('MAC_RESTORED_AUTHENTICATION_OK')
        write_json(receipts/'nas-source.json',downloaded)
        write_json(ROOT/'receipts/latest-restore.json',{'completed_epoch':int(time.time()),'run_id':run_id,
                   'source_commit':production['commit'],'archive':Path(downloaded['archive']).name,
                   'sha256':downloaded['sha256'],'verification':values,'backup_source':backup_source,'origin':downloaded['source']})
    finally:
        command(['/opt/homebrew/bin/bash','-c',prefix+compose+' down\n'],capture=False,cwd=repo)
        volumes=command(['docker','volume','ls','-q','--filter','label=com.docker.compose.project='+project]).splitlines()
        for volume in volumes:
            owner=command(['docker','volume','inspect','--format','{{index .Labels "com.docker.compose.project"}}',volume]).strip()
            if owner!=project:raise ValueError('scratch-volume-ownership-mismatch')
            command(['docker','volume','rm',volume])
        shutil.rmtree(work)
    evidence()
    print('MEDTRACK_MAC_RESTORE_OK')


def catalog_environment(configuration):
    catalog=ROOT/'secrets/retained-integrity.json'
    pin=configuration.get('legacy_catalog_sha256')
    if pin is None and not catalog.exists():return {}
    if (not isinstance(pin,str) or not re.fullmatch('[a-f0-9]{64}',pin) or
        catalog.is_symlink() or not catalog.is_file() or catalog.stat().st_uid!=os.getuid() or
        catalog.stat().st_mode & 0o077 or not 0<catalog.stat().st_size<=2*1024**2):
        raise ValueError('private-catalog-and-independent-pin-required')
    return {'MEDTRACK_LEGACY_CATALOG':str(catalog),'MEDTRACK_LEGACY_CATALOG_SHA256':pin}


def health(full=False):
    # Never let an older successful receipt hide a later failed or interrupted run.
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from scheduler import current
    if not current(ROOT/'state','restore')['healthy']:
        raise ValueError('latest-restore-attempt-not-successful')
    production=status()
    configuration=settings()
    repo=source(configuration.get('operations_commit',production['commit']))
    hook=ROOT/'bin/evidence-check'
    hook.write_text('#!/bin/sh\nexec /opt/homebrew/bin/python3.12 '+shlex.quote(str(Path(__file__).resolve()))+' evidence\n');hook.chmod(0o700)
    env={'MEDTRACK_BACKUP_CONFIG':'/nonexistent/medtrack-mac','RCLONE_CONFIG':str(ROOT/'secrets/rclone.conf'),
         'RCLONE_REMOTE':'medtrack-drive:Naveen-Hospital-Backups/MEDTRACK/production',
         'MEDTRACK_HEALTH_PRODUCTION_MODE':'1','MEDTRACK_HEALTH_HASH_MODE':'all' if full else 'incremental',
         'MEDTRACK_HEALTH_STATE_ROOT':str(ROOT/'state/health-cache'),
         'MEDTRACK_SCRATCH_RESTORE_RECEIPT':str(ROOT/'state/scratch-restore.receipt'),
         'MEDTRACK_SECURITY_EVIDENCE_HEALTH_HOOK':str(hook)}
    env.update(catalog_environment(configuration))
    command(['/opt/homebrew/bin/bash',str(repo/'scripts/check-offsite-backups.sh')],capture=False,env=env,timeout=7200)
    print('MEDTRACK_MAC_HEALTH_OK')


def main():
    os.umask(0o077)
    def cancelled(signum,frame):
        raise InterruptedError('recovery-cancelled')
    signal.signal(signal.SIGTERM,cancelled)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('access','restore','health','scrub','evidence'))
    p.add_argument('--archive');p.add_argument('--tier',choices=TIERS)
    p.add_argument('--backup-source',choices=('nas','drive'),default='nas');args=p.parse_args()
    if args.action=='access':
        print(json.dumps(status()));command(ssh_args('authenticated-check'),capture=False,timeout=120)
    elif args.action=='restore':restore(args.archive,args.tier,args.backup_source)
    elif args.action=='evidence':evidence()
    else:health(args.action=='scrub')


if __name__=='__main__':
    try:main()
    except Exception as error:
        # Keep raw command output and exceptions out of notifications/transcripts.
        import traceback
        print(json.dumps({'error':'MEDTRACK_MAC_RECOVERY_FAILED','type':type(error).__name__,
                          'line':traceback.extract_tb(error.__traceback__)[-1].lineno,
                          'reason':str(error) if isinstance(error,(ValueError,RuntimeError)) else 'private-diagnostic-withheld'}),file=sys.stderr)
        sys.exit(1)
