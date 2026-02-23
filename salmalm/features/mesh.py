"""SalmAlm Mesh — peer-to-peer networking between SalmAlm instances.

OpenClaw's "Node pairing" adapted for SalmAlm's pip-install philosophy:
Instead of mobile device pairing (camera/GPS/screen), SalmAlm peers are
other SalmAlm instances on the network (your laptop, server, VPS, Pi).

Features:
- Auto-discovery via mDNS/UDP broadcast (LAN)
- Manual peer registration (WAN)
- Remote task delegation (send a task to a peer)
- Shared clipboard / file transfer
- Health monitoring across peers
- Token-based authentication

Protocol: HTTP API on each SalmAlm instance's existing server port.
"""

import hashlib
import json
import os
import socket
import threading
import time
import urllib.request
import urllib.error
from typing import Dict, List, Optional

from salmalm.security.crypto import log
from salmalm.constants import DATA_DIR, VERSION

_MESH_FILE = DATA_DIR / "mesh_peers.json"
_MESH_SECRET = os.environ.get("SALMALM_MESH_SECRET", "")


class MeshPeer:
    """Represents a remote SalmAlm instance."""

    def __init__(self, peer_id: str, url: str, name: str = "", secret: str = "") -> None:
        """Init  ."""
        self.peer_id = peer_id
        self.url = url.rstrip("/")
        self.name = name or peer_id
        self.secret = secret or _MESH_SECRET
        self.last_seen = 0.0
        self.status = "unknown"  # unknown, online, offline, error
        self.version = ""
        self.capabilities: list = []

    def _auth_header(self) -> dict:
        """Generate auth header for peer requests."""
        if not self.secret:
            return {}
        ts = str(int(time.time()))
        sig = hashlib.sha256(f"{self.secret}:{ts}".encode()).hexdigest()[:32]
        return {"X-Mesh-Auth": f"{ts}:{sig}"}

    def ping(self) -> bool:
        """Check if peer is alive."""
        try:
            req = urllib.request.Request(
                f"{self.url}/api/mesh/ping",
                headers={**self._auth_header(), "User-Agent": f"SalmAlm-Mesh/{VERSION}"},
                method="GET",
            )
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read().decode())
            self.status = "online"
            self.last_seen = time.time()
            self.version = data.get("version", "")
            self.capabilities = data.get("capabilities", [])
            return True
        except Exception as e:  # noqa: broad-except
            self.status = "offline"
            return False

    def send_task(self, task: str, model: Optional[str] = None) -> dict:
        """Delegate a task to this peer."""
        try:
            payload = json.dumps(
                {
                    "task": task,
                    "model": model,
                    "from": socket.gethostname(),
                }
            ).encode()
            req = urllib.request.Request(
                f"{self.url}/api/mesh/task",
                data=payload,
                headers={
                    **self._auth_header(),
                    "Content-Type": "application/json",
                    "User-Agent": f"SalmAlm-Mesh/{VERSION}",
                },
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=60)
            return json.loads(resp.read().decode())
        except Exception as e:
            return {"error": str(e)}

    def send_clipboard(self, text: str) -> dict:
        """Share clipboard content with peer."""
        try:
            payload = json.dumps({"text": text}).encode()
            req = urllib.request.Request(
                f"{self.url}/api/mesh/clipboard",
                data=payload,
                headers={
                    **self._auth_header(),
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=10)
            return json.loads(resp.read().decode())
        except Exception as e:
            return {"error": str(e)}

    def get_status(self) -> dict:
        """Get detailed status from peer."""
        try:
            req = urllib.request.Request(
                f"{self.url}/api/mesh/status",
                headers={**self._auth_header()},
                method="GET",
            )
            resp = urllib.request.urlopen(req, timeout=10)
            return json.loads(resp.read().decode())
        except Exception as e:
            return {"error": str(e), "status": "offline"}

    def to_dict(self) -> dict:
        """To dict."""
        return {
            "peer_id": self.peer_id,
            "url": self.url,
            "name": self.name,
            "status": self.status,
            "version": self.version,
            "last_seen": self.last_seen,
            "capabilities": self.capabilities,
        }


class MeshManager:
    """Manages peer-to-peer SalmAlm mesh network."""

    _DISCOVERY_PORT = 18805
    _MAX_PEERS = 20

    def __init__(self) -> None:
        """Init  ."""
        self._peers: Dict[str, MeshPeer] = {}
        self._lock = threading.Lock()
        self._clipboard: str = ""
        self._clipboard_ts: float = 0
        self._load()

    def _load(self):
        """Load peers from config file."""
        try:
            if _MESH_FILE.exists():
                data = json.loads(_MESH_FILE.read_text(encoding="utf-8"))
                for p in data.get("peers", []):
                    peer = MeshPeer(p["peer_id"], p["url"], p.get("name", ""), p.get("secret", ""))
                    self._peers[peer.peer_id] = peer
        except Exception as e:
            log.warning(f"[MESH] Load error: {e}")

    def _save(self):
        """Save peers to config file."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "peers": [
                    {"peer_id": p.peer_id, "url": p.url, "name": p.name, "secret": p.secret}
                    for p in self._peers.values()
                ]
            }
            _MESH_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning(f"[MESH] Save error: {e}")

    def add_peer(self, url: str, name: str = "", secret: str = "") -> str:
        """Add a peer by URL. Returns status message."""
        url = url.rstrip("/")
        peer_id = hashlib.md5(url.encode()).hexdigest()[:8]

        with self._lock:
            if len(self._peers) >= self._MAX_PEERS:
                return "❌ Max peers reached (20)"

            peer = MeshPeer(peer_id, url, name or url, secret)
            online = peer.ping()
            self._peers[peer_id] = peer
            self._save()

            status = "🟢 online" if online else "🔴 offline"
            ver = f" (v{peer.version})" if peer.version else ""
            return f"📡 Peer added: {peer.name} [{peer_id}] — {status}{ver}"

    def remove_peer(self, peer_id: str) -> str:
        """Remove a peer."""
        with self._lock:
            if peer_id in self._peers:
                name = self._peers[peer_id].name
                del self._peers[peer_id]
                self._save()
                return f"📡 Peer removed: {name}"
            return f"❌ Peer not found: {peer_id}"

    def list_peers(self) -> List[dict]:
        """List all peers with their status."""
        return [p.to_dict() for p in self._peers.values()]

    def ping_all(self) -> dict:
        """Ping all peers and return status."""
        results = {}
        for peer in self._peers.values():
            results[peer.peer_id] = {
                "name": peer.name,
                "online": peer.ping(),
                "version": peer.version,
            }
        return results

    def delegate_task(self, peer_id: str, task: str, model: Optional[str] = None) -> dict:
        """Send a task to a specific peer for execution."""
        peer = self._peers.get(peer_id)
        if not peer:
            return {"error": f"Peer {peer_id} not found"}
        return peer.send_task(task, model=model)

    def broadcast_task(self, task: str, model: Optional[str] = None) -> List[dict]:
        """Send task to all online peers (parallel execution)."""
        results = []
        for peer in self._peers.values():
            if peer.status == "online":
                result = peer.send_task(task, model=model)
                results.append({"peer": peer.name, **result})
        return results

    def share_clipboard(self, text: str) -> dict:
        """Share clipboard with all online peers."""
        self._clipboard = text
        self._clipboard_ts = time.time()
        results = {}
        for peer in self._peers.values():
            if peer.status == "online":
                results[peer.name] = peer.send_clipboard(text)
        return results

    def get_clipboard(self) -> dict:
        """Get the latest shared clipboard content."""
        return {"text": self._clipboard, "timestamp": self._clipboard_ts}

    def set_clipboard(self, text: str) -> None:
        """Set clipboard (called when receiving from a peer)."""
        self._clipboard = text
        self._clipboard_ts = time.time()

    # ── API handlers (mounted on the existing web server) ──

    def handle_ping(self) -> dict:
        """Handle /api/mesh/ping — return this instance's info."""
        from salmalm.tools import TOOL_DEFINITIONS

        return {
            "version": VERSION,
            "hostname": socket.gethostname(),
            "capabilities": ["task", "clipboard", "status"],
            "tools": len(TOOL_DEFINITIONS),
            "timestamp": time.time(),
        }

    def handle_task(self, data: dict) -> dict:
        """Handle /api/mesh/task — execute a delegated task."""
        task = data.get("task", "")
        model = data.get("model")
        from_host = data.get("from", "unknown")
        if not task:
            return {"error": "No task provided"}
        log.info(f"[MESH] Task from {from_host}: {task[:80]}")
        try:
            import asyncio
            from salmalm.core.engine import process_message

            result = asyncio.run(process_message(f"mesh-{from_host}", task, model_override=model))
            return {"result": result[:5000], "status": "completed"}
        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def handle_clipboard(self, data: dict) -> dict:
        """Handle /api/mesh/clipboard — receive shared clipboard."""
        text = data.get("text", "")
        self.set_clipboard(text)
        return {"ok": True, "length": len(text)}

    def handle_status(self) -> dict:
        """Handle /api/mesh/status — return detailed status."""
        from salmalm.core.core import _sessions, _metrics

        return {
            "version": VERSION,
            "hostname": socket.gethostname(),
            "sessions": len(_sessions),
            "uptime_s": time.time() - _metrics.get("start_time", time.time()),
            "peers": len(self._peers),
        }

    def discover_lan(self, timeout: float = 3.0) -> List[str]:
        """Discover SalmAlm instances on LAN via UDP broadcast.

        Sends a discovery packet and listens for responses.
        Returns list of discovered URLs.
        """
        discovered = []
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(timeout)

            # Send discovery packet
            msg = json.dumps({"type": "salmalm_discover", "version": VERSION}).encode()
            sock.sendto(msg, ("<broadcast>", self._DISCOVERY_PORT))

            # Listen for responses
            end_time = time.time() + timeout
            while time.time() < end_time:
                try:
                    data, addr = sock.recvfrom(1024)
                    resp = json.loads(data.decode())
                    if resp.get("type") == "salmalm_announce":
                        url = f"http://{addr[0]}:{resp.get('port', 18800)}"
                        if url not in discovered:
                            discovered.append(url)
                except socket.timeout:
                    break
                except Exception as e:  # noqa: broad-except
                    log.debug(f"Suppressed: {e}")
            sock.close()
        except Exception as e:
            log.warning(f"[MESH] Discovery error: {e}")

        return discovered


# Singleton
mesh_manager = MeshManager()
