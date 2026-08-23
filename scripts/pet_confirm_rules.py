"""
pet_confirm_rules.py - Rule engine for pet confirm mode.

Decides whether a tool call needs user confirmation on the desktop pet,
and persists "remember" (allow) rules. Pure logic, no HTTP.
"""
import json
import os
import time

# Default dangerous-operation rules (tool + substring pattern).
# tool "" or "*" matches any tool; empty pattern matches any input.
DEFAULT_CONFIRM_RULES = [
    {"tool": "Bash", "pattern": "rm -rf", "label": "强制删除"},
    {"tool": "Bash", "pattern": "rm -r ", "label": "递归删除"},
    {"tool": "Bash", "pattern": "git push", "label": "推送代码"},
    {"tool": "Bash", "pattern": "git reset --hard", "label": "强制回退"},
    {"tool": "Bash", "pattern": "pip uninstall", "label": "卸载 Python 包"},
    {"tool": "Bash", "pattern": "npm publish", "label": "发布 npm 包"},
    {"tool": "Bash", "pattern": "robocopy", "label": "批量复制文件"},
    {"tool": "Bash", "pattern": "shutdown", "label": "关机/重启"},
    {"tool": "Bash", "pattern": "format ", "label": "格式化"},
    {"tool": "mcp__agent-mail__SendMessage", "pattern": "", "label": "发送邮件"},
    {"tool": "mcp__agent-mail__ReplyMessage", "pattern": "", "label": "回复邮件"},
    {"tool": "mcp__agent-mail__ForwardMessage", "pattern": "", "label": "转发邮件"},
    {"tool": "mcp__tmeet__*", "pattern": "", "label": "会议操作"},
]

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".workbuddy", "pet_config.json")
DEFAULT_TIMEOUT = 60


def load_config(config_file: str = CONFIG_FILE) -> dict:
    defaults = {"confirm_timeout": DEFAULT_TIMEOUT,
                "confirm_rules": DEFAULT_CONFIRM_RULES,
                "allow_rules": []}
    try:
        if os.path.exists(config_file):
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            defaults.update(data)
    except (OSError, json.JSONDecodeError):
        pass
    return defaults


def save_config(config: dict, config_file: str = CONFIG_FILE):
    try:
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def _tool_match(tool_pattern: str, tool_name: str) -> bool:
    if not tool_pattern or tool_pattern == "*":
        return True
    if tool_pattern.endswith("*"):
        return tool_name.startswith(tool_pattern[:-1])
    return tool_name == tool_pattern


def _input_text(tool_input: dict) -> str:
    return json.dumps(tool_input, ensure_ascii=False)


def _rule_hits(rule: dict, tool_name: str, text: str) -> bool:
    if not _tool_match(rule.get("tool", ""), tool_name):
        return False
    pattern = rule.get("pattern", "")
    return (pattern == "") or (pattern.lower() in text.lower())


def should_confirm(tool_name: str, tool_input: dict,
                   config_file: str = CONFIG_FILE) -> bool:
    """True if this tool call needs the desktop-pet confirmation card."""
    cfg = load_config(config_file)
    if _allow_hits(cfg, tool_name, tool_input):
        return False
    text = _input_text(tool_input)
    for rule in cfg.get("confirm_rules", []):
        if _rule_hits(rule, tool_name, text):
            return True
    return False


def _allow_hits(cfg: dict, tool_name: str, tool_input: dict) -> bool:
    text = _input_text(tool_input)
    for rule in cfg.get("allow_rules", []):
        if _rule_hits(rule, tool_name, text):
            return True
    return False


def is_allowed(tool_name: str, tool_input: dict,
               config_file: str = CONFIG_FILE) -> bool:
    return _allow_hits(load_config(config_file), tool_name, tool_input)


def save_allow_rule(tool_name: str, pattern: str,
                    config_file: str = CONFIG_FILE):
    """Persist an allow rule (used by tests and by daemon 'remember')."""
    cfg = load_config(config_file)
    rules_list = cfg.setdefault("allow_rules", [])
    existing = [r for r in rules_list if r.get("tool") == tool_name and r.get("pattern") == pattern]
    if not existing:
        rules_list.append({"tool": tool_name, "pattern": pattern,
                           "note": "remembered", "ts": time.time()})
        cfg["allow_rules"] = rules_list
        save_config(cfg, config_file)


def remember_rule(tool_name: str, tool_input: dict,
                  config_file: str = CONFIG_FILE):
    """Persist an allow rule derived from this call (whole input text as pattern)."""
    text = _input_text(tool_input)
    save_allow_rule(tool_name, text, config_file)


def build_summary(tool_name: str, tool_input: dict, max_len: int = 200) -> str:
    """Human-readable summary shown on the pet card."""
    text = _input_text(tool_input)
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return f"{tool_name}: {text}"
