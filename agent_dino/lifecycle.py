"""Translate documented hook events into game activity, independent of UI."""

from collections import Counter

QUESTION_TOOLS = {"AskUserQuestion", "request_user_input", "tool/requestUserInput"}


class Lifecycle:
    def __init__(self, auto_only=False):
        self.auto_only = auto_only
        self.session = None
        self.turn = None
        self.status = "idle"
        self.pending = set()
        self.pending_names = Counter()
        self.active = False
        self.enabled = not auto_only
        self.seen_hook = False
        self.last_ignored_reason = None

    def handle(self, event):
        self.last_ignored_reason = None
        if not isinstance(event, dict) or event.get("agent_id"):
            self.last_ignored_reason = "subagent or invalid event"
            return False
        name = event.get("hook_event_name")
        session = event.get("session_id")
        if not isinstance(name, str) or not isinstance(session, str) or not session:
            self.last_ignored_reason = "missing event name or session ID"
            return False
        if self.session is None:
            if name not in {"SessionStart", "UserPromptSubmit"}:
                self.last_ignored_reason = "no main session established yet"
                return False
            self.session = session
        if session != self.session:
            self.last_ignored_reason = "different session"
            return False
        turn = event.get("turn_id")
        if name not in {"SessionStart", "UserPromptSubmit"} and turn and self.turn and turn != self.turn:
            self.last_ignored_reason = "different turn"
            return False
        self.seen_hook = True
        old = self.status
        mode = event.get("permission_mode")
        if mode is not None and self.auto_only:
            self.enabled = mode in {"auto", "dontAsk", "bypassPermissions", "never"}
        tool = event.get("tool_name", "unknown")
        if not isinstance(tool, str):
            return False
        key = event.get("tool_use_id") or tool
        if not isinstance(key, str):
            return False
        if name == "UserPromptSubmit":
            self.turn = turn
            self.pending.clear()
            self.pending_names.clear()
            self.active = True
            self.status = "busy" if self.enabled else "idle"
        elif name in {"Stop", "StopFailure", "Interrupt", "SessionEnd"}:
            self.pending.clear()
            self.pending_names.clear()
            self.active = False
            self.status = "idle"
            if name == "SessionEnd":
                self.session = None
                self.turn = None
        elif name == "PermissionRequest" or (name == "PreToolUse" and tool in QUESTION_TOOLS):
            if name == "PermissionRequest" and not event.get("tool_use_id"):
                self.pending_names[tool] += 1
            else:
                self.pending.add(key)
            self.status = "waiting"
        elif name in {"Elicitation", "Notification"}:
            if name == "Elicitation" or event.get("notification_type") in {"permission_prompt", "elicitation_dialog", "idle_prompt"}:
                self.status = "waiting"
        elif name in {"PostToolUse", "PostToolUseFailure", "ElicitationResult"}:
            # PermissionRequest in Claude has no tool_use_id; match its name.
            self.pending.discard(key)
            self.pending.discard(tool)
            if self.pending_names[tool] > 0:
                self.pending_names[tool] -= 1
            pending = self.pending or any(self.pending_names.values())
            self.status = "waiting" if pending else ("busy" if self.enabled and self.active else "idle")
        elif name == "PreToolUse" and self.enabled and self.active and not self.pending and not any(self.pending_names.values()):
            self.status = "busy"
        return old != self.status

