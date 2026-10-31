"""CLI launcher for a local terminal game and temporary session data."""

import argparse
import curses
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

from . import __version__
from .adapters import command
from .terminal import Tmux, pane_main, play_demo, run_curses


def find_tmux():
    local = Path(__file__).resolve().parent.parent / ".tools/bin/tmux"
    return shutil.which("tmux") or (str(local) if local.is_file() else None)


def module_command(*args):
    # Use the same interpreter and source tree even when launched from another
    # project, or from an existing tmux server with a different PATH.
    return shlex.join([sys.executable, str(Path(__file__).with_name("boot.py")), *args])


def launch_tmux(options):
    executable = find_tmux()
    if not executable:
        raise RuntimeError("tmux is required. macOS: brew install tmux; Ubuntu/Debian: sudo apt install tmux.")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("Run agent-dino in an interactive terminal (not a pipe). Use 'demo' to try the game.")
    cols, rows = shutil.get_terminal_size()
    if cols < 42 or rows < 24:
        raise RuntimeError("Enlarge your terminal to at least 42 columns and 24 rows.")
    with tempfile.TemporaryDirectory(prefix="dino-", dir="/tmp") as runtime:
        root = Path(runtime)
        server = "agent-dino-" + root.name
        tmux = Tmux(executable, server)
        args = options.args
        if args[:1] == ["--"]:
            args = args[1:]
        argv = command(options.agent, args, root, options.installed_hooks)
        if not shutil.which(argv[0]):
            raise RuntimeError(f"Cannot find {argv[0]!r} on PATH. Install and sign in to your agent first.")
        argv[0] = shutil.which(argv[0])
        try:
            agent_pane = tmux.call("-f", "/dev/null", "new-session", "-d", "-s", "dino",
                                   "-x", str(cols), "-y", str(rows), "-P", "-F", "#{pane_id}",
                                   module_command("_agent", runtime))
            tmux.call("set-option", "-t", "dino", "status", "off")
            tmux.call("set-option", "-t", "dino", "remain-on-exit", "on")
            tmux.call("set-option", "-t", "dino", "prefix", "C-g")
            tmux.call("bind-key", "C-g", "send-prefix")
            tmux.call("bind-key", "-n", "F6", "select-pane", "-t", ":.+")
            tmux.call("set-option", "-g", "exit-empty", "on")
            config = {"tmux": executable, "server": server, "agent_pane": agent_pane,
                      "argv": argv, "auto_only": options.auto_only}
            (root / "session.json").write_text(json.dumps(config))
            tmux.call("split-window", "-d", "-v", "-l", "3", "-t", agent_pane,
                      module_command("_pane", runtime))
            deadline = time.monotonic() + 8
            while not (root / "ready").exists():
                if time.monotonic() > deadline:
                    raise RuntimeError("The game pane did not start. Check that Python has curses support.")
                time.sleep(0.05)
            tmux.call("select-pane", "-t", agent_pane)
            (root / "go").touch()
            env = os.environ.copy()
            env.pop("TMUX", None)
            # A separate server and prefix allow nesting without changing any
            # existing tmux sessions, bindings, or user configuration.
            result = subprocess.run(tmux.prefix + ["attach-session", "-t", "dino"], env=env)
            status = root / "exit-code"
            return int(status.read_text()) if status.exists() else result.returncode
        finally:
            tmux.call("kill-server", check=False)


def launch(options):
    if options.backend == "tmux":
        return launch_tmux(options)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("Run agent-dino in an interactive terminal.")
    try:
        from .pty_terminal import launch_pty
    except ImportError as error:
        raise RuntimeError("Install terminal dependencies with: python3 -m pip install .") from error
    with tempfile.TemporaryDirectory(prefix="dino-", dir="/tmp") as runtime:
        args = options.args[1:] if options.args[:1] == ["--"] else options.args
        argv = command(options.agent, args, runtime, options.installed_hooks)
        executable = shutil.which(argv[0])
        if not executable:
            raise RuntimeError(f"Cannot find {argv[0]!r} on PATH.")
        argv[0] = executable
        return launch_pty(argv, runtime, options.auto_only, agent=options.agent)


def agent_main(runtime):
    root = Path(runtime)
    deadline = time.monotonic() + 12
    while not (root / "go").exists():
        if time.monotonic() > deadline:
            return 1
        time.sleep(0.05)
    config = json.loads((root / "session.json").read_text())
    env = os.environ.copy()
    env["AGENT_DINO_EVENTS"] = str(root / "events")
    os.execvpe(config["argv"][0], config["argv"], env)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Play a dinosaur runner while your coding agent works.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--auto-only", action="store_true", help="Only play for hooks reporting an automatic permission mode")
    parser.add_argument("--installed-hooks", action="store_true", help="Use an already installed plugin instead of injecting session hooks")
    parser.add_argument("--backend", choices=["pty", "tmux"], default="pty", help="Terminal display backend (default: pty; no tmux required)")
    parser.add_argument("agent", choices=["claude", "codex", "demo", "doctor", "status", "run", "install-default", "uninstall-default", "auto", "_pane", "_agent"])
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed unchanged to the agent")
    options = parser.parse_args(argv)
    try:
        if options.agent == "status":
            from .diagnostics import show
            return show()
        if options.agent in {"install-default", "uninstall-default"}:
            from .shell import install, uninstall
            path = install(options.args or ["claude"]) if options.agent == "install-default" else uninstall()
            print(f"Updated {path}. Open a new terminal to apply the change.")
            return 0
        if options.agent == "auto":
            from .shell import should_wrap
            if not options.args or options.args[0] not in {"codex", "claude"}:
                raise ValueError("auto requires codex or claude")
            options.agent, options.args = options.args[0], options.args[1:]
            if not should_wrap(options.agent, options.args):
                os.execvp(options.agent, [options.agent, *options.args])
        if options.agent == "doctor":
            print(f"agent-dino {__version__} | Python {sys.version.split()[0]}")
            for name in ("tmux", "claude", "codex"):
                path = find_tmux() if name == "tmux" else shutil.which(name)
                print(f"{name}: {path or 'not found'}")
            print("Use a local terminal; native Windows and desktop/web chat UIs are not supported.")
            import importlib.util
            available = importlib.util.find_spec("pyte") is not None
            print(f"Default backend: PTY (tmux not required); terminal emulator: {'ready' if available else 'missing pyte'}")
            return 0 if available else 1
        if options.agent == "demo":
            if not sys.stdin.isatty():
                raise RuntimeError("Demo requires an interactive terminal.")
            return run_curses(play_demo)
        if options.agent == "_agent":
            return agent_main(options.args[0])
        if options.agent == "_pane":
            return pane_main(options.args[0])
        if options.agent in {"codex", "claude"}:
            from .shell import should_wrap
            if not should_wrap(options.agent, options.args):
                os.execvp(options.agent, [options.agent, *options.args])
        return launch(options)
    except (RuntimeError, OSError, curses.error, ValueError, subprocess.TimeoutExpired) as error:
        print(f"agent-dino: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

