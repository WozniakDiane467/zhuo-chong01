# workbuddy-pet-pro 确认模式实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 基于 WorkBuddy-pet 仓库二次开发 `workbuddy-pet-pro` skill——在保留原有状态联动的基础上，新增"桌宠反向确认"能力（A档真双向）：WorkBuddy 遇到重要操作时，由桌宠弹出确认卡片（同意/拒绝/同意并记住），用户点击后回传 allow/deny，超时默认拒绝。

**Architecture:** 沿用现有「hooks → pet_bridge → daemon(HTTP) → state 文件 → 桌宠轮询」管道。新增一层"确认请求"管道：PreToolUse 钩子（pet_confirm_hook.py）拦截需确认的工具调用 → daemon 创建 pending 请求 → 桌宠轮询 `/pending` 弹出三按钮卡片 → 点击后 daemon 记录 decision → 钩子轮询 `/confirm/result` 拿到结果 → 输出 `permissionDecision`（优先于 WorkBuddy 自带权限弹窗）。规则引擎（pet_confirm_rules.py）负责名单匹配与"记住"规则持久化。daemon 不可用时钩子降级为放行（不阻塞 WorkBuddy）。

**Tech Stack:** Python 3.10+ / tkinter / http.server / Pillow；配置持久化到 `~/.workbuddy/pet_config.json`；无新依赖。

**关键决策（grill-me 已确认）：**
1. 另建新 skill `workbuddy-pet-pro`，旧版 workbuddy-pet 不动
2. A 档·真双向确认：钩子拦截 → 桌宠卡片 → 点击回传 allow/deny
3. 判定机制：WorkBuddy 权限确认类操作全部交给桌宠承接（钩子决策优先于系统弹窗）+ 自定义危险名单补充
4. 三按钮：同意 / 拒绝 / 同意并记住；弹卡时动画+气泡+提示音三连提醒
5. 超时 60 秒默认拒绝（可配置）；daemon 不可用时降级放行
6. 新 daemon 端口 19877（避开旧版 19876），沿用现有 4 角色

---

## 项目目录约定

- 新 skill 项目根：`C:\Users\Administrator\WorkBuddy\2026-08-23-09-28-41\workbuddy-pet-pro\`
- 源仓库（只读参考）：`C:\Users\Administrator\WorkBuddy\2026-08-23-09-28-41\WorkBuddy-pet\`
- 运行时配置文件：`~/.workbuddy/pet_config.json`（Windows: `C:\Users\Administrator\.workbuddy\pet_config.json`）
- 安装目标（最终）：`C:\Users\Administrator\.workbuddy\skills\workbuddy-pet-pro\`

**注意：所有脚本内部一律使用 `os.path.expanduser("~")` 推导用户目录，禁止硬编码 `C:/Users/Admin/` 或 `C:/Users/Administrator/`。**（旧版 hooks.json 硬编码 `C:/Users/Admin/` 是 bug，本次必须根治。）

---

## Task 1: 项目骨架初始化（复制+改名+修路径）

**Files:**
- Create: `workbuddy-pet-pro/`（整体复制自 `WorkBuddy-pet/`，含 assets/ scripts/ hooks.json SKILL.md README.md LICENSE，**不含 .git**）
- Modify: `workbuddy-pet-pro/SKILL.md`
- Modify: `workbuddy-pet-pro/hooks.json`
- Modify: `workbuddy-pet-pro/scripts/pet_launch.py`
- Modify: `workbuddy-pet-pro/scripts/install_hooks.py`

**Step 1: 复制骨架**

Run:
```bash
cd "C:/Users/Administrator/WorkBuddy/2026-08-23-09-28-41"
cp -r WorkBuddy-pet workbuddy-pet-pro
rm -rf workbuddy-pet-pro/.git
cd workbuddy-pet-pro && git init
```

**Step 2: 重写 SKILL.md**（保留图集生成等原有说明，更新头部与确认能力）

重写 `workbuddy-pet-pro/SKILL.md` 的 frontmatter 与 /pet 命令部分：

```markdown
---
name: workbuddy-pet-pro
description: WorkBuddy 桌面宠物强化版（确认模式）。当用户想要创建、自定义或启动桌面宠物，或需要"重要操作通过桌宠确认"时使用。触发词包括"/pet-pro""启动宠物""桌宠确认""同意并记住"等。支持聊天感知状态联动 + 桌宠反向确认（重要操作由桌宠弹卡，用户点击同意/拒绝/记住）。
agent_created: true
---
```

命令部分改为：

```bash
python ~/.workbuddy/skills/workbuddy-pet-pro/scripts/pet_launch.py
```

（即所有 `workbuddy-pet` 字样在 SKILL.md 内改为 `workbuddy-pet-pro`。）

**Step 3: 重写 hooks.json 为模板（用 {SKILL_DIR} 占位，由 install_hooks.py 安装时替换为真实路径）**

写 `workbuddy-pet-pro/hooks.json`：

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python \"{SKILL_DIR}/scripts/pet_confirm_hook.py\"",
            "timeout": 65
          }
        ]
      },
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python \"{SKILL_DIR}/scripts/pet_bridge.py\" thinking \"正在思考...\"",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python \"{SKILL_DIR}/scripts/pet_bridge.py\" running \"工作中...\"",
            "timeout": 5
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"{SKILL_DIR}/scripts/pet_bridge.py\" thinking \"正在思考...\"",
            "timeout": 5
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"{SKILL_DIR}/scripts/pet_bridge.py\" waving \"完成！\"",
            "timeout": 5
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"{SKILL_DIR}/scripts/pet_bridge.py\" idle",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

> 注意：`pet_confirm_hook.py` 在 thinking 钩子**之前**（数组顺序即执行顺序），timeout 65s > 确认超时 60s。

**Step 4: 修改 pet_launch.py**

将 `SKILL_DIR` 常量改为：

```python
SKILL_DIR = os.path.join(os.path.expanduser("~"), ".workbuddy", "skills", "workbuddy-pet-pro")
```

（其余逻辑不变。）

**Step 5: 修改 install_hooks.py（路径模板替换）**

在 `load_skill_hooks` 中增加占位符替换。修改函数：

```python
def load_skill_hooks(skill_dir: str) -> dict:
    """Load hooks.json from skill directory, replacing {SKILL_DIR} placeholder."""
    hooks_path = os.path.join(skill_dir, "hooks.json")
    if not os.path.exists(hooks_path):
        print(f"[install] hooks.json not found at {hooks_path}")
        return {}
    with open(hooks_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = content.replace("{SKILL_DIR}", skill_dir.replace("\\", "/"))
    return json.loads(content).get("hooks", {})
```

同时把模块级 `_HOOK_MARKER = "workbuddy-pet"` 改为 `_HOOK_MARKER = "workbuddy-pet-pro"`（uninstall 时按新标记识别）。

**Step 6: Commit**

```bash
git add -A && git commit -m "chore: init workbuddy-pet-pro skeleton from upstream"
```

---

## Task 2: 规则引擎 pet_confirm_rules.py（纯逻辑，TDD）

**Files:**
- Create: `workbuddy-pet-pro/scripts/pet_confirm_rules.py`
- Create: `workbuddy-pet-pro/scripts/tests/test_confirm_rules.py`

**Step 1: Write the failing test**

`scripts/tests/test_confirm_rules.py`（pytest）：

```python
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


def test_allow_rule_takes_priority():
    cfg = _cfg(tmp_path)
    rules.save_allow_rule("Bash", "rm -rf /tmp/", cfg)
    assert rules.is_allowed("Bash", "rm -rf /tmp/foo", cfg) is True
    assert rules.should_confirm("Bash", "rm -rf /tmp/foo", cfg) is False


def test_build_summary_truncates():
    s = rules.build_summary("Bash", {"command": "x" * 500})
    assert len(s) <= 220
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_confirm_rules.py -v`
Expected: FAIL（模块不存在）

**Step 3: Write implementation**

`scripts/pet_confirm_rules.py`：

```python
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


def remember_rule(tool_name: str, tool_input: dict,
                  config_file: str = CONFIG_FILE):
    """Persist an allow rule derived from this call (same tool + first arg substring)."""
    cfg = load_config(config_file)
    rules_list = cfg.setdefault("allow_rules", [])
    text = _input_text(tool_input)
    # Store the whole input text as pattern: subsequent calls with same tool
    # and containing this text will be auto-allowed.
    existing = [r for r in rules_list if r.get("tool") == tool_name and r.get("pattern") == text]
    if not existing:
        rules_list.append({"tool": tool_name, "pattern": text,
                           "note": "remembered", "ts": time.time()})
        cfg["allow_rules"] = rules_list
        save_config(cfg, config_file)


def build_summary(tool_name: str, tool_input: dict, max_len: int = 200) -> str:
    """Human-readable summary shown on the pet card."""
    text = _input_text(tool_input)
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return f"{tool_name}: {text}"
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/tests/test_confirm_rules.py -v`
Expected: PASS (5 passed)

**Step 5: Commit**

```bash
git add scripts/pet_confirm_rules.py scripts/tests/test_confirm_rules.py
git commit -m "feat: confirm rule engine with allow-rule persistence"
```

---

## Task 3: daemon 确认队列扩展

**Files:**
- Modify: `workbuddy-pet-pro/scripts/pet_constants.py`
- Modify: `workbuddy-pet-pro/scripts/pet_daemon.py`
- Create: `workbuddy-pet-pro/scripts/tests/test_daemon_confirm.py`

**Step 1: Write the failing test**

`scripts/tests/test_daemon_confirm.py`：

```python
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
    assert d._remembered is not None  # stored (tool, tool_input) for rules layer
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_daemon_confirm.py -v`
Expected: FAIL（PetDaemon 无 create_confirm）

**Step 3: Modify pet_constants.py**

DAEMON_PORT 改为 19877，并增加确认间隔常量：

```python
DAEMON_PORT = 19877
CONFIRM_POLL_INTERVAL = 500     # ms, pet polls /pending
CONFIRM_RESULT_POLL = 0.5       # s, hook polls /confirm/result
```

**Step 4: Modify pet_daemon.py（PetDaemon 类增加确认队列）**

在 `PetDaemon.__init__` 增加：

```python
self.confirm_lock = threading.Lock()
self.confirm_requests = {}      # request_id -> dict
self._confirm_seq = 0
self._remembered = None         # (tool_name, tool_input) from last remember
```

新增方法（放在 `get_status` 之前）：

```python
def create_confirm(self, tool_name: str, summary: str, tool_input: dict,
                   timeout: float = 60) -> str:
    with self.confirm_lock:
        self._confirm_seq += 1
        request_id = f"cf-{int(time.time())}-{self._confirm_seq}"
        self.confirm_requests[request_id] = {
            "request_id": request_id,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "summary": summary,
            "created_at": time.time(),
            "timeout": timeout,
            "decision": None,
        }
        return request_id

def _sweep_expired(self):
    now = time.time()
    for rid, req in list(self.confirm_requests.items()):
        if req["decision"] is None and now - req["created_at"] > req["timeout"]:
            req["decision"] = "deny"
            req["reason"] = "timeout"

def get_pending(self) -> list:
    with self.confirm_lock:
        self._sweep_expired()
        return [
            {"request_id": r["request_id"], "tool_name": r["tool_name"],
             "summary": r["summary"], "created_at": r["created_at"]}
            for r in self.confirm_requests.values()
            if r["decision"] is None
        ]

def get_confirm_result(self, request_id: str) -> dict:
    with self.confirm_lock:
        self._sweep_expired()
        req = self.confirm_requests.get(request_id)
        if req is None:
            return {"status": "unknown"}
        if req["decision"] is None:
            return {"status": "pending"}
        return {"status": "decided", "decision": req["decision"],
                "reason": req.get("reason", "")}

def respond(self, request_id: str, decision: str):
    with self.confirm_lock:
        req = self.confirm_requests.get(request_id)
        if req is None:
            return
        if decision == "remember":
            self._remembered = (req["tool_name"], req.get("tool_input", {}))
            req["decision"] = "allow"
            req["reason"] = "remembered"
        elif decision in ("allow", "deny"):
            req["decision"] = decision
        else:
            return
```

在 `PetHandler` 增加三个端点（do_POST 中 `/confirm`、`/respond`；do_GET 中 `/pending`、`/confirm/result`）：

do_POST 增加：

```python
elif path == "/confirm":
    summary = data.get("summary", "")
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})
    timeout = float(data.get("timeout", 60))
    rid = self.daemon.create_confirm(tool_name, summary, tool_input, timeout)
    self._send_json({"ok": True, "request_id": rid})
elif path == "/respond":
    rid = data.get("request_id", "")
    decision = data.get("decision", "")
    self.daemon.respond(rid, decision)
    self._send_json({"ok": True, "request_id": rid, "decision": decision})
```

do_GET 增加：

```python
elif path == "/pending":
    self._send_json({"requests": self.daemon.get_pending()})
elif path == "/confirm/result":
    rid = fixed_params.get("request_id", [""])[0]
    self._send_json(self.daemon.get_confirm_result(rid))
```

同时给 PetDaemon 增加 `get_remembered()` 供钩子侧使用：

```python
def get_remembered(self):
    with self.confirm_lock:
        return self._remembered
```

**Step 5: Run test to verify it passes**

Run: `python -m pytest scripts/tests/test_daemon_confirm.py -v`
Expected: PASS (3 passed)

**Step 6: Commit**

```bash
git add scripts/pet_constants.py scripts/pet_daemon.py scripts/tests/test_daemon_confirm.py
git commit -m "feat: daemon confirm queue with timeout and remember"
```

---

## Task 4: 确认钩子 pet_confirm_hook.py

**Files:**
- Create: `workbuddy-pet-pro/scripts/pet_confirm_hook.py`
- Create: `workbuddy-pet-pro/scripts/tests/test_confirm_hook.py`

**Step 1: Write the failing test**

`scripts/tests/test_confirm_hook.py`：

```python
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
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest scripts/tests/test_confirm_hook.py -v`
Expected: FAIL（模块不存在）

**Step 3: Write implementation**

`scripts/pet_confirm_hook.py`：

```python
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
    req = urllib.request.Request(
        url, data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=2).read().decode("utf-8"))


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
            result = _get(f"{daemon_url}/confirm/result?request_id={request_id}")
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
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest scripts/tests/test_confirm_hook.py -v`
Expected: PASS (4 passed)

> 注意：test 里 monkeypatch 的是 `urllib.request.urlopen`，实现必须用 `urllib.request.urlopen`（而不是 `urllib.request` 模块级别名）才能被 patch 到——上面实现已满足。

**Step 5: Commit**

```bash
git add scripts/pet_confirm_hook.py scripts/tests/test_confirm_hook.py
git commit -m "feat: PreToolUse confirm hook with degrade-safe passthrough"
```

---

## Task 5: 桌宠确认卡片 UI

**Files:**
- Modify: `workbuddy-pet-pro/scripts/pet_constants.py`
- Modify: `workbuddy-pet-pro/scripts/desktop_pet.py`

**Step 1: Modify pet_constants.py**

确认状态映射（agree → waiting 动画更贴切）：

```python
"agree":      "waiting",   # 等待确认 → 思考/等待动画 + 三按钮卡片
```

**Step 2: Modify desktop_pet.py（三按钮确认卡片 + 轮询 pending）**

在 `DesktopPet.__init__` 中，OK 按钮之后新增确认卡片 frame：

```python
# ── Confirm card (3 buttons, shown on pending confirm request) ──
self.confirm_frame = tk.Frame(self.main_frame, bg=TRANSPARENT_COLOR)
self.confirm_btn_allow = tk.Button(
    self.confirm_frame, text="同意", font=("Microsoft YaHei", 9, "bold"),
    bg="#4CAF50", fg="white", activebackground="#388E3C",
    relief="flat", padx=10, pady=2, cursor="hand2",
    command=lambda: self._on_confirm_click("allow"))
self.confirm_btn_deny = tk.Button(
    self.confirm_frame, text="拒绝", font=("Microsoft YaHei", 9, "bold"),
    bg="#E53935", fg="white", activebackground="#C62828",
    relief="flat", padx=10, pady=2, cursor="hand2",
    command=lambda: self._on_confirm_click("deny"))
self.confirm_btn_remember = tk.Button(
    self.confirm_frame, text="记住", font=("Microsoft YaHei", 9, "bold"),
    bg="#2196F3", fg="white", activebackground="#1565C0",
    relief="flat", padx=10, pady=2, cursor="hand2",
    command=lambda: self._on_confirm_click("remember"))
for b in (self.confirm_btn_allow, self.confirm_btn_deny, self.confirm_btn_remember):
    b.pack(side="left", padx=2, pady=2)
self.confirm_frame.pack_forget()  # hidden initially
self._confirm_visible = False
self._confirm_request_id = None
self._last_pending_count = 0
```

初始化时启动确认轮询（在 `_poll_chat_state` 调用后追加）：

```python
self._poll_confirm()
```

新增方法（放在 `_poll_chat_state` 之后）：

```python
def _poll_confirm(self):
    """Poll daemon /pending; show the confirm card when a request arrives."""
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:19877/pending", timeout=2) as r:
            data = json.loads(r.read().decode("utf-8"))
        requests = data.get("requests", [])
        if requests and not self._confirm_visible:
            req = requests[0]
            self._show_confirm_card(req)
        elif not requests and self._confirm_visible:
            # Request resolved (allow/deny) or expired while card shown
            self._confirm_visible = False
            self.confirm_frame.pack_forget()
            self.set_state("idle")
    except (OSError, ValueError):
        pass
    self.root.after(500, self._poll_confirm)

def _show_confirm_card(self, req: dict):
    self._confirm_visible = True
    self._confirm_request_id = req["request_id"]
    self._stop_wander()
    self.set_state("waiting")
    summary = req.get("summary", "需要确认操作")
    self._show_bubble(summary)
    self.confirm_frame.pack(fill="x", padx=4)
    try:
        if self.sound_enabled:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONQUESTION)
    except Exception:
        pass

def _on_confirm_click(self, decision: str):
    """User clicked a confirm-card button; report to daemon."""
    try:
        import urllib.request
        body = json.dumps({"request_id": self._confirm_request_id,
                           "decision": decision}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:19877/respond", data=body,
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=2)
    except OSError:
        pass
    self._confirm_visible = False
    self.confirm_frame.pack_forget()
    feedback = {"allow": "已放行", "deny": "已拒绝", "remember": "已记住，同类自动放行"}
    self._show_bubble(feedback.get(decision, "已处理"))
    self.set_state("waving")
    self.root.after(2000, lambda: (self.bubble.hide(), self.set_state("idle")))
    self._write_state_file("idle", "")
```

注意 `_show_confirm_card` 用 `set_state("waiting")` 而非 "agree"（constants 已映射 agree→waiting，这里直接用动画状态名）。`_poll_chat_state` 中 agree 分支逻辑保留（兼容旧 bridge 手动触发）。

**Step 3: 手动冒烟测试**

Run（需 Windows 图形环境）：
```bash
cd "C:/Users/Administrator/WorkBuddy/2026-08-23-09-28-41/workbuddy-pet-pro/scripts"
python pet_daemon.py &
python desktop_pet.py --atlas ../assets/diana/diana_atlas.png --manifest ../assets/diana/pet.json --scale 1.0 &
curl -s -X POST http://127.0.0.1:19877/confirm -H "Content-Type: application/json" -d '{"tool_name":"Bash","summary":"执行命令：rm -rf /test","tool_input":{"command":"rm -rf /test"},"timeout":60}'
```
Expected: 宠物出现，气泡显示摘要，宠物下方出现 同意/拒绝/记住 三个按钮；点"同意"→ 气泡"已放行"→ 2 秒后恢复待机。

**Step 4: Commit**

```bash
git add scripts/pet_constants.py scripts/desktop_pet.py
git commit -m "feat: pet confirm card UI (allow/deny/remember)"
```

---

## Task 6: 安装脚本与端到端验收

**Files:**
- Modify: `workbuddy-pet-pro/scripts/pet_launch.py`（Task 1 已改 SKILL_DIR，此处确认端口常量一致）
- Verify: `workbuddy-pet-pro/hooks.json`（Task 1 已改）

**Step 1: 安装到用户 skill 目录**

Run:
```bash
SKILL_SRC="C:/Users/Administrator/WorkBuddy/2026-08-23-09-28-41/workbuddy-pet-pro"
SKILL_DST="C:/Users/Administrator/.workbuddy/skills/workbuddy-pet-pro"
rm -rf "$SKILL_DST"
cp -r "$SKILL_SRC" "$SKILL_DST"
python "$SKILL_DST/scripts/install_hooks.py"
```

Expected: 输出 "Hooks saved to C:\Users\Administrator\.workbuddy\settings.json"。

**Step 2: 验证 settings.json hooks 路径正确**

Run:
```bash
python -c "import json,os; d=json.load(open(os.path.expanduser('~/.workbuddy/settings.json'))); print(json.dumps(d['hooks'], ensure_ascii=False, indent=1)[:800])"
```
Expected: 所有 command 中的路径含 `workbuddy-pet-pro` 且用户目录为 `C:/Users/Administrator/`（**不允许出现 `C:/Users/Admin/`**）。

**Step 3: 端到端手动验收清单**（每项记录结果）

1. 启动：`python C:/Users/Administrator/.workbuddy/skills/workbuddy-pet-pro/scripts/pet_launch.py` → daemon + 宠物窗口出现
2. 聊天感知：在 WorkBuddy 发一条任务 → 宠物变"思考中"；工具执行 → "工作中"；结束 → "完成！"+提示音
3. 弹卡：`curl -s -X POST http://127.0.0.1:19877/confirm -H "Content-Type: application/json" -d '{"tool_name":"Bash","summary":"执行命令：rm -rf /test","tool_input":{"command":"rm -rf /test"},"timeout":60}'` → 宠物弹卡片
4. 同意：点"同意" → `curl -s "http://127.0.0.1:19877/confirm/result?request_id=<id>"` 返回 `decision:"allow"`
5. 拒绝：再来一次点"拒绝" → result 返回 `decision:"deny"`
6. 记住：再来一次点"记住" → result 返回 `decision:"allow"`；`~/.workbuddy/pet_config.json` 的 allow_rules 增加一条；再次同命令触发钩子 → **不弹卡直接放行**
7. 超时：timeout 设 5，不点击 → 5 秒后 result 返回 `decision:"deny", reason:"timeout"`
8. 真实钩子：在 WorkBuddy 让 agent 执行 `rm -rf /tmp/pet-test`（或任何命中名单的命令）→ 宠物弹卡 → 点击后 agent 继续/被拒
9. 降级：杀掉 daemon 后 WorkBuddy 执行命中命令 → 不阻塞，任务正常继续
10. `/pet-pro` 触发词：新开会话输入 `/pet-pro` → 宠物启动

**Step 4: 更新 README.md**（说明确认模式、端口 19877、配置项 confirm_rules/allow_rules/confirm_timeout）

**Step 5: Commit**

```bash
git add -A && git commit -m "feat: install flow + e2e verification for confirm mode"
```

---

## 验收标准（Definition of Done）

1. 新 skill 独立运行，旧 workbuddy-pet 不受影响（端口 19876 vs 19877）
2. hooks 路径正确（无 Admin 硬编码）
3. 状态联动完整：思考/工作/完成/待机
4. 确认链路真双向：钩子拦截 → 卡片 → 点击回传 → allow/deny 生效于 WorkBuddy
5. "同意并记住"持久化，同类操作不再弹卡
6. 超时 60s 默认拒绝；daemon 挂掉不阻塞 WorkBuddy（降级放行）
7. 4 个角色可切换；右键菜单功能保留
8. 全部 pytest 通过（test_confirm_rules / test_daemon_confirm / test_confirm_hook）

## 风险与兜底

| 风险 | 兜底 |
|---|---|
| 桌宠没开/用户不在 → 卡片无人点 | daemon 超时自动 deny，安全优先 |
| daemon 崩溃 | 钩子捕获 OSError 输出空 → 放行不阻塞 |
| 钩子脚本自身异常 | 顶层 try 兜底，无输出=放行 |
| 误伤日常操作（频繁弹卡） | 名单默认仅危险命令+发信；用户可编辑 pet_config.json 增删 |
| 旧 hooks 与新 hooks 并存 | 新 skill 用独立标记 workbuddy-pet-pro，可单独 uninstall |
