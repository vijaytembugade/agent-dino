"""Exercise real TTYs, tmux panes, hooks, input routing, and cleanup."""

import fcntl
import json
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest

from agent_dino.terminal import Tmux
from agent_dino.cli import find_tmux


class DemoTests(unittest.TestCase):
    def test_game_runs_in_real_terminal_and_restores_terminal_mode(self):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 26, 100, 0, 0))
        before = termios.tcgetattr(slave)
        process = subprocess.Popen([sys.executable, "-m", "agent_dino", "demo"],
                                   stdin=slave, stdout=slave, stderr=slave,
                                   env={**os.environ, "TERM": "xterm-256color"})
        output = bytearray()
        try:
            deadline = time.monotonic() + 5
            while b"DINO / DEMO" not in output and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    output.extend(os.read(master, 65536))
            self.assertIn(b"DINO / DEMO", output)
            os.write(master, b" ")
            time.sleep(0.1)
            os.write(master, b"rq")
            # Keep draining the PTY while curses draws/restores the screen;
            # its small output buffer can otherwise block the child at exit.
            deadline = time.monotonic() + 3
            while process.poll() is None and time.monotonic() < deadline:
                if select.select([master], [], [], 0.05)[0]:
                    output.extend(os.read(master, 65536))
            self.assertEqual(process.poll(), 0)
            after = termios.tcgetattr(slave)
            # macOS sets PENDIN when input is reprocessed after switching back
            # to canonical mode; it is transient kernel state, not a mode leak.
            pending = getattr(termios, "PENDIN", 0)
            after[3] &= ~pending
            before[3] &= ~pending
            self.assertEqual(after, before)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)


@unittest.skipUnless(find_tmux(), "tmux not installed")
class TerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        probe = Tmux(find_tmux(), f"agent-dino-test-probe-{os.getpid()}")
        try:
            probe.call("-f", "/dev/null", "new-session", "-d", "-s", "probe")
        except RuntimeError as error:
            if "Operation not permitted" in str(error):
                raise unittest.SkipTest("This sandbox blocks tmux's local Unix socket") from error
            raise
        finally:
            probe.call("kill-server", check=False)

    def test_real_panes_switch_on_hooks_and_jump_keys_never_reach_agent(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            marker = Path(directory) / "socket-path"
            pid, fd = pty.fork()
            if pid == 0:
                fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 36, 110, 0, 0))
                os.environ["TERM"] = "xterm-256color"
                os.execv(sys.executable, [sys.executable, "-m", "agent_dino", "--backend", "tmux", "run", "--",
                                         sys.executable, str(project / "tests/fixture_agent.py"), str(marker)])
            tmux = None
            output = bytearray()

            def drain():
                while select.select([fd], [], [], 0)[0]:
                    try:
                        data = os.read(fd, 65536)
                    except OSError:
                        break
                    if not data:
                        break
                    output.extend(data)

            def until(predicate, timeout=10):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    drain()
                    if predicate():
                        return
                    time.sleep(0.05)
                self.fail("Timed out. Terminal output: " + output[-3000:].decode(errors="replace"))

            try:
                until(marker.exists)
                runtime = Path(marker.read_text()).parent
                config = json.loads((runtime / "session.json").read_text())
                tmux = Tmux(config["tmux"], config["server"])
                agent = config["agent_pane"]
                panes = tmux.call("list-panes", "-F", "#{pane_id}").splitlines()
                game = next(pane for pane in panes if pane != agent)

                def send(text):
                    tmux.call("send-keys", "-t", agent, text, "Enter")

                def capture(pane):
                    return tmux.call("capture-pane", "-p", "-t", pane)

                def active():
                    return tmux.call("display-message", "-p", "#{pane_id}")

                until(lambda: "DINO READY" in capture(game) or "DINO RESTING" in capture(game))
                self.assertEqual(active(), agent)
                send("busy")
                until(lambda: "YOUR AGENT IS WORKING" in capture(game))
                self.assertEqual(active(), game)
                os.write(fd, b" ")
                send("wait")
                until(lambda: "YOUR AGENT NEEDS YOU" in capture(game))
                self.assertEqual(active(), game)
                os.write(fd, b" \r")
                until(lambda: active() == agent)
                # Neither jump nor the handoff Enter becomes agent input.
                self.assertNotIn("received:  ", capture(agent))
                send("resume")
                until(lambda: "YOUR AGENT IS WORKING" in capture(game))
                self.assertEqual(active(), game)
                send("done")
                until(lambda: "DINO RESTING" in capture(game))
                self.assertEqual(tmux.call("display-message", "-p", "-t", game, "#{pane_height}"), "3")
                send("quit")
                until(lambda: not runtime.exists())
                child, status = os.waitpid(pid, 0)
                self.assertEqual(os.waitstatus_to_exitcode(status), 0)
                pid = None
                result = subprocess.run(tmux.prefix + ["list-sessions"], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
            finally:
                if tmux:
                    tmux.call("kill-server", check=False)
                if pid:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    os.waitpid(pid, 0)
                os.close(fd)


if __name__ == "__main__":
    unittest.main()

