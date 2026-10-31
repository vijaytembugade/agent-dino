import fcntl
import json
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest

import pyte

from agent_dino.hook import relay
from agent_dino.pty_terminal import AgentScreen, AgentStream, Input
from agent_dino.shell import install


class InputTests(unittest.TestCase):
    def test_modern_terminal_sequences_do_not_pollute_codex_prompt(self):
        pending = bytearray()
        screen = AgentScreen(80, 24, pending)
        stream = AgentStream(screen)
        stream.feed(b"prompt: \x1b[>")
        stream.feed(b"1u\x1b[<u\x1b[?u\x1b[6 qtext\x1b_Ggraphic")
        stream.feed(b"s\x1b\\\x1b[6n")
        self.assertEqual(screen.display[0].rstrip(), "prompt: text")
        self.assertIn(b"R", pending)

    def test_split_function_key_and_escape_timeout(self):
        decoder = Input()
        self.assertEqual(decoder.feed(b"\x1b[1", now=1), [])
        self.assertEqual(decoder.feed(b"7~", now=1.01), [("key", b"\x1b[17~")])
        self.assertEqual(decoder.feed(b"\x1b", now=2), [])
        self.assertEqual(decoder.feed(now=2.1), [("key", b"\x1b")])

    def test_bracketed_paste_is_one_event_even_when_split(self):
        decoder = Input()
        self.assertEqual(decoder.feed(b"\x1b[200~many spaces \x1b[17~", now=1), [])
        data = b"\x1b[200~many spaces \x1b[17~\x1b[201~"
        self.assertEqual(decoder.feed(b"\x1b[201~", now=2), [("paste", data)])


class PtyTests(unittest.TestCase):
    def run_terminal(self, argv, env=None):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 26, 100, 0, 0))
        process = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave,
                                   env={**os.environ, "TERM": "xterm-256color", **(env or {})})
        screen = pyte.Screen(100, 26)
        stream = pyte.ByteStream(screen)
        output = bytearray()

        def poll():
            while select.select([master], [], [], 0)[0]:
                data = os.read(master, 65536)
                if not data:
                    break
                output.extend(data)
                stream.feed(data)

        def until(predicate, timeout=8):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                poll()
                if predicate():
                    return
                time.sleep(0.02)
            self.fail("Timeout. Screen:\n" + "\n".join(screen.display) + "\nRaw: " + repr(output[-1000:]))

        def cleanup():
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            os.close(master)
            os.close(slave)

        self.addCleanup(cleanup)
        return process, master, slave, screen, until

    def test_real_agent_tty_hooks_game_handoff_resize_and_cleanup(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            marker = Path(directory) / "events-path"
            process, master, slave, screen, until = self.run_terminal(
                [sys.executable, "-m", "agent_dino", "run", "--", sys.executable,
                 str(project / "tests/fixture_agent.py"), str(marker)])
            text = lambda: "\n".join(screen.display)
            until(lambda: marker.exists() and "Fixture agent ready" in text())
            inbox = marker.read_text()
            status_path = Path(inbox).parent / "status.json"
            until(lambda: status_path.exists() and json.loads(status_path.read_text())["hooks_connected"])
            os.write(master, b"busy\r")
            until(lambda: "YOUR AGENT IS WORKING" in text())
            until(lambda: json.loads(status_path.read_text())["events"].get("UserPromptSubmit") == 1)
            self.assertEqual(json.loads(status_path.read_text())["view"], "game")
            os.write(master, b" ")
            relay({"session_id": "fixture", "hook_event_name": "PermissionRequest", "tool_name": "Bash"}, inbox)
            until(lambda: "Agent needs you" in text())
            os.write(master, b" \rnext\r")
            until(lambda: "received: next" in text())
            self.assertNotIn("received:  ", text())
            relay({"session_id": "fixture", "hook_event_name": "PostToolUse", "tool_name": "Bash"}, inbox)
            until(lambda: "YOUR AGENT IS WORKING" in text())
            # A real resize must update the child's terminal without restarting it.
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 22, 80, 0, 0))
            screen.resize(lines=22, columns=80)
            relay({"session_id": "fixture", "hook_event_name": "Stop"}, inbox)
            until(lambda: "Agent needs you" in text())
            os.write(master, b"\rquit\r")
            until(lambda: process.poll() is not None)
            self.assertEqual(process.returncode, 0)
            self.assertFalse(Path(inbox).parent.exists())

    def test_plain_codex_shell_command_uses_launcher_and_preserves_exit_code(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            root = Path(directory)
            rc = root / "zshrc"
            install(["codex"], path=rc)
            executable = root / "codex"
            executable.write_text(f"#!{sys.executable}\nimport os,sys\nprint('DEFAULT_CODEX_LAUNCHED:' + os.environ.get('AGENT_DINO_ACTIVE','missing'))\nsys.exit(7)\n")
            executable.chmod(0o755)
            process, master, slave, screen, until = self.run_terminal(
                ["zsh", "-dfc", 'source "$1"; codex', "zsh", str(rc)],
                env={"PATH": str(root) + os.pathsep + os.environ["PATH"]})
            until(lambda: process.poll() is not None)
            self.assertEqual(process.returncode, 7)
            self.assertIn("DEFAULT_CODEX_LAUNCHED:1", "\n".join(screen.display))

    def test_plain_claude_receives_session_hooks_and_claude_status_strip(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            root = Path(directory)
            rc = root / "zshrc"
            install(["claude"], path=rc)
            executable = root / "claude"
            executable.write_text(
                f"#!{sys.executable}\n"
                "import json,sys\n"
                "from pathlib import Path\n"
                "settings=json.loads(Path(sys.argv[sys.argv.index('--settings')+1]).read_text())\n"
                "assert 'UserPromptSubmit' in settings['hooks']\n"
                "assert 'Stop' in settings['hooks']\n"
                "print('CLAUDE_WITH_HOOKS_READY',flush=True)\n"
                "input()\n")
            executable.chmod(0o755)
            process, master, slave, screen, until = self.run_terminal(
                ["zsh", "-dfc", 'source "$1"; claude', "zsh", str(rc)],
                env={"PATH": str(root) + os.pathsep + os.environ["PATH"]})
            until(lambda: "CLAUDE_WITH_HOOKS_READY" in "\n".join(screen.display))
            self.assertNotIn("Codex", "\n".join(screen.display))
            os.write(master, b"\r")
            until(lambda: process.poll() is not None)
            self.assertEqual(process.returncode, 0)


if __name__ == "__main__":
    unittest.main()
