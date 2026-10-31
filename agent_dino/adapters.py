"""Session-scoped integration, with no edits to user agent settings."""

import json
from pathlib import Path
import shlex
import sys

COMMON = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PermissionRequest",
          "PostToolUse", "Stop", "SessionEnd")
EXTRA = {
    "claude": ("PostToolUseFailure", "Notification", "StopFailure", "Elicitation", "ElicitationResult"),
    "codex": ("Interrupt",),
}


def hooks(agent, command=None):
    command = command or shlex.join([sys.executable, str(Path(__file__).with_name("hook.py"))])
    return {event: [{"hooks": [{"type": "command", "command": command, "timeout": 2,
                               "statusMessage": "Agent Dino"}]}]
            for event in COMMON + EXTRA[agent]}


def toml(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(toml(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(f"{k}={toml(v)}" for k, v in value.items()) + "}"
    raise TypeError(type(value))


def command(agent, args, runtime, installed_hooks=False):
    if agent == "run":
        if not args:
            raise ValueError("Pass a command after 'run --'.")
        return args
    if installed_hooks:
        return [agent, *(["--no-daemon", "--enable", "hooks"] if agent == "codex" else []), *args]
    config = hooks(agent)
    if agent == "claude":
        path = Path(runtime) / "claude-settings.json"
        path.write_text(json.dumps({"hooks": config}))
        return [agent, "--settings", str(path), *args]
    result = ["codex", "--no-daemon", "--enable", "hooks"]
    for event, groups in config.items():
        result += ["-c", f"hooks.{event}={toml(groups)}"]
    return result + args

