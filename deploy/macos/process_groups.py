"""Bounded cleanup of process groups owned by one verifier invocation."""
import os
import signal
import subprocess
import time


def live(group):
    rows=subprocess.check_output(['/bin/ps','-axo','pid=,pgid=,stat='],text=True)
    return [int(parts[0]) for line in rows.splitlines() if len(parts:=line.split())>=3
            and parts[1]==str(group) and not parts[2].startswith('Z')]


def terminate(process,grace=5):
    if live(process.pid):
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
    try:process.wait(timeout=grace)
    except subprocess.TimeoutExpired:pass
    # Leader exit alone does not prove its descendants have exited. Darwin can
    # return EPERM when signaling an empty group, hence the live-member check.
    if live(process.pid):
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
    process.wait(timeout=5)
    deadline=time.monotonic()+5
    while live(process.pid):
        if time.monotonic()>deadline:raise RuntimeError('worker-group-did-not-stop')
        time.sleep(0.02)
