from __future__ import annotations
"""SalmAlm Node Control — lightweight remote agent management.

Manages remote machines via SSH (subprocess) or HTTP agent protocol.
Simpler than OpenClaw's node system but covers core use cases:
  - Execute commands on remote machines
  - Transfer files
  - Monitor system status (CPU, memory, disk)
  - Screen capture (via SSH + scrot/screencapture)
  - Wake-on-LAN

Nodes are configured in nodes.json:
{
  "home-server": {
    "type": "ssh",
    "host": "192.168.1.100",
    "user": "admin",
    "port": 22,
    "key": "~/.ssh/id_rsa"
  },
  "work-pc": {
    "type": "http",
    "url": "http://192.168.1.50:18810",
    "token": "secret123"
  }
}
"""


import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from .constants import BASE_DIR
from .crypto import log

NODES_CONFIG = BASE_DIR / "nodes.json"


class SSHNode:
    """Remote node accessible via SSH."""

    def __init__(self, name: str, host: str, user: str = "root",
                 port: int = 22, key: str = None):
        self.name = name
        self.host = host
        self.user = user
        self.port = port
        self.key = key
        self._last_status = None
        self._last_check = 0

    def _ssh_cmd(self, command: str, timeout: int = 30) -> tuple:
        """Execute SSH command, return (stdout, stderr, returncode)."""
        # StrictHostKeyChecking=accept-new: trust on first use, reject changes (TOFU)
        args = ["ssh", "-o", "StrictHostKeyChecking=accept-new",
                "-o", "ConnectTimeout=10",
                "-p", str(self.port)]
        if self.key:
            key_path = os.path.expanduser(self.key)
            args.extend(["-i", key_path])
        args.append(f"{self.user}@{self.host}")
        args.append(command)

        try:
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=timeout
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", "Timeout", -1
        except Exception as e:
            return "", str(e), -1

    def run(self, command: str, timeout: int = 30) -> dict:
        """Execute command on remote node."""
        stdout, stderr, code = self._ssh_cmd(command, timeout)
        return {
            "node": self.name,
            "command": command,
            "stdout": stdout[:10000],
            "stderr": stderr[:2000],
            "exit_code": code,
            "success": code == 0,
        }

    def status(self) -> dict:
        """Get node system status (CPU, memory, disk, uptime)."""
        now = time.time()
        if self._last_status and now - self._last_check < 60:
            return self._last_status

        cmd = """echo "===CPU===" && top -bn1 | head -5 && echo "===MEM===" && free -h && echo "===DISK===" && df -h / && echo "===UPTIME===" && uptime"""
        stdout, stderr, code = self._ssh_cmd(cmd, timeout=15)

        if code != 0:
            return {"node": self.name, "status": "unreachable",
                    "error": stderr[:200]}

        self._last_status = {
            "node": self.name,
            "status": "online",
            "raw": stdout[:3000],
            "checked_at": time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        self._last_check = now

        # Parse key metrics
        try:
            for line in stdout.splitlines():
                if "Mem:" in line:
                    parts = line.split()
                    self._last_status["memory"] = {
                        "total": parts[1] if len(parts) > 1 else "?",
                        "used": parts[2] if len(parts) > 2 else "?",
                    }
                if line.strip().startswith("/"):
                    parts = line.split()
                    if len(parts) >= 5:
                        self._last_status["disk"] = {
                            "total": parts[1], "used": parts[2],
                            "avail": parts[3], "pct": parts[4],
                        }
                if "load average" in line:
                    load = line.split("load average:")[-1].strip()
                    self._last_status["load"] = load
        except Exception:
            pass

        return self._last_status

    def upload(self, local_path: str, remote_path: str) -> dict:
        """Upload file via SCP."""
        args = ["scp", "-o", "StrictHostKeyChecking=accept-new",
                "-P", str(self.port)]
        if self.key:
            args.extend(["-i", os.path.expanduser(self.key)])
        args.extend([local_path, f"{self.user}@{self.host}:{remote_path}"])

        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=120)
            return {"success": result.returncode == 0,
                    "error": result.stderr[:200] if result.returncode != 0 else ""}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def download(self, remote_path: str, local_path: str) -> dict:
        """Download file via SCP."""
        args = ["scp", "-o", "StrictHostKeyChecking=accept-new",
                "-P", str(self.port)]
        if self.key:
            args.extend(["-i", os.path.expanduser(self.key)])
        args.extend([f"{self.user}@{self.host}:{remote_path}", local_path])

        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=120)
            return {"success": result.returncode == 0,
                    "error": result.stderr[:200] if result.returncode != 0 else ""}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def is_reachable(self) -> bool:
        """Quick ping check."""
        _, _, code = self._ssh_cmd("echo ok", timeout=10)
        return code == 0


class HTTPNode:
    """Remote node accessible via HTTP agent protocol."""

    def __init__(self, name: str, url: str, token: str = ""):
        self.name = name
        self.url = url.rstrip('/')
        self.token = token

    def _request(self, path: str, method: str = "GET",
                 data: dict = None, timeout: int = 30) -> dict:
        """Make HTTP request to node agent."""
        full_url = f"{self.url}{path}"
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(full_url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception as e:
            return {"error": str(e)}

    def run(self, command: str, timeout: int = 30) -> dict:
        result = self._request("/exec", "POST",
                               {"command": command, "timeout": timeout},
                               timeout=timeout + 5)
        result["node"] = self.name
        return result

    def status(self) -> dict:
        result = self._request("/status")
        result["node"] = self.name
        return result

    def upload(self, local_path: str, remote_path: str) -> dict:
        """Upload via HTTP (base64 in JSON — for small files)."""
        try:
            with open(local_path, 'rb') as f:
                data = f.read()
            if len(data) > 50 * 1024 * 1024:
                return {"success": False, "error": "File too large (>50MB)"}
            import base64
            result = self._request("/upload", "POST", {
                "path": remote_path,
                "data": base64.b64encode(data).decode(),
                "size": len(data),
            }, timeout=60)
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def is_reachable(self) -> bool:
        result = self._request("/ping", timeout=5)
        return "error" not in result


class NodeManager:
    """Manages all remote nodes."""

    def __init__(self):
        self._nodes: Dict[str, object] = {}

    def load_config(self):
        """Load nodes from nodes.json."""
        if not NODES_CONFIG.exists():
            return
        try:
            config = json.loads(NODES_CONFIG.read_text(encoding='utf-8'))
            for name, cfg in config.items():
                node_type = cfg.get("type", "ssh")
                if node_type == "ssh":
                    self._nodes[name] = SSHNode(
                        name, cfg["host"],
                        user=cfg.get("user", "root"),
                        port=cfg.get("port", 22),
                        key=cfg.get("key"),
                    )
                elif node_type == "http":
                    self._nodes[name] = HTTPNode(
                        name, cfg["url"],
                        token=cfg.get("token", ""),
                    )
            if self._nodes:
                log.info(f"📡 Loaded {len(self._nodes)} nodes")
        except Exception as e:
            log.error(f"Node config error: {e}")

    def save_config(self):
        """Save node configs to JSON."""
        config = {}
        for name, node in self._nodes.items():
            if isinstance(node, SSHNode):
                config[name] = {
                    "type": "ssh", "host": node.host,
                    "user": node.user, "port": node.port,
                    "key": node.key,
                }
            elif isinstance(node, HTTPNode):
                config[name] = {
                    "type": "http", "url": node.url,
                    "token": node.token,
                }
        NODES_CONFIG.write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding='utf-8')

    def add_ssh_node(self, name: str, host: str, user: str = "root",
                     port: int = 22, key: str = None) -> bool:
        """Add an SSH node."""
        node = SSHNode(name, host, user, port, key)
        self._nodes[name] = node
        self.save_config()
        log.info(f"📡 Added SSH node: {name} ({user}@{host}:{port})")
        return True

    def add_http_node(self, name: str, url: str, token: str = "") -> bool:
        """Add an HTTP agent node."""
        node = HTTPNode(name, url, token)
        self._nodes[name] = node
        self.save_config()
        log.info(f"📡 Added HTTP node: {name} ({url})")
        return True

    def remove_node(self, name: str) -> bool:
        if name in self._nodes:
            del self._nodes[name]
            self.save_config()
            return True
        return False

    def get_node(self, name: str):
        return self._nodes.get(name)

    def list_nodes(self) -> List[dict]:
        """List all nodes with basic status."""
        result = []
        for name, node in self._nodes.items():
            info = {
                "name": name,
                "type": "ssh" if isinstance(node, SSHNode) else "http",
            }
            if isinstance(node, SSHNode):
                info["host"] = f"{node.user}@{node.host}:{node.port}"
            elif isinstance(node, HTTPNode):
                info["url"] = node.url
            result.append(info)
        return result

    def run_on(self, name: str, command: str, timeout: int = 30) -> dict:
        """Execute command on a specific node."""
        node = self._nodes.get(name)
        if not node:
            return {"error": f"Node not found: {name}"}
        return node.run(command, timeout)

    def status_all(self) -> List[dict]:
        """Get status of all nodes."""
        results = []
        for name, node in self._nodes.items():
            try:
                results.append(node.status())
            except Exception as e:
                results.append({"node": name, "status": "error", "error": str(e)})
        return results

    def wake_on_lan(self, mac_address: str, broadcast: str = "255.255.255.255",
                    port: int = 9) -> dict:
        """Send Wake-on-LAN magic packet."""
        import socket
        try:
            mac = mac_address.replace(":", "").replace("-", "")
            if len(mac) != 12:
                return {"error": "Invalid MAC address"}
            magic = b'\xff' * 6 + bytes.fromhex(mac) * 16
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(magic, (broadcast, port))
            sock.close()
            return {"success": True, "mac": mac_address}
        except Exception as e:
            return {"error": str(e)}


# Module-level instance
node_manager = NodeManager()
