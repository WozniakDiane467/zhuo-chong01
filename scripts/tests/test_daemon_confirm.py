"""Tests for daemon confirm-request queue logic (no HTTP)."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pet_daemon import PetDaemon


def test_create_and_respond():
    d = PetDaemon()
    rid = d.create_confirm("Bash", "执行命令：rm -rf /x", {}, timeout=60)
    pending = d.get_pending()
    assert any(r["request_id"] == rid for r in pending)
    d.respond(rid, "allow")
    res = d.get_confirm_result(rid)
    assert res["status"] == "decided" and res["decision"] == "allow"
    assert d.get_pending() == []


def test_timeout_denies():
    d = PetDaemon()
    rid = d.create_confirm("Bash", "执行命令：rm -rf /x", {}, timeout=0.1)
    time.sleep(0.3)
    res = d.get_confirm_result(rid)
    assert res["status"] == "decided" and res["decision"] == "deny"
    assert res.get("reason") == "timeout"


def test_remember_decision():
    d = PetDaemon()
    rid = d.create_confirm("Bash", "rm -rf /tmp/", {"command": "rm -rf /tmp/x"}, timeout=60)
    d.respond(rid, "remember")
    res = d.get_confirm_result(rid)
    assert res["decision"] == "allow"  # remember behaves as allow
    assert d._remembered is not None  # stored (tool_name, tool_input) for rules layer
