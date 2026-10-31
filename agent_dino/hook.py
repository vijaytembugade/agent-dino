"""Best-effort, silent hook relay. Never writes a permission decision.

Runs as a standalone file as well as a module. Only lifecycle metadata crosses
the local inbox: prompts, tool inputs, transcripts, and answers are discarded.
"""

import json
import os
from pathlib import Path
import sys
import tempfile
import time
import uuid

FIELDS = ("hook_event_name", "session_id", "turn_id", "agent_id", "tool_name",
          "tool_use_id", "permission_mode", "notification_type")


def relay(payload, path):
    if not path or not isinstance(payload, dict):
        return
    event = {key: payload[key] for key in FIELDS
             if isinstance(payload.get(key), str) and len(payload[key]) <= 512}
    # One atomic file per event avoids lost updates between concurrent hooks.
    # No socket permissions or background service are required by this relay.
    inbox = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=inbox, prefix=".event-", delete=False) as output:
            temporary = Path(output.name)
            json.dump(event, output)
        destination = inbox / f"{time.monotonic_ns():020d}-{uuid.uuid4().hex}.json"
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    path = os.environ.get("AGENT_DINO_EVENTS")
    if not path:
        return 0
    try:
        payload = json.load(sys.stdin)
        relay(payload, path)
    except (OSError, ValueError, TypeError):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

