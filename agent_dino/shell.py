"""Reversible default launch integration for interactive zsh and bash."""

import os
from pathlib import Path
import shlex
import shutil
import sys
import time

START = "# >>> agent-dino managed defaults >>>"
END = "# <<< agent-dino managed defaults <<<"
COMMANDS = {
    "codex": {"agents", "exec", "e", "review", "login", "logout", "mcp", "plugin", "app-server",
              "remote-control", "app", "completion", "update", "doctor", "sandbox", "debug", "apply",
              "queue", "archive", "delete", "migrate-rollouts", "migrate-nfs-db", "unarchive", "cloud",
              "exec-server", "features", "help"},
    "claude": {"agents", "auth", "auto-mode", "doctor", "gateway", "import", "install", "logs", "mcp",
               "plugin", "plugins", "purge", "respawn", "rm", "setup-token", "stop", "kill", "update", "upgrade"},
}
VALUES = {"-c", "--config", "-C", "--cd", "-m", "--model", "-p", "--profile", "-a", "--ask-for-approval",
          "-s", "--sandbox", "--enable", "--disable", "--add-dir", "--local-provider", "--effort", "--settings",
          "--permission-mode", "--agent", "--name", "-n", "--system-prompt", "--append-system-prompt"}


def should_wrap(agent, args, interactive=None):
    if interactive is None:
        interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if not interactive or os.environ.get("AGENT_DINO_ACTIVE") or os.environ.get("AGENT_DINO_OFF"):
        return False
    switches = {"-h", "--help", "--version", "-V", "--remote", "--desktop", "--cloud", "--bg", "--background"}
    if agent == "claude":
        switches.update({"-p", "--print", "-v"})
    if any(arg.split("=", 1)[0] in switches for arg in args):
        return False
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg == "--":
            return True
        elif arg in VALUES:
            skip = True
        elif not arg.startswith("-"):
            return arg not in COMMANDS[agent]
    return True


def without_block(text):
    if START not in text:
        return text
    start = text.index(START)
    if END not in text[start:]:
        raise ValueError("Incomplete Agent Dino block in shell configuration; no changes made.")
    end = text.index(END, start) + len(END)
    if text[end:end+1] == "\n":
        end += 1
    return text[:start] + text[end:]


def rc_path(home=None, shell=None):
    shell = Path(shell or os.environ.get("SHELL", "/bin/zsh")).name
    home = Path(home or Path.home())
    if shell == "zsh":
        return Path(os.environ.get("ZDOTDIR", str(home))) / ".zshrc"
    if shell == "bash":
        return home / ".bashrc"
    raise ValueError("Automatic shell installation supports zsh and bash.")


def block(agents):
    entry = shlex.join([sys.executable, str(Path(__file__).with_name("boot.py")), "auto"])
    lines = [START]
    for agent in agents:
        if agent not in {"codex", "claude"}:
            raise ValueError(f"Unsupported agent: {agent}")
        lines += [f"function {agent} {{",
                  '  if [[ -n "${AGENT_DINO_ACTIVE:-}${AGENT_DINO_OFF:-}" || ! -t 0 || ! -t 1 ]]; then',
                  f'    command {agent} "$@"', "  else",
                  f'    {entry} {agent} "$@"', "  fi", "}"]
    return "\n".join(lines + [END, ""])


def update(path, content):
    if path.exists() and path.read_text() == content:
        return path
    if path.exists():
        backup = path.with_name(path.name + f".agent-dino-backup-{time.time_ns()}")
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def install(agents, path=None):
    path = Path(path) if path is not None else rc_path()
    original = path.read_text() if path.exists() else ""
    clean = without_block(original).rstrip("\n")
    return update(path, clean + ("\n\n" if clean else "") + block(agents))


def uninstall(path=None):
    path = Path(path) if path is not None else rc_path()
    if path.exists():
        update(path, without_block(path.read_text()))
    return path
