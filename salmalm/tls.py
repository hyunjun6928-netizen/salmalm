from __future__ import annotations
"""삶앎 TLS — Self-signed certificate generation + HTTPS server wrapper.

Pure stdlib (ssl module). Generates self-signed certs on first run.
Production: replace with Let's Encrypt or reverse proxy (nginx/caddy).

Usage:
  from salmalm.tls import create_https_server, ensure_cert
  ensure_cert()  # Generate self-signed cert if missing
  server = create_https_server(('0.0.0.0', 443), handler)
"""


import os
import ssl
import subprocess
import http.server
from pathlib import Path
from typing import Optional

from .constants import BASE_DIR
from .crypto import log

CERT_DIR = BASE_DIR / "certs"
CERT_FILE = CERT_DIR / "server.crt"
KEY_FILE = CERT_DIR / "server.key"


def ensure_cert(cn: str = "localhost", days: int = 365) -> bool:
    """Generate self-signed certificate if not exists. Returns True if cert exists."""
    if CERT_FILE.exists() and KEY_FILE.exists():
        return True

    CERT_DIR.mkdir(exist_ok=True)

    # Try OpenSSL first
    try:
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(KEY_FILE), "-out", str(CERT_FILE),
            "-days", str(days), "-nodes",
            "-subj", f"/CN={cn}/O=SalmAlm/C=KR",
            "-addext", f"subjectAltName=DNS:{cn},DNS:localhost,IP:127.0.0.1",
        ], capture_output=True, check=True, timeout=30)
        os.chmod(str(KEY_FILE), 0o600)
        log.info(f"🔒 Self-signed certificate generated: {CERT_FILE}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Fallback: try Python ssl (limited)
    try:
        # Python 3.10+ has ssl.create_default_context but no cert generation
        # Use subprocess with python -c as last resort
        script = f'''
import ssl, tempfile, subprocess, os
# Generate using openssl via python
subprocess.run(["openssl", "version"], capture_output=True, check=True)
'''
        log.warning("🔒 OpenSSL not available. TLS disabled.")
        log.warning("   Install OpenSSL or use a reverse proxy for HTTPS.")
        return False
    except Exception:
        return False


def create_ssl_context() -> Optional[ssl.SSLContext]:
    """Create SSL context with the server certificate."""
    if not CERT_FILE.exists() or not KEY_FILE.exists():
        return None

    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(CERT_FILE), str(KEY_FILE))
        # Security settings
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
        log.info("🔒 TLS context created (TLS 1.2+)")
        return ctx
    except Exception as e:
        log.error(f"TLS context error: {e}")
        return None


def create_https_server(address: tuple, handler_class,
                        ssl_context: ssl.SSLContext = None):
    """Create a ThreadingHTTPServer with optional TLS."""
    server = http.server.ThreadingHTTPServer(address, handler_class)

    if ssl_context is None:
        ssl_context = create_ssl_context()

    if ssl_context:
        server.socket = ssl_context.wrap_socket(
            server.socket, server_side=True
        )
        log.info(f"🔒 HTTPS server on {address[0]}:{address[1]}")
    else:
        log.info(f"🌐 HTTP server on {address[0]}:{address[1]} (no TLS)")

    return server


def get_cert_info() -> dict:
    """Get certificate info."""
    info = {
        "cert_exists": CERT_FILE.exists(),
        "key_exists": KEY_FILE.exists(),
        "cert_path": str(CERT_FILE),
    }
    if CERT_FILE.exists():
        try:
            result = subprocess.run(
                ["openssl", "x509", "-in", str(CERT_FILE), "-noout",
                 "-subject", "-dates", "-fingerprint"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    if line.startswith("subject="):
                        info["subject"] = line[8:]
                    elif line.startswith("notBefore="):
                        info["not_before"] = line[10:]
                    elif line.startswith("notAfter="):
                        info["not_after"] = line[9:]
                    elif "Fingerprint" in line:
                        info["fingerprint"] = line.split("=", 1)[1] if "=" in line else line
        except Exception:
            pass
        info["size_bytes"] = CERT_FILE.stat().st_size
    return info
