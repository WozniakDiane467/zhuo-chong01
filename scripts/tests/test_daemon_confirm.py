"""Tests for daemon confirm-request queue logic (no HTTP)."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pet_daemon import PetDaemon
import pet_confirm_rules as rules


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


def test_remember_decision(tmp_path):
    config_file = str(tmp_path / "pet_config.json")
    d = PetDaemon(config_file=config_file)
    rid = d.create_confirm("Bash", "rm -rf /tmp/", {"command": "rm -rf /tmp/x"}, timeout=60)
    assert d.respond(rid, "remember") is True
    res = d.get_confirm_result(rid)
    assert res["decision"] == "allow"  # remember behaves as allow
    assert d._remembered is not None  # stored (tool_name, tool_input) for rules layer
    # rule persisted to disk: hook's is_allowed reads the same config file
    cfg = rules.load_config(config_file)
    assert len(cfg.get("allow_rules", [])) == 1
    assert cfg["allow_rules"][0]["tool"] == "Bash"
    # already decided: cannot override
    assert d.respond(rid, "deny") is False


def test_respond_invalid_decision():
    d = PetDaemon()
    rid = d.create_confirm("Bash", "rm -rf /tmp/", {}, timeout=60)
    assert d.respond(rid, "maybe") is False
    res = d.get_confirm_result(rid)
    assert res["status"] == "pending"  # decision untouched


def test_respond_unknown_rid():
    d = PetDaemon()
    assert d.respond("cf-does-not-exist", "allow") is False


def test_already_decided_cannot_override():
    d = PetDaemon()
    rid = d.create_confirm("Bash", "rm -rf /tmp/", {}, timeout=60)
    assert d.respond(rid, "allow") is True
    assert d.respond(rid, "deny") is False
    assert d.respond(rid, "remember") is False
    res = d.get_confirm_result(rid)
    assert res["decision"] == "allow"
