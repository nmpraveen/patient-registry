#!/usr/bin/env python3
"""Pass a bounded scheduler alert to the owner's Keychain-backed skill helper."""
import errno
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import termios
import time


def deliver(payload):
    if set(payload)!={'title','message','idempotency_key'}:
        raise ValueError('invalid-alert-fields')
    if (not all(isinstance(v,str) for v in payload.values()) or
        len(payload['title'])>250 or len(payload['message'])>1000 or
        not payload['idempotency_key'].startswith('medtrack-mac-')):
        raise ValueError('invalid-alert')
    skill=Path.home()/'.codex/skills/pushover-notify'
    master,slave=os.openpty()
    previous=termios.tcgetattr(slave)
    quiet=termios.tcgetattr(slave);quiet[3]&=~termios.ECHO
    termios.tcsetattr(slave,termios.TCSANOW,quiet)
    process=None
    try:
        process=subprocess.Popen(['/opt/homebrew/bin/node','scripts/pushover.mjs','send'],
            cwd=skill,stdin=slave,stdout=slave,stderr=slave,
            env={'HOME':str(Path.home()),'PATH':'/opt/homebrew/bin:/usr/bin:/bin'})
        os.write(master,(json.dumps(payload)+'\n').encode())
        os.write(master,b'\x04')
        result=bytearray();deadline=time.monotonic()+35
        while process.poll() is None or select.select([master],[],[],0)[0]:
            if time.monotonic()>deadline:raise TimeoutError('alert-timeout')
            if select.select([master],[],[],0.2)[0]:
                try:data=os.read(master,4096)
                except OSError as error:
                    if error.errno==errno.EIO:break
                    raise
                if not data:break
                result.extend(data)
                if len(result)>16384:raise ValueError('invalid-helper-output')
        answer=json.loads(result.decode().strip())
        # Forward only the content-free delivery status.
        return {'status':answer.get('status','ambiguous')}
    except Exception:
        # A started provider request may have been accepted; never auto-retry it.
        return {'status':'ambiguous' if process is not None else 'failed'}
    finally:
        if process is not None and process.poll() is None:
            process.kill();process.wait()
        termios.tcsetattr(slave,termios.TCSANOW,previous)
        os.close(master);os.close(slave)


if __name__=='__main__':
    try:
        raw=sys.stdin.read(8193)
        if len(raw)>8192:raise ValueError('alert-size-limit')
        answer=deliver(json.loads(raw))
        print(json.dumps(answer))
        sys.exit(0 if answer['status'] in ('provider_accepted','duplicate') else 1)
    except Exception:
        print('{"status":"failed","code":"local-alert-helper-failed"}')
        sys.exit(1)
