"""Run the API with uvicorn's own Server header suppressed.

uvicorn appends `Server: uvicorn` at the transport layer (after the ASGI app), which
would collide with the decoy Server header injected by RequestContextMiddleware. Launch
the app through this entrypoint (or pass `--no-server-header` to the uvicorn CLI) so the
decoy is the only Server header a client sees.

    python run.py            # production-style
    python run.py --reload   # dev
"""
from __future__ import annotations

import sys

import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload="--reload" in sys.argv,
        server_header=False,   # suppress `Server: uvicorn`; decoy is added by middleware
        date_header=True,      # a Date header is normal and not a fingerprint
        log_config=None,       # keep our structured logging (configure_logging)
        proxy_headers=True,
        forwarded_allow_ips="*" if settings.app_env != "production" else None,
    )
