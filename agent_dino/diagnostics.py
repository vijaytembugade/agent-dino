"""Short-lived launcher status. No prompts, responses, or tool arguments."""

import json
import os
from pathlib import Path
import time


def publish(root, agent, focus, state, event_counts, last_event):
    payload = {"pid": os.getpid(), "updated_at": time.time(), "agent": agent or "custom",
               "view": focus, "activity": state.status, "hooks_connected": state.seen_hook,
               "events": dict(event_counts), "last_event": last_event,
               "last_ignored_reason": state.last_ignored_reason}
    temporary = Path(root) / ".status.tmp"
    temporary.write_text(json.dumps(payload))
    temporary.replace(Path(root) / "status.json")


def active_sessions(base="/tmp", now=None):
    now = time.time() if now is None else now
    result = []
    for path in Path(base).glob("dino-*/status.json"):
        try:
            if path.stat().st_uid != os.getuid():
                continue
            data = json.loads(path.read_text())
            if isinstance(data, dict) and now - data.get("updated_at", 0) < 5:
                result.append(data)
        except (OSError, ValueError, TypeError):
            continue
    return result


def show():
    sessions = active_sessions()
    if not sessions:
        print("No current Agent Dino launcher was detected.")
        print("Start Claude with: ~/Code/agent-dino/agent-dino claude")
        print("An already-open session needs restarting to load this version.")
        return 1
    for data in sessions:
        print(f"{data['agent']}: activity={data['activity']}, view={data['view']}, pid={data['pid']}")
        print("Hooks: " + ("connected" if data['hooks_connected'] else "no event received"))
        print("Events: " + (", ".join(f"{name}={count}" for name, count in data['events'].items()) or "none"))
        if data.get("last_ignored_reason"):
            print("Last event ignored: " + data['last_ignored_reason'])
    return 0
