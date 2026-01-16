import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_server(url: str, timeout_s: float = 10.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            resp = requests.get(f"{url}/_dash-layout", timeout=2)
            if resp.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.2)
    return False


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    venv_python = repo_root / ".venv" / "bin" / "python"
    if not venv_python.exists():
        print(".venv not found; install dependencies first.")
        return 1

    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    env["HOST"] = "127.0.0.1"
    env["PORT"] = str(port)

    # Start server
    server_cmd = [str(venv_python), "run.py", "--config", "config/mock.yaml"]
    server_proc = subprocess.Popen(
        server_cmd,
        cwd=str(repo_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        if not _wait_for_server(base_url, timeout_s=12.0):
            print("Server failed to start.")
            if server_proc.stdout:
                print(server_proc.stdout.read())
            return 1

        # Run live tests
        env["DASH_TEST_URL"] = base_url
        test_cmd = [str(venv_python), "-m", "pytest", "-q", "-m", "live"]
        result = subprocess.run(test_cmd, cwd=str(repo_root), env=env)
        return result.returncode
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()


if __name__ == "__main__":
    sys.exit(main())

