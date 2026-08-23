"""
pet_confirm_hook.py - PreToolUse hook that routes important operations to the
desktop pet for user confirmation.

Reads the PreToolUse JSON payload from stdin, checks the rule engine:
- allow-rule hit  -> print permissionDecision "allow" (silent bypass)
- no rule hit     -> print nothing (pass through, WorkBuddy default permissions apply)
- confirm-rule hit -> create a pending request on the daemon, poll for the
  user's decision on the pet (allow/deny/remember), then print the decision.
- daemon unreachable -> print nothing (degrade: never block WorkBuddy)

Output (advanced JSON mode):
{"hookSpecificOutput": {"hookEventName": "PreToolUse",
                        "permissionDecision": "allow|deny",
                        "permissionDecisionReason": "..."}}
"""
import json
import sys
import time
import urllib.request

import pet_confirm_rules as rules

DAEMON_URL = "http://127.0.0.1:19877"
RESULT_POLL = 0.5  # seconds between result polls


def _post(url: str, data: dict):
    return json.loads(urllib.request.urlopen(
        url, data=json.dumps(data).encode("utf-8"), timeout=2
    ).read().decode("utf-8"))


def _get(url: str):
    return json.loads(urllib.request.urlopen(url, timeout=2).read().decode("utf-8"))


def _emit(decision: str, reason: str = ""):
    out = {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}
    print(json.dumps(out, ensure_ascii=False))


def run(stdin_text: str, daemon_url: str = DAEMON_URL):
    try:
        payload = json.loads(stdin_text)
    except json.JSONDecodeError:
        return  # malformed payload: pass through
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    if not tool_name:
        return

    # 1) Remembered allow-rule: silent allow, no card.
    if rules.is_allowed(tool_name, tool_input):
        _emit("allow", "remembered rule")
        return

    # 2) No confirm rule: pass through (WorkBuddy default permissions apply).
    if not rules.should_confirm(tool_name, tool_input):
        return

    summary = rules.build_summary(tool_name, tool_input)
    cfg = rules.load_config()
    timeout = float(cfg.get("confirm_timeout", 60))

    try:
        resp = _post(f"{daemon_url}/confirm",
                     {"tool_name": tool_name, "tool_input": tool_input,
                      "summary": summary, "timeout": timeout})
        request_id = resp.get("request_id", "")
        if not request_id:
            return
    except OSError:
        return  # daemon down: degrade, never block

    # 3) Poll until the pet user decides or timeout.
    deadline = time.time() + timeout + 2
    while time.time() < deadline:
        try:
            result = _get(f"{daemon_url}/result?request_id={request_id}")
        except OSError:
            time.sleep(RESULT_POLL)
            continue
        if result.get("status") == "decided":
            decision = result.get("decision", "deny")
            reason = result.get("reason", "")
            _emit("allow" if decision == "allow" else "deny", reason)
            return
        time.sleep(RESULT_POLL)

    _emit("deny", "timeout: no response from pet")


if __name__ == "__main__":
    run(sys.stdin.read())
