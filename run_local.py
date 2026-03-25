#!/usr/bin/env python3
import os
import sys
import time
import signal
import subprocess


ROOT = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable
FRONTEND_PORT = "3000"


def _start_backend() -> subprocess.Popen:
    backend_dir = os.path.join(ROOT, "Backend")
    return subprocess.Popen([PYTHON, "main.py"], cwd=backend_dir)


def _start_frontend() -> subprocess.Popen:
    frontend_dir = os.path.join(ROOT, "Frontend")
    return subprocess.Popen([PYTHON, "-m", "http.server", FRONTEND_PORT], cwd=frontend_dir)


def _terminate(proc: subprocess.Popen, name: str) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
    except Exception:
        return


def main() -> int:
    backend = _start_backend()
    frontend = _start_frontend()

    print("Backend running at http://localhost:8080")
    print(f"Frontend running at http://localhost:{FRONTEND_PORT}")
    print("Press Ctrl+C to stop both.")

    try:
        while True:
            backend_code = backend.poll()
            frontend_code = frontend.poll()

            if backend_code is not None:
                print(f"Backend exited with code {backend_code}. Shutting down frontend...")
                break
            if frontend_code is not None:
                print(f"Frontend exited with code {frontend_code}. Shutting down backend...")
                break

            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        _terminate(frontend, "frontend")
        _terminate(backend, "backend")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
