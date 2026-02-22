"""SalmAlm Agent-to-Agent Protocol — inter-instance communication."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from salmalm.security.crypto import log

_DATA_DIR = Path.home() / ".salmalm"
_PEERS_PATH = _DATA_DIR / "a2a_peers.json"
_INBOX_PATH = _DATA_DIR / "a2a_inbox.json"

PROTOCOL_VERSION = "salmalm-a2a-v1"

VALID_ACTIONS = frozenset(
    {
        "schedule_meeting",
        "share_document",
        "ask_question",
        "task_delegate",
    }
)


class A2AProtocol:
    """SalmAlm instance-to-instance negotiation protocol."""

    def __init__(self, instance_name: str = "SalmAlm", instance_id: Optional[str] = None) -> None:
        self.instance_name = instance_name
        self.instance_id = instance_id or uuid.uuid4().hex[:12]
        self.peers: Dict[str, Dict[str, Any]] = {}
        self.inbox: List[Dict[str, Any]] = []
        self._pending_approvals: Dict[str, Dict[str, Any]] = {}
        self._load()

    # ── Persistence ──────────────────────────────────────────

    def _load(self) -> None:
        try:
            if _PEERS_PATH.exists():
                self.peers = json.loads(_PEERS_PATH.read_text("utf-8"))
            if _INBOX_PATH.exists():
                self.inbox = json.loads(_INBOX_PATH.read_text("utf-8"))
        except Exception as exc:
            log.warning("a2a: load error: %s", exc)

    def _save_peers(self) -> None:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _PEERS_PATH.write_text(json.dumps(self.peers, ensure_ascii=False, indent=2), "utf-8")

    def _save_inbox(self) -> None:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _INBOX_PATH.write_text(json.dumps(self.inbox, ensure_ascii=False, indent=2), "utf-8")

    # ── Signing ──────────────────────────────────────────────

    @staticmethod
    def sign(payload: dict, secret: str) -> str:
        """HMAC-SHA256 signature over canonical JSON."""
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()

    @staticmethod
    def verify(payload: dict, signature: str, secret: str) -> bool:
        expected = A2AProtocol.sign(payload, secret)
        return hmac.compare_digest(expected, signature)

    # ── Peering ──────────────────────────────────────────────

    def pair(self, url: str, shared_secret: str, peer_name: str = "") -> str:
        """Register a peer instance."""
        peer_id = uuid.uuid4().hex[:8]
        self.peers[peer_id] = {
            "url": url.rstrip("/"),
            "secret": shared_secret,
            "name": peer_name or url,
            "paired_at": time.time(),
        }
        self._save_peers()
        return peer_id

    def unpair(self, peer_id: str) -> bool:
        if peer_id in self.peers:
            del self.peers[peer_id]
            self._save_peers()
            return True
        return False

    def list_peers(self) -> List[Dict[str, Any]]:
        return [{"id": pid, "name": p.get("name", ""), "url": p["url"]} for pid, p in self.peers.items()]

    # ── Sending ──────────────────────────────────────────────

    def build_request(self, action: str, params: dict) -> dict:
        """Build an unsigned A2A request payload."""
        if action not in VALID_ACTIONS:
            raise ValueError(f"Invalid action: {action}. Must be one of {VALID_ACTIONS}")
        return {
            "protocol": PROTOCOL_VERSION,
            "from": {
                "name": self.instance_name,
                "instance_id": self.instance_id,
            },
            "action": action,
            "params": params,
            "timestamp": time.time(),
            "request_id": uuid.uuid4().hex,
        }

    def send(self, peer_id: str, action: str, params: dict, timeout: int = 30) -> Dict[str, Any]:
        """Send an A2A request to a paired peer. Returns the response dict."""
        peer = self.peers.get(peer_id)
        if not peer:
            return {"error": f"Unknown peer: {peer_id}"}

        payload = self.build_request(action, params)
        signature = self.sign(payload, peer["secret"])
        body = {**payload, "signature": signature}

        url = f"{peer['url']}/api/a2a/negotiate"
        data = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "SalmAlm-A2A/1.0"}
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            log.error("a2a send error: %s", exc)
            return {"error": str(exc)}

    # ── Receiving ────────────────────────────────────────────

    def receive(self, body: dict) -> Dict[str, Any]:
        """Process an incoming A2A request. Returns response dict."""
        protocol = body.get("protocol")
        if protocol != PROTOCOL_VERSION:
            return {"status": "error", "message": f"Unsupported protocol: {protocol}"}

        signature = body.pop("signature", "")
        _sender_id = body.get("from", {}).get("instance_id", "")  # noqa: F841

        # Find matching peer by instance_id or try all secrets
        peer_secret = None
        for pid, p in self.peers.items():
            if self.verify(body, signature, p["secret"]):
                peer_secret = p["secret"]
                break

        if not peer_secret:
            return {"status": "error", "message": "Invalid signature or unknown peer"}

        action = body.get("action")
        if action not in VALID_ACTIONS:
            return {"status": "error", "message": f"Unknown action: {action}"}

        # Queue for human approval
        request_id = body.get("request_id", uuid.uuid4().hex)
        entry = {
            "request_id": request_id,
            "from": body.get("from", {}),
            "action": action,
            "params": body.get("params", {}),
            "received_at": time.time(),
            "status": "pending",
        }
        self.inbox.append(entry)
        self._save_inbox()

        return {
            "status": "received",
            "request_id": request_id,
            "requires_human_approval": True,
        }

    def approve(self, request_id: str) -> Dict[str, Any]:
        """Approve a pending inbox request."""
        for item in self.inbox:
            if item.get("request_id") == request_id and item.get("status") == "pending":
                item["status"] = "approved"
                item["approved_at"] = time.time()
                self._save_inbox()
                return {"status": "approved", "request_id": request_id}
        return {"status": "error", "message": "Request not found or already processed"}

    def reject(self, request_id: str) -> Dict[str, Any]:
        """Reject a pending inbox request."""
        for item in self.inbox:
            if item.get("request_id") == request_id and item.get("status") == "pending":
                item["status"] = "rejected"
                item["rejected_at"] = time.time()
                self._save_inbox()
                return {"status": "rejected", "request_id": request_id}
        return {"status": "error", "message": "Request not found or already processed"}

    def get_inbox(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if status:
            return [i for i in self.inbox if i.get("status") == status]
        return list(self.inbox)

    # ── Web endpoint helpers ─────────────────────────────────

    def handle_negotiate_endpoint(self, body: dict) -> Dict[str, Any]:
        """Handler for POST /api/a2a/negotiate."""
        return self.receive(body)

    def handle_peers_endpoint(self) -> List[Dict[str, Any]]:
        """Handler for GET /api/a2a/peers."""
        return self.list_peers()

    def handle_pair_endpoint(self, body: dict) -> Dict[str, Any]:
        """Handler for POST /api/a2a/pair."""
        url = body.get("url", "")
        secret = body.get("secret", "")
        name = body.get("name", "")
        if not url or not secret:
            return {"error": "url and secret are required"}
        peer_id = self.pair(url, secret, name)
        return {"status": "paired", "peer_id": peer_id}

    # ── Command handling ─────────────────────────────────────

    def handle_command(self, args: str) -> str:
        """Handle /a2a subcommands."""
        parts = args.strip().split(maxsplit=3)
        sub = parts[0].lower() if parts else ""

        if sub == "pair":
            if len(parts) < 3:
                return "사용법: `/a2a pair <url> <secret>`"
            url, secret = parts[1], parts[2]
            pid = self.pair(url, secret)
            return f"✅ 페어링 완료 — peer_id: {pid}"

        if sub == "list":
            peers = self.list_peers()
            if not peers:
                return "페어링된 인스턴스가 없습니다."
            lines = [f"• {p['id']}: {p['name']} ({p['url']})" for p in peers]
            return "\n".join(lines)

        if sub == "send":
            if len(parts) < 4:
                return "사용법: `/a2a send <peer> <action> <params_json>`"
            peer_id, action = parts[1], parts[2]
            try:
                params = json.loads(parts[3]) if len(parts) > 3 else {}
            except json.JSONDecodeError:
                return "❌ params가 올바른 JSON이 아닙니다."
            result = self.send(peer_id, action, params)
            return json.dumps(result, ensure_ascii=False, indent=2)

        if sub == "inbox":
            items = self.get_inbox("pending")
            if not items:
                return "수신함이 비어있습니다."
            lines = []
            for item in items:
                lines.append(
                    f"• [{item['request_id'][:8]}] {item['action']} from {item.get('from', {}).get('name', '?')}"
                )
            return "\n".join(lines)

        if sub == "approve":
            if len(parts) < 2:
                return "사용법: `/a2a approve <request_id>`"
            result = self.approve(parts[1])
            return "✅ 승인됨" if result.get("status") == "approved" else result.get("message", "오류")

        if sub == "reject":
            if len(parts) < 2:
                return "사용법: `/a2a reject <request_id>`"
            result = self.reject(parts[1])
            return "❌ 거부됨" if result.get("status") == "rejected" else result.get("message", "오류")

        if sub == "unpair":
            if len(parts) < 2:
                return "사용법: `/a2a unpair <peer_id>`"
            ok = self.unpair(parts[1])
            return "페어링 해제됨" if ok else "해당 peer를 찾을 수 없습니다."

        return (
            "사용법:\n"
            "  /a2a pair <url> <secret>\n"
            "  /a2a list\n"
            "  /a2a send <peer> <action> <params_json>\n"
            "  /a2a inbox\n"
            "  /a2a approve <id>\n"
            "  /a2a reject <id>\n"
            "  /a2a unpair <peer>"
        )
