"""Tests for SalmAlm Agent-to-Agent Protocol."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from salmalm.features.a2a import A2AProtocol, PROTOCOL_VERSION, VALID_ACTIONS


@pytest.fixture
def a2a(tmp_path, monkeypatch):
    monkeypatch.setattr("salmalm.a2a._PEERS_PATH", tmp_path / "peers.json")
    monkeypatch.setattr("salmalm.a2a._INBOX_PATH", tmp_path / "inbox.json")
    monkeypatch.setattr("salmalm.a2a._DATA_DIR", tmp_path)
    return A2AProtocol(instance_name="TestBot", instance_id="test123")


def test_initial_state(a2a):
    assert a2a.instance_name == "TestBot"
    assert a2a.instance_id == "test123"
    assert a2a.peers == {}
    assert a2a.inbox == []


def test_pair_and_list(a2a):
    pid = a2a.pair("http://peer1.local", "secret123", "Peer1")
    peers = a2a.list_peers()
    assert len(peers) == 1
    assert peers[0]["name"] == "Peer1"
    assert peers[0]["url"] == "http://peer1.local"


def test_unpair(a2a):
    pid = a2a.pair("http://peer1.local", "secret123")
    assert a2a.unpair(pid) is True
    assert a2a.list_peers() == []
    assert a2a.unpair("nonexistent") is False


def test_sign_and_verify():
    payload = {"action": "test", "data": "hello"}
    sig = A2AProtocol.sign(payload, "mysecret")
    assert isinstance(sig, str)
    assert len(sig) == 64  # SHA256 hex
    assert A2AProtocol.verify(payload, sig, "mysecret") is True
    assert A2AProtocol.verify(payload, sig, "wrong") is False
    assert A2AProtocol.verify(payload, "badsig", "mysecret") is False


def test_build_request(a2a):
    req = a2a.build_request("schedule_meeting", {"topic": "test"})
    assert req["protocol"] == PROTOCOL_VERSION
    assert req["action"] == "schedule_meeting"
    assert req["from"]["name"] == "TestBot"
    assert req["params"]["topic"] == "test"
    assert "request_id" in req
    assert "timestamp" in req


def test_build_request_invalid_action(a2a):
    with pytest.raises(ValueError, match="Invalid action"):
        a2a.build_request("invalid_action", {})


def test_receive_valid(a2a):
    pid = a2a.pair("http://sender.local", "shared_secret")
    payload = a2a.build_request("ask_question", {"q": "hello?"})
    sig = A2AProtocol.sign(payload, "shared_secret")
    body = {**payload, "signature": sig}
    result = a2a.receive(body)
    assert result["status"] == "received"
    assert result["requires_human_approval"] is True
    assert len(a2a.inbox) == 1
    assert a2a.inbox[0]["status"] == "pending"


def test_receive_bad_signature(a2a):
    a2a.pair("http://sender.local", "shared_secret")
    payload = a2a.build_request("ask_question", {"q": "hello?"})
    body = {**payload, "signature": "invalid"}
    result = a2a.receive(body)
    assert result["status"] == "error"
    assert "signature" in result["message"].lower() or "unknown" in result["message"].lower()


def test_receive_wrong_protocol(a2a):
    result = a2a.receive({"protocol": "wrong-v99", "signature": "x"})
    assert result["status"] == "error"


def test_approve_and_reject(a2a):
    pid = a2a.pair("http://sender.local", "secret")
    payload = a2a.build_request("task_delegate", {"task": "do stuff"})
    sig = A2AProtocol.sign(payload, "secret")
    a2a.receive({**payload, "signature": sig})
    rid = a2a.inbox[0]["request_id"]

    result = a2a.approve(rid)
    assert result["status"] == "approved"
    assert a2a.inbox[0]["status"] == "approved"

    # Can't approve again
    result = a2a.approve(rid)
    assert result["status"] == "error"


def test_reject(a2a):
    pid = a2a.pair("http://sender.local", "secret")
    payload = a2a.build_request("share_document", {"doc": "readme.md"})
    sig = A2AProtocol.sign(payload, "secret")
    a2a.receive({**payload, "signature": sig})
    rid = a2a.inbox[0]["request_id"]

    result = a2a.reject(rid)
    assert result["status"] == "rejected"


def test_get_inbox_filter(a2a):
    pid = a2a.pair("http://x.local", "s")
    for action in ["ask_question", "task_delegate"]:
        payload = a2a.build_request(action, {})
        sig = A2AProtocol.sign(payload, "s")
        a2a.receive({**payload, "signature": sig})

    assert len(a2a.get_inbox("pending")) == 2
    a2a.approve(a2a.inbox[0]["request_id"])
    assert len(a2a.get_inbox("pending")) == 1
    assert len(a2a.get_inbox("approved")) == 1


def test_command_pair(a2a):
    result = a2a.handle_command("pair http://example.com mysecret")
    assert "페어링 완료" in result


def test_command_list_empty(a2a):
    result = a2a.handle_command("list")
    assert "없습니다" in result


def test_command_list_with_peers(a2a):
    a2a.pair("http://a.com", "s", "Alpha")
    result = a2a.handle_command("list")
    assert "Alpha" in result


def test_command_inbox_empty(a2a):
    result = a2a.handle_command("inbox")
    assert "비어있습니다" in result


def test_command_unpair(a2a):
    pid = a2a.pair("http://a.com", "s")
    result = a2a.handle_command(f"unpair {pid}")
    assert "해제" in result


def test_command_help(a2a):
    result = a2a.handle_command("")
    assert "/a2a pair" in result


def test_web_endpoints(a2a):
    # peers endpoint
    assert a2a.handle_peers_endpoint() == []
    a2a.pair("http://x.local", "s", "X")
    assert len(a2a.handle_peers_endpoint()) == 1

    # pair endpoint
    result = a2a.handle_pair_endpoint({"url": "http://y.local", "secret": "s2", "name": "Y"})
    assert result["status"] == "paired"

    # pair endpoint missing fields
    result = a2a.handle_pair_endpoint({})
    assert "error" in result


def test_persistence(tmp_path, monkeypatch):
    peers_path = tmp_path / "peers.json"
    inbox_path = tmp_path / "inbox.json"
    monkeypatch.setattr("salmalm.a2a._PEERS_PATH", peers_path)
    monkeypatch.setattr("salmalm.a2a._INBOX_PATH", inbox_path)
    monkeypatch.setattr("salmalm.a2a._DATA_DIR", tmp_path)

    a1 = A2AProtocol(instance_name="A")
    pid = a1.pair("http://z.local", "sec")

    a2 = A2AProtocol(instance_name="B")
    assert len(a2.peers) == 1
