"""Curses game pane and tmux integration. The agent keeps its own real TTY."""

import curses
import json
import os
from pathlib import Path
import subprocess
import sys
import termios
import time

from .game import CACTUS, DINO, DINO_X, Game
from .lifecycle import Lifecycle


class Tmux:
    def __init__(self, executable="tmux", server=None):
        self.prefix = [executable] + (["-L", server] if server else [])

    def call(self, *args, check=True):
        result = subprocess.run(self.prefix + list(args), text=True, capture_output=True, timeout=3)
        if check and (result.returncode or result.stderr.startswith("error ")):
            raise RuntimeError(result.stderr.strip() or "tmux command failed")
        return result.stdout.strip()


def run_curses(function, *args):
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        return curses.wrapper(function, *args)
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, saved)


def put(screen, y, x, text, style=0):
    height, width = screen.getmaxyx()
    if 0 <= y < height and x < width - 1:
        if x < 0:
            text, x = text[-x:], 0
        try:
            screen.addnstr(y, x, text, max(0, width - x - 1), style)
        except curses.error:
            pass


def paint(screen, game, lifecycle, demo=False):
    height, width = screen.getmaxyx()
    screen.erase()
    accent = curses.color_pair(1) | curses.A_BOLD
    muted = curses.color_pair(2)
    if width < 42 or (lifecycle.status == "busy" and height < 11):
        put(screen, 0, 1, "DINO | Enlarge terminal (42 x 24 minimum).", accent)
        put(screen, 1, 1, "Esc / F6: back to agent. Game paused.", muted)
        screen.refresh()
        return
    if lifecycle.status != "busy":
        if lifecycle.status == "waiting":
            text = "YOUR AGENT NEEDS YOU  |  Enter / Esc / F6: return to agent"
        elif lifecycle.seen_hook:
            text = "DINO RESTING  |  Enter / Esc / F6: agent  |  starts with your next prompt"
        else:
            text = "DINO READY  |  submit a prompt to play  |  F6 switches panes"
        put(screen, 0, 1, text, accent)
        put(screen, 1, 1, f"Best this session: {game.best:05d}  |  F6 switches panes", muted)
        screen.refresh()
        return
    title = "DINO / DEMO" if demo else "DINO / YOUR AGENT IS WORKING"
    put(screen, 0, 2, title, accent)
    score = f"HI {game.best:05d}   {game.score:05d}"
    put(screen, 0, max(len(title) + 5, width - len(score) - 3), score, muted)
    ground = height - 3
    for y, row in enumerate(DINO):
        put(screen, ground - len(DINO) - round(game.height) + y, DINO_X, row, accent)
    for obstacle in game.obstacles:
        for y, row in enumerate(CACTUS):
            put(screen, ground - len(CACTUS) + y, round(obstacle.x), row, accent)
    offset = int(game.distance) % 5
    put(screen, ground, 0, ("_" * width), muted)
    put(screen, ground + 1, 0, ("  .  " * (width // 5 + 1))[offset:offset + width], muted)
    help_text = "SPACE / UP: jump   R: restart   Esc / F6: agent   Ctrl-C: interrupt agent"
    if demo:
        help_text = "SPACE / UP: jump   R: restart   Q: quit demo"
    put(screen, height - 1, 2, help_text, muted)
    if game.over:
        message = " GAME OVER - SPACE TO RUN AGAIN "
        put(screen, max(2, ground - 7), max(0, (width - len(message)) // 2), message, curses.A_REVERSE)
    screen.refresh()


def configure(screen):
    curses.raw()
    set_cursor(0)
    screen.nodelay(True)
    screen.keypad(True)
    if hasattr(curses, "set_escdelay"):
        curses.set_escdelay(25)
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_CYAN, -1)


def set_cursor(visibility):
    try:
        curses.curs_set(visibility)
    except curses.error:
        pass


def play_demo(screen):
    configure(screen)
    lifecycle = Lifecycle()
    lifecycle.status = "busy"
    game = Game()
    previous = time.monotonic()
    while True:
        now = time.monotonic()
        height, width = screen.getmaxyx()
        if height >= 11 and width >= 42:
            game.tick(now - previous, width)
        previous = now
        key = screen.getch()
        if key in (ord("q"), ord("Q"), 27, 3):
            return 0
        if key in (32, curses.KEY_UP):
            game.jump()
        if key in (ord("r"), ord("R")):
            game.reset()
        paint(screen, game, lifecycle, demo=True)
        time.sleep(1 / 30)


def play_pane(screen, runtime):
    configure(screen)
    root = Path(runtime)
    config = json.loads((root / "session.json").read_text())
    tmux = Tmux(config["tmux"], config["server"])
    agent = config["agent_pane"]
    pane = os.environ["TMUX_PANE"]
    lifecycle = Lifecycle(config["auto_only"])
    game = Game()
    previous = time.monotonic()
    last_check = 0.0
    inbox = root / "events"
    inbox.mkdir(mode=0o700)
    try:
        (root / "ready").touch()
        while True:
            now = time.monotonic()
            # Drain a bounded batch so a busy agent cannot starve the frame loop.
            before = lifecycle.status
            for path in sorted(inbox.glob("*.json"))[:100]:
                try:
                    event = json.loads(path.read_text())
                except (OSError, ValueError, UnicodeError):
                    continue
                finally:
                    path.unlink(missing_ok=True)
                lifecycle.handle(event)
            if lifecycle.status != before:
                desired_height = 15 if lifecycle.status == "busy" else 3
                tmux.call("resize-pane", "-t", pane, "-y", str(desired_height), check=False)
                if lifecycle.status == "busy":
                    tmux.call("select-pane", "-t", pane, check=False)
                # On completion, retain game focus until Enter/Esc/F6. This
                # prevents a held jump key from approving a tool or entering text.
            if now - last_check > 0.5:
                last_check = now
                state = tmux.call("display-message", "-p", "-t", agent,
                                  "#{pane_dead}:#{pane_dead_status}", check=False)
                if state.startswith("1:") or not state:
                    status = state.partition(":")[2]
                    (root / "exit-code").write_text(status if status.isdigit() else "1")
                    return 0
            height, width = screen.getmaxyx()
            if lifecycle.status == "busy" and height >= 11 and width >= 42:
                game.tick(now - previous, width)
            previous = now
            key = screen.getch()
            if key in (10, 13, 27, ord("q")):
                tmux.call("select-pane", "-t", agent, check=False)
            elif key == 3:
                lifecycle.status = "waiting"
                tmux.call("resize-pane", "-t", pane, "-y", "3", check=False)
                tmux.call("send-keys", "-t", agent, "C-c", check=False)
                tmux.call("select-pane", "-t", agent, check=False)
            elif key in (32, curses.KEY_UP) and lifecycle.status == "busy":
                game.jump()
            elif key in (ord("r"), ord("R")) and lifecycle.status == "busy":
                game.reset()
            paint(screen, game, lifecycle)
            time.sleep(1 / 30)
    finally:
        for path in inbox.iterdir():
            path.unlink(missing_ok=True)


def pane_main(runtime):
    root = Path(runtime)
    try:
        return run_curses(play_pane, runtime)
    finally:
        # An unexpected game failure must give the terminal back, never leave
        # a broken game selected while the agent waits for input.
        config = json.loads((root / "session.json").read_text())
        tmux = Tmux(config["tmux"], config["server"])
        if (root / "exit-code").exists():
            tmux.call("kill-session", "-t", "dino", check=False)
        else:
            tmux.call("select-pane", "-t", config["agent_pane"], check=False)

