import os
import socket
import subprocess
import sys
from pathlib import Path

from app.config import get_config
from app.main import create_app


def find_free_port(preferred: int = 8050) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if s.connect_ex(("127.0.0.1", preferred)) != 0:
            return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def main():
    config = get_config()

    if config.get("reset_mock"):
        generator = Path(__file__).resolve().parent / "scripts" / "generate_mock_data.py"
        if generator.exists():
            result = subprocess.run([sys.executable, str(generator)])
            if result.returncode != 0:
                raise SystemExit("Mock data generation failed.")
        else:
            raise SystemExit(f"Mock data generator not found at {generator}")

    app = create_app(config)

    host = os.environ.get("HOST", "127.0.0.1")
    preferred_port = int(os.environ.get("PORT", "8050"))
    port = find_free_port(preferred_port)
    if port != preferred_port:
        print(f"Port {preferred_port} in use, switching to {port}")

    app.run(debug=False, host=host, port=port)


if __name__ == "__main__":
    main()
