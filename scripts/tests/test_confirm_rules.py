"""Tests for pet_confirm_rules - rule matching and allow-rule persistence."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pet_confirm_rules as rules


def _cfg(tmp_path):
    return str(tmp_path / "pet_config.json")


def test_default_rules_match_rm_rf():
    assert rules.should_confirm("Bash", {"command": "rm -rf /home/x"}) is True


def test_safe_command_not_confirmed():
    assert rules.should_confirm("Bash", {"command": "ls -la"}) is False


def test_tool_pattern_matches_mcp_send():
    assert rules.should_confirm("mcp__agent-mail__SendMessage", {"to": "x@y.com"}) is True


def test_allow_rule_takes_priority(tmp_path):
    cfg = _cfg(tmp_path)
    rules.save_allow_rule("Bash", "rm -rf /tmp/", cfg)
    assert rules.is_allowed("Bash", "rm -rf /tmp/foo", cfg) is True
    assert rules.should_confirm("Bash", "rm -rf /tmp/foo", cfg) is False


def test_build_summary_truncates():
    s = rules.build_summary("Bash", {"command": "x" * 500})
    assert len(s) <= 220
