"""
Production entry point: serve Django via Waitress.

Usage (manual):
    python run_waitress.py

Environment (see .env.example):
    WAITRESS_HOST   bind address (default 0.0.0.0)
    WAITRESS_PORT   listen port (default 8000)
    WAITRESS_THREADS worker threads (default 8)
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv

load_dotenv(BASE_DIR / ".env", override=True)

from waitress import serve  # noqa: E402

from config.wsgi import application  # noqa: E402


def main() -> None:
    host = os.getenv("WAITRESS_HOST", "0.0.0.0")
    port = int(os.getenv("WAITRESS_PORT", "8000"))
    threads = int(os.getenv("WAITRESS_THREADS", "8"))

    print(f"Starting Waitress on {host}:{port} ({threads} threads)", flush=True)
    serve(application, host=host, port=port, threads=threads)


if __name__ == "__main__":
    main()
