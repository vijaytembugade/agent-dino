"""A local PTY with an off-screen agent terminal and a dinosaur overlay.

No tmux server, sockets, or shell configuration are needed by this renderer.
Agent output is always consumed, including while the game owns the screen.
"""

import curses
import errno
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import signal
import struct
import sys
import termios
import time
from collections import Counter

import pyte

from .game import Game
from .diagnostics import publish
from .lifecycle import Lifecycle
from .terminal import configure, paint, put, run_curses, set_cursor


class Input:
    """Recognize our keys without corrupting split escapes or bracketed paste."""
    KEYS = (b"\x1b[17~", b"\x1b[A", b"\x1bOA", b"\x1b[200~")

    def __init__(self):
        self.buffer = b""
        self.updated = 0.0

    def feed(self, data=b"", now=None):
        now = time.monotonic() if now is None else now
        if data:
            self.buffer += data
            self.updated = now
        result = []
        while self.buffer:
            if self.buffer.startswith(b"\x1b[200~"):
                end = self.buffer.find(b"\x1b[201~", 6)
                if end < 0:
                    break
                end += 6
                result.append(("paste", self.buffer[:end]))
                self.buffer = self.buffer[end:]
                continue
            key = next((key for key in self.KEYS[:-1] if self.buffer.startswith(key)), None)
            if key is not None:
                result.append(("key", key))
                self.buffer = self.buffer[len(key):]
            elif any(key.startswith(self.buffer) for key in self.KEYS) and now - self.updated < 0.04:
                break
            else:
                result.append(("key", self.buffer[:1]))
                self.buffer = self.buffer[1:]
        return result


class AgentScreen(pyte.Screen):
    def __init__(self, width, height, pending):
        super().__init__(width, height)
        self.pending = pending

    def write_process_input(self, data):
        self.pending.extend(data.encode())

    def report_device_status(self, mode=0, **kwargs):
        super().report_device_status(mode)


class AgentStream:
    """Keep unsupported modern terminal negotiations out of the text buffer.

    pyte implements a VT-style terminal, not the Kitty keyboard protocol or
    DCS/APC graphics. Drop those complete sequences, including across reads.
    Without this, CSI > 1 u can incorrectly appear as literal '1u' in Codex.
    """
    def __init__(self, terminal):
        self.stream = pyte.ByteStream(terminal)
        self.buffer = b""

    def feed(self, data):
        self.buffer += data
        clean = bytearray()
        while self.buffer:
            escape = self.buffer.find(b"\x1b")
            if escape < 0:
                clean.extend(self.buffer)
                self.buffer = b""
                break
            clean.extend(self.buffer[:escape])
            self.buffer = self.buffer[escape:]
            if len(self.buffer) < 2:
                break
            introducer = self.buffer[1:2]
            if introducer == b"[":
                end = next((i for i in range(2, len(self.buffer)) if 0x40 <= self.buffer[i] <= 0x7e), None)
                if end is None:
                    break
                body, final = self.buffer[2:end], self.buffer[end:end+1]
                unsupported = (body[:1] in (b">", b"<", b"=", b"!") or
                               any(0x20 <= c <= 0x2f for c in body) or
                               (body.startswith(b"?") and final not in (b"h", b"l", b"c", b"n")))
                if not unsupported:
                    clean.extend(self.buffer[:end+1])
                self.buffer = self.buffer[end+1:]
            elif introducer in (b"P", b"_", b"^", b"X", b"]"):
                end = self.buffer.find(b"\x1b\\", 2)
                length = 2
                bell = self.buffer.find(b"\x07", 2) if introducer == b"]" else -1
                if bell >= 0 and (end < 0 or bell < end):
                    end, length = bell, 1
                if end < 0:
                    break
                if introducer == b"]":
                    clean.extend(self.buffer[:end+length])
                self.buffer = self.buffer[end+length:]
            else:
                length = 3 if introducer in (b"(", b")", b"*", b"+", b"-", b".", b"/") else 2
                if len(self.buffer) < length:
                    break
                clean.extend(self.buffer[:length])
                self.buffer = self.buffer[length:]
        if clean:
            self.stream.feed(bytes(clean))


def resize(fd, rows, cols):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", max(1, rows), max(1, cols), 0, 0))


class Palette:
    NAMES = {"black": 0, "red": 1, "green": 2, "brown": 3, "blue": 4,
             "magenta": 5, "cyan": 6, "white": 7, "default": -1}

    def __init__(self):
        self.pairs = {}

    def color(self, name):
        if name in self.NAMES:
            return self.NAMES[name]
        if len(name) == 6 and curses.COLORS >= 256:
            try:
                rgb = [int(name[i:i+2], 16) for i in (0, 2, 4)]
                return 16 + 36 * round(rgb[0] * 5 / 255) + 6 * round(rgb[1] * 5 / 255) + round(rgb[2] * 5 / 255)
            except ValueError:
                pass
        return -1

    def style(self, cell):
        style = 0
        if cell.bold:
            style |= curses.A_BOLD
        if cell.italics:
            style |= getattr(curses, "A_ITALIC", 0)
        if cell.underscore:
            style |= curses.A_UNDERLINE
        if cell.reverse:
            style |= curses.A_REVERSE
        if curses.has_colors():
            colors = (self.color(cell.fg), self.color(cell.bg))
            if colors not in self.pairs and len(self.pairs) + 3 < curses.COLOR_PAIRS:
                pair = len(self.pairs) + 3
                curses.init_pair(pair, *colors)
                self.pairs[colors] = pair
            style |= curses.color_pair(self.pairs.get(colors, 0))
        return style


def draw_agent(window, terminal, palette, state, focus, agent=None):
    rows, cols = window.getmaxyx()
    window.erase()
    for y in range(min(terminal.lines, rows - 2)):
        for x, cell in terminal.buffer[y].items():
            if x < cols - 1 and cell.data:
                try:
                    window.addstr(y, x, cell.data, palette.style(cell))
                except curses.error:
                    pass
    if focus == "handoff":
        label = "DINO PAUSED | Agent needs you / finished. Enter, Esc or F6 to type."
    elif state.status == "busy":
        label = "AGENT WORKING | F6: play dinosaur | Ctrl-C: interrupt"
    elif not state.seen_hook and agent == "codex":
        label = "DINO READY | Codex: review hooks with /hooks | F6: manual play"
    elif not state.seen_hook:
        label = "DINO CONNECTING | Waiting for agent hooks | F6: manual play"
    else:
        label = "DINO READY | Hooks connected | Send a prompt to play | F6: manual play"
    put(window, rows - 2, 0, "-" * cols, curses.color_pair(2))
    put(window, rows - 1, 0, label, curses.color_pair(1))
    cursor = terminal.cursor
    if focus == "agent" and not cursor.hidden:
        set_cursor(1)
        window.move(min(cursor.y, rows - 3), min(cursor.x, cols - 1))
    else:
        set_cursor(0)
    window.refresh()


def reap(pid, force=False):
    found, status = os.waitpid(pid, os.WNOHANG)
    if found:
        return os.waitstatus_to_exitcode(status)
    if not force:
        return None
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        found, status = os.waitpid(pid, os.WNOHANG)
        if found:
            return os.waitstatus_to_exitcode(status)
        time.sleep(0.02)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status)


def session(window, argv, root, auto_only, agent=None):
    configure(window)
    rows, cols = window.getmaxyx()
    inbox = root / "events"
    inbox.mkdir(mode=0o700)
    pending = bytearray()
    terminal = AgentScreen(cols, max(1, rows - 2), pending)
    stream = AgentStream(terminal)
    state = Lifecycle(auto_only)
    game = Game()
    palette = Palette()
    keyboard = Input()
    focus = "agent"
    last_frame = time.monotonic()
    last_status_write = 0.0
    event_counts = Counter()
    last_event = None
    status = None
    pid, master = pty.fork()
    if pid == 0:
        try:
            resize(0, rows - 2, cols)
            env = {**os.environ, "AGENT_DINO_EVENTS": str(inbox),
                   "AGENT_DINO_ACTIVE": "1", "TERM": "xterm-256color"}
            os.execvpe(argv[0], argv, env)
        except Exception as error:
            os.write(2, f"Unable to start agent: {error}\r\n".encode())
            os._exit(127)
    os.set_blocking(master, False)
    stdin = sys.stdin.fileno()
    # Paste is forwarded intact to the agent and ignored by the game.
    sys.stdout.write("\x1b[?2004h")
    sys.stdout.flush()
    closed = False
    try:
        while True:
            now = time.monotonic()
            # curses notices SIGWINCH during getch, but input here is read raw.
            actual = os.get_terminal_size(stdin)
            if actual.lines > 0 and actual.columns > 0 and (rows, cols) != (actual.lines, actual.columns):
                rows, cols = actual.lines, actual.columns
                curses.resizeterm(rows, cols)
                terminal.resize(lines=max(1, rows - 2), columns=cols)
                resize(master, rows - 2, cols)
            before = state.status
            for path in sorted(inbox.glob("*.json"))[:100]:
                try:
                    event = json.loads(path.read_text())
                    state.handle(event)
                    if isinstance(event, dict) and isinstance(event.get("hook_event_name"), str):
                        last_event = event["hook_event_name"]
                        event_counts[last_event] += 1
                except (OSError, ValueError):
                    pass
                finally:
                    path.unlink(missing_ok=True)
            if state.status != before:
                if state.status == "busy":
                    focus = "game"
                elif focus == "game":
                    focus = "handoff"
            if now - last_status_write >= 0.5:
                try:
                    publish(root, agent, focus, state, event_counts, last_event)
                except OSError:
                    pass  # Diagnostics must never terminate the agent session.
                last_status_write = now
            readable, writable, _ = select.select(
                [stdin] + ([] if closed else [master]),
                [master] if pending and not closed else [], [], 1 / 30)
            if master in readable:
                try:
                    output = os.read(master, 65536)
                    if output:
                        stream.feed(output)
                    else:
                        closed = True
                except OSError as error:
                    if error.errno == errno.EIO:
                        closed = True
                    elif error.errno != errno.EAGAIN:
                        raise
            if master in writable:
                try:
                    sent = os.write(master, pending)
                    del pending[:sent]
                except BlockingIOError:
                    pass
                except OSError as error:
                    if error.errno == errno.EIO:
                        closed = True
                    else:
                        raise
            data = os.read(stdin, 65536) if stdin in readable else b""
            if stdin in readable and not data:
                raise KeyboardInterrupt
            for kind, key in keyboard.feed(data):
                if key == b"\x1b[17~" and kind == "key":
                    focus = "agent" if focus in {"game", "handoff"} else "game"
                elif focus == "agent":
                    if kind == "paste" and (2004 << 5) not in terminal.mode:
                        pending.extend(key[6:-6])
                    else:
                        pending.extend(key)
                elif kind == "paste":
                    continue
                elif key in {b"\r", b"\n", b"\x1b"}:
                    focus = "agent"
                elif key == b"\x03":
                    pending.extend(key)
                    focus = "agent"
                elif focus == "game":
                    if key in {b" ", b"\x1b[A", b"\x1bOA"}:
                        game.jump()
                    elif key.lower() == b"r":
                        game.reset()
            if focus == "game":
                if cols >= 42 and rows >= 11:
                    game.tick(now - last_frame, cols)
                # Manual play is available before hooks have been trusted.
                view = Lifecycle()
                view.status = "busy"
                set_cursor(0)
                paint(window, game, view)
            else:
                draw_agent(window, terminal, palette, state, focus, agent)
            last_frame = now
            if status is None:
                status = reap(pid)
            if status is not None and closed:
                return status, "\n".join(terminal.display).rstrip()
    finally:
        sys.stdout.write("\x1b[?2004l")
        sys.stdout.flush()
        if status is None:
            reap(pid, force=True)
        os.close(master)


def launch_pty(argv, runtime, auto_only=False, agent=None):
    def terminate(signum, frame):
        raise KeyboardInterrupt

    old_handler = signal.signal(signal.SIGTERM, terminate)
    try:
        status, last_screen = run_curses(session, argv, Path(runtime), auto_only, agent)
    finally:
        signal.signal(signal.SIGTERM, old_handler)
    if last_screen:
        print(last_screen)
    return status if status >= 0 else 128 - status
