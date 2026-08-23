"""Tests for pet_confirm_rules - rule matching and allow-rule persistence."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pet_confirm_rules as rules


def _cfg(tmp_path):
    return str(tmp_path / "pet_config.json")


def test_default_rules_match_rm_rf(tmp_path):
    cfg = _cfg(tmp_path)
    assert rules.should_confirm("Bash", {"command": "rm -rf /home/x"}, cfg) is True


def test_safe_command_not_confirmed(tmp_path):
    cfg = _cfg(tmp_path)
    assert rules.should_confirm("Bash", {"command": "ls -la"}, cfg) is False


def test_tool_pattern_matches_mcp_send(tmp_path):
    cfg = _cfg(tmp_path)
    assert rules.should_confirm("mcp__agent-mail__SendMessage", {"to": "x@y.com"}, cfg) is True


def test_allow_rule_takes_priority(tmp_path):
    cfg = _cfg(tmp_path)
    rules.save_allow_rule("Bash", "rm -rf /tmp/", cfg)
    assert rules.is_allowed("Bash", "rm -rf /tmp/foo", cfg) is True
    assert rules.should_confirm("Bash", "rm -rf /tmp/foo", cfg) is False


def test_build_summary_truncates():
    s = rules.build_summary("Bash", {"command": "x" * 500})
    assert len(s) <= 220


def test_remember_rule_persists(tmp_path):
    cfg = _cfg(tmp_path)
    rules.remember_rule("Bash", {"command": "rm -rf /tmp/x"}, cfg)
    assert rules.is_allowed("Bash", {"command": "rm -rf /tmp/x"}, cfg) is True


def test_mcp_tmeet_wildcard(tmp_path):
    cfg = _cfg(tmp_path)
    assert rules.should_confirm("mcp__tmeet__create", {}, cfg) is True


def test_none_and_empty_tool_input_do_not_crash(tmp_path):
    cfg = _cfg(tmp_path)
    assert rules.should_confirm("Bash", None, cfg) is False
    assert rules.should_confirm("Bash", {}, cfg) is False


def test_build_summary_unicode():
    s = rules.build_summary("Bash", {"command": "删除文件"})
    assert "删除文件" in s


def test_save_load_roundtrip(tmp_path):
    cfg = _cfg(tmp_path)
    original = {"confirm_timeout": 30,
                "confirm_rules": [{"tool": "Bash", "pattern": "danger", "label": "危险"}],
                "allow_rules": [{"tool": "Bash", "pattern": "safe"}]}
    rules.save_config(original, cfg)
    loaded = rules.load_config(cfg)
    assert loaded == original
