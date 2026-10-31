"""Local fake agent for integration tests; no models or network calls."""

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_dino.hook import relay

path = os.environ["AGENT_DINO_EVENTS"]
Path(sys.argv[1]).write_text(path)


def emit(name, **fields):
    relay({"session_id": "fixture", "hook_event_name": name, **fields}, path)


emit("SessionStart")
print("Fixture agent ready", flush=True)
for line in sys.stdin:
    name = line.strip()
    if name == "busy":
        emit("UserPromptSubmit")
    elif name == "wait":
        emit("PermissionRequest", tool_name="Bash")
    elif name == "resume":
        emit("PostToolUse", tool_name="Bash")
    elif name == "done":
        emit("Stop")
    elif name == "quit":
        break
    print("received: " + name, flush=True)

