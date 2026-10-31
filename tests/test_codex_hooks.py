"""Check registration and display names against the installed Codex itself."""

import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile
import time
import unittest

from agent_dino.adapters import command


@unittest.skipUnless(shutil.which("codex"), "Codex CLI is not installed")
class CodexHooksTests(unittest.TestCase):
    def test_codex_lists_all_eight_session_hooks_with_agent_dino_name(self):
        with tempfile.TemporaryDirectory(prefix="dino-hooks-test-", dir="/tmp") as directory:
            root = Path(directory)
            argv = command("codex", ["app-server", "--stdio"], root)
            with (root / "stderr").open("w+") as errors:
                process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=errors, env={**os.environ, "CODEX_HOME": directory})
                def send(payload):
                    process.stdin.write(json.dumps(payload).encode() + b"\n")
                    process.stdin.flush()

                send({"method": "initialize", "id": 1, "params": {
                    "clientInfo": {"name": "agent_dino_test", "version": "0.2.0"}}})
                response = None
                buffer = b""
                try:
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline and response is None:
                        if not select.select([process.stdout], [], [], 0.1)[0]:
                            continue
                        data = os.read(process.stdout.fileno(), 65536)
                        if not data:
                            break
                        buffer += data
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            message = json.loads(line)
                            if message.get("id") == 1:
                                self.assertNotIn("error", message)
                                send({"method": "initialized", "params": {}})
                                send({"method": "hooks/list", "id": 2,
                                      "params": {"cwds": [str(Path.cwd())]}})
                            elif message.get("id") == 2:
                                response = message
                    errors.seek(0)
                    self.assertIsNotNone(response, errors.read())
                    self.assertNotIn("error", response)
                    entry = response["result"]["data"][0]
                    self.assertEqual(entry["errors"], [])
                    registered = entry["hooks"]
                    self.assertEqual(len(registered), 8)
                    self.assertEqual({h["eventName"] for h in registered}, {
                        "sessionStart", "sessionEnd", "userPromptSubmit", "preToolUse",
                        "postToolUse", "permissionRequest", "stop", "interrupt"})
                    for hook in registered:
                        self.assertEqual(hook["statusMessage"], "Agent Dino")
                        self.assertEqual(hook["source"], "sessionFlags")
                        self.assertEqual(hook["trustStatus"], "untrusted")
                        self.assertTrue(hook["enabled"])
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    process.stdin.close()
                    process.stdout.close()


if __name__ == "__main__":
    unittest.main()
