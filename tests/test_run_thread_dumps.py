"""run.py: SIGUSR1 prints every thread's stack and the server keeps running."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not hasattr(signal, "SIGUSR1"), reason="no SIGUSR1 on this platform")
def test_sigusr1_prints_the_threads_and_the_process_carries_on():
    script = (
        f"import sys, time; sys.path.insert(0, {str(ROOT)!r}); import run; "
        "run.enable_thread_dumps(); print('ready', flush=True); time.sleep(60)"
    )
    proc = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "ready"
        os.kill(proc.pid, signal.SIGUSR1)
        time.sleep(0.5)
        # Without the handler SIGUSR1 would have ended the process.
        assert proc.poll() is None
    finally:
        proc.kill()
    _, err = proc.communicate()
    # The dump shows the main thread waiting in the script's sleep.
    assert "most recent call first" in err and '"<string>"' in err
