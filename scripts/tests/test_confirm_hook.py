"""Tests for pet_confirm_hook - PreToolUse confirmation interception."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pet_confirm_hook as hook


def _payload(tool_name, tool_input):
    return json.dumps({"tool_name": tool_name, "tool_input": tool_input})


def test_no_output_when_safe(capsys):
    hook.run(_payload("Bash", {"command": "ls -la"}), daemon_url="http://127.0.0.1:1")
    out = capsys.readouterr().out.strip()
    assert out == ""


def test_allow_decision_on_confirm(capsys, monkeypatch):
    state = {"pending": True}
    def fake_request(url, data=None, **kw):
        if "confirm" in url:
            return _FakeResp({"ok": True, "request_id": "cf-1"})
        if "result" in url:
            state["pending"] = False
            return _FakeResp({"status": "decided", "decision": "allow"})
        raise AssertionError(url)
    monkeypatch.setattr("urllib.request.urlopen", fake_request)
    hook.run(_payload("Bash", {"command": "rm -rf /x"}), daemon_url="http://127.0.0.1:9")
    out = capsys.readouterr().out.strip()
    parsed = json.loads(out)
    pd = parsed["hookSpecificOutput"]["permissionDecision"]
    assert pd == "allow"


def test_deny_when_daemon_timeout(capsys, monkeypatch):
    def fake_request(url, data=None, **kw):
        if "confirm" in url:
            return _FakeResp({"ok": True, "request_id": "cf-2"})
        return _FakeResp({"status": "decided", "decision": "deny", "reason": "timeout"})
    monkeypatch.setattr("urllib.request.urlopen", fake_request)
    hook.run(_payload("Bash", {"command": "rm -rf /x"}), daemon_url="http://127.0.0.1:9")
    out = capsys.readouterr().out.strip()
    parsed = json.loads(out)
    assert parsed["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_graceful_when_daemon_down(capsys, monkeypatch):
    def boom(url, data=None, **kw):
        raise OSError("connection refused")
    monkeypatch.setattr("urllib.request.urlopen", boom)
    hook.run(_payload("Bash", {"command": "rm -rf /x"}), daemon_url="http://127.0.0.1:1")
    out = capsys.readouterr().out.strip()
    assert out == ""  # degrade: pass through, never block


class _FakeResp:
    def __init__(self, data):
        self._data = data
    def read(self):
        return json.dumps(self._data).encode("utf-8")
