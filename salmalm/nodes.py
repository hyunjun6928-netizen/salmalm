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
                 port: int = 22, key: Optional[str] = None):
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

        self._last_status = {  # type: ignore[assignment]
            "node": self.name,
            "status": "online",
            "raw": stdout[:3000],
            "checked_at": time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        self._last_check = now  # type: ignore[assignment]

        # Parse key metrics
        try:
            for line in stdout.splitlines():
                if "Mem:" in line:
                    parts = line.split()
                    self._last_status["memory"] = {  # type: ignore[index]
                        "total": parts[1] if len(parts) > 1 else "?",
                        "used": parts[2] if len(parts) > 2 else "?",
                    }
                if line.strip().startswith("/"):
                    parts = line.split()
                    if len(parts) >= 5:
                        self._last_status["disk"] = {  # type: ignore[index]
                            "total": parts[1], "used": parts[2],
                            "avail": parts[3], "pct": parts[4],
                        }
                if "load average" in line:
                    load = line.split("load average:")[-1].strip()
                    self._last_status["load"] = load  # type: ignore[index]
        except Exception:
            pass

        return self._last_status  # type: ignore[return-value]

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
        return code == 0  # type: ignore[no-any-return]


class HTTPNode:
    """Remote node accessible via HTTP agent protocol."""

    def __init__(self, name: str, url: str, token: str = ""):
        self.name = name
        self.url = url.rstrip('/')
        self.token = token

    def _request(self, path: str, method: str = "GET",
                 data: Optional[dict] = None, timeout: int = 30) -> dict:
        """Make HTTP request to node agent."""
        full_url = f"{self.url}{path}"
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(full_url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())  # type: ignore[no-any-return]
        except Exception as e:
            return {"error": str(e)}

    def run(self, command: str, timeout: int = 30) -> dict:
        """Execute a command on a remote node."""
        result = self._request("/exec", "POST",
                               {"command": command, "timeout": timeout},
                               timeout=timeout + 5)
        result["node"] = self.name
        return result

    def status(self) -> dict:
        """Get the status of a remote node."""
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
        """Check if a remote node is reachable."""
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
                log.info(f"[NET] Loaded {len(self._nodes)} nodes")
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
                     port: int = 22, key: Optional[str] = None) -> bool:
        """Add an SSH node."""
        node = SSHNode(name, host, user, port, key)
        self._nodes[name] = node
        self.save_config()
        log.info(f"[NET] Added SSH node: {name} ({user}@{host}:{port})")
        return True

    def add_http_node(self, name: str, url: str, token: str = "") -> bool:
        """Add an HTTP agent node."""
        node = HTTPNode(name, url, token)
        self._nodes[name] = node
        self.save_config()
        log.info(f"[NET] Added HTTP node: {name} ({url})")
        return True

    def remove_node(self, name: str) -> bool:
        """Remove a registered remote node."""
        if name in self._nodes:
            del self._nodes[name]
            self.save_config()
            return True
        return False

    def get_node(self, name: str):
        """Get configuration for a specific node."""
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
        return node.run(command, timeout)  # type: ignore[attr-defined, no-any-return]

    def status_all(self) -> List[dict]:
        """Get status of all nodes."""
        results = []
        for name, node in self._nodes.items():
            try:
                results.append(node.status())  # type: ignore[attr-defined]
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


# ============================================================
# Gateway-Node Protocol
# ============================================================
# Nodes register with the gateway. Gateway can dispatch tool calls to nodes.
# Node runs in --node mode: lightweight SalmAlm that only executes tools.
# Gateway keeps a registry and routes tool calls based on node capabilities.

class GatewayRegistry:
    """Gateway side: manages registered nodes that can execute tools remotely."""

    def __init__(self):
        self._nodes: Dict[str, dict] = {}  # node_id → {url, token, capabilities, last_heartbeat, status}

    def register(self, node_id: str, url: str, token: str = '',
                 capabilities: Optional[list] = None, name: str = '') -> dict:
        """Register a node with the gateway."""
        self._nodes[node_id] = {
            'id': node_id,
            'name': name or node_id,
            'url': url.rstrip('/'),
            'token': token,
            'capabilities': capabilities or ['exec', 'read_file', 'write_file', 'edit_file', 'web_search', 'web_fetch'],
            'last_heartbeat': time.time(),
            'status': 'online',
            'tool_calls': 0,
            'errors': 0,
        }
        log.info(f"[NET] Node registered: {node_id} ({url})")
        return {'ok': True, 'node_id': node_id}

    def heartbeat(self, node_id: str) -> dict:
        """Update node heartbeat timestamp."""
        node = self._nodes.get(node_id)
        if not node:
            return {'error': 'Node not registered'}
        node['last_heartbeat'] = time.time()
        node['status'] = 'online'
        return {'ok': True}

    def unregister(self, node_id: str) -> dict:
        """Remove a node."""
        if node_id in self._nodes:
            del self._nodes[node_id]
            log.info(f"[NET] Node unregistered: {node_id}")
            return {'ok': True}
        return {'error': 'Node not found'}

    def list_nodes(self) -> list:
        """List all registered nodes with status."""
        now = time.time()
        result = []
        for nid, node in self._nodes.items():
            age = now - node['last_heartbeat']
            if age > 120:
                node['status'] = 'offline'
            elif age > 60:
                node['status'] = 'stale'
            result.append({
                'id': nid,
                'name': node['name'],
                'url': node['url'],
                'status': node['status'],
                'capabilities': node['capabilities'],
                'tool_calls': node['tool_calls'],
                'errors': node['errors'],
                'last_seen': int(age),
            })
        return result

    def find_node(self, tool_name: str) -> Optional[dict]:
        """Find an online node that supports the given tool."""
        now = time.time()
        for nid, node in self._nodes.items():
            if (node['status'] == 'online'
                    and (now - node['last_heartbeat']) < 120
                    and tool_name in node['capabilities']):
                return node
        return None

    def dispatch(self, node_id: str, tool_name: str, tool_args: dict,
                 timeout: int = 60) -> dict:
        """Dispatch a tool call to a specific node."""
        node = self._nodes.get(node_id)
        if not node:
            return {'error': f'Node {node_id} not found'}

        url = f"{node['url']}/api/node/execute"
        headers = {'Content-Type': 'application/json'}
        if node['token']:
            headers['Authorization'] = f'Bearer {node["token"]}'

        payload = json.dumps({
            'tool': tool_name,
            'args': tool_args,
        }).encode()

        req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read())
                node['tool_calls'] += 1
                return result  # type: ignore[no-any-return]
        except Exception as e:
            node['errors'] += 1
            return {'error': f'Node dispatch failed: {str(e)[:200]}'}

    def dispatch_auto(self, tool_name: str, tool_args: dict,
                      timeout: int = 60) -> Optional[dict]:
        """Auto-find a node for this tool and dispatch. Returns None if no node available."""
        node = self.find_node(tool_name)
        if not node:
            return None
        return self.dispatch(node['id'], tool_name, tool_args, timeout)


class NodeAgent:
    """Node side: lightweight agent that receives and executes tool calls from gateway."""

    def __init__(self, gateway_url: str, node_id: str, token: str = '',
                 capabilities: Optional[list] = None, name: str = ''):
        self.gateway_url = gateway_url.rstrip('/')
        self.node_id = node_id
        self.token = token
        self.capabilities = capabilities or ['exec', 'read_file', 'write_file', 'edit_file', 'web_search', 'web_fetch']
        self.name = name or node_id
        self._heartbeat_thread = None
        self._running = False

    def register(self) -> dict:
        """Register this node with the gateway."""
        payload = json.dumps({
            'node_id': self.node_id,
            'url': f'http://{self._get_local_ip()}:18810',
            'token': self.token,
            'capabilities': self.capabilities,
            'name': self.name,
        }).encode()

        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        req = urllib.request.Request(
            f'{self.gateway_url}/api/gateway/register',
            data=payload, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                log.info(f"[NET] Registered with gateway: {self.gateway_url}")
                return result  # type: ignore[no-any-return]
        except Exception as e:
            log.error(f"[NET] Gateway registration failed: {e}")
            return {'error': str(e)}

    def _get_local_ip(self) -> str:
        """Get local IP for advertising to gateway."""
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip  # type: ignore[no-any-return]
        except Exception:
            return '127.0.0.1'

    def start_heartbeat(self, interval: int = 30):
        """Start background heartbeat to gateway."""
        self._running = True
        import threading

        def _beat():
            while self._running:
                try:
                    payload = json.dumps({'node_id': self.node_id}).encode()
                    headers = {'Content-Type': 'application/json'}
                    if self.token:
                        headers['Authorization'] = f'Bearer {self.token}'
                    req = urllib.request.Request(
                        f'{self.gateway_url}/api/gateway/heartbeat',
                        data=payload, headers=headers, method='POST')
                    urllib.request.urlopen(req, timeout=10)
                except Exception:
                    pass
                time.sleep(interval)

        self._heartbeat_thread = threading.Thread(target=_beat, daemon=True)  # type: ignore[assignment]
        self._heartbeat_thread.start()  # type: ignore[attr-defined]

    def stop(self):
        """Stop the node manager and close connections."""
        self._running = False


# Module-level instances
node_manager = NodeManager()
gateway = GatewayRegistry()
