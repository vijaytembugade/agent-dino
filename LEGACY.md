# Legacy terminal wrapper (0.2.3)

These instructions describe the optional older Python adapter. For native Claude installation, use [README.md](README.md).

# Agent Dino

A terminal dinosaur runner for the time between your prompt and the agent's answer.
Version 0.2 runs directly in your terminal. **tmux is no longer required.**

## Install and enable by default

Requires macOS or Linux (including WSL), Python 3.10+ with curses, and a recent
Claude Code or Codex CLI. The terminal renderer uses `pyte` and `wcwidth`.

From this checkout:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
./agent-dino install-default
```

Open a **new terminal**, then use your normal Claude command, from any project:

```sh
claude
```

The installer adds a reversible block to `.zshrc` or `.bashrc`, with a backup
before changing the file. It enables Claude by default. Running
`./agent-dino install-default claude` also removes this tool's Codex wrapper
from the managed block. Optional Codex support remains available explicitly.

Claude's hooks are supplied automatically to the launched session. Submit a
prompt to start the game, or press F6 to try it immediately. Codex's hook-trust
instructions below do not apply to the Claude setup.

Only interactive sessions are wrapped. Help/version commands, `codex exec`,
Claude's `--print`, management commands, piped commands, and agent subprocesses
pass through. Your working directory and arguments are kept.

For a one-off plain session: `AGENT_DINO_OFF=1 claude`.
To undo: `/path/to/agent-dino/agent-dino uninstall-default`, then open a new terminal.

You can also run without changing shell defaults:

```sh
./agent-dino demo
./agent-dino codex
./agent-dino claude
```

The checkout executable uses its `.venv` when available. For a global command,
`pipx install /path/to/agent-dino` is also supported. This project has not been
published to PyPI or a public plugin marketplace.

## Codex's one-time hook review

Codex requires non-managed hooks to be trusted before they run. If it shows a
hook-review warning, open **`/hooks`**. This first shows a table of events, not
plugin names. Select **UserPromptSubmit**, press **Enter**, select **Agent Dino**,
and press **T** to trust that hook. Repeat for the Agent Dino hooks under
PreToolUse, PermissionRequest, PostToolUse, SessionStart, SessionEnd, Stop, and
Interrupt. The command must point to this project's `agent_dino/hook.py`.

If all hooks needing review belong to Agent Dino, **T** on the first event table
trusts all of them. Do not use trust-all for other commands you have not reviewed.
Older launches label these entries **Unnamed hook**; exit and start a fresh
`codex` session to load the current display names. If every Installed count is
zero, the session was not started with Agent Dino's hooks. Launch it explicitly
with `/path/to/agent-dino/agent-dino codex`.

Changed definitions may require another review. The launcher does not bypass
hook trust, tool permissions, or sandbox settings.

Before hook approval, **F6** can open the game manually. Automatic play requires
enabled, trusted lifecycle hooks. The status strip explains this. `--no-daemon`
keeps Codex and its event inbox in the same process tree.

Adapters use the documented interfaces in Codex 0.165.0 and Claude Code 2.1.314.
Older versions may not implement all events. This tool wraps local CLI sessions;
it does not modify desktop, web, IDE, remote daemon, or cloud interfaces.

## Playing

Submit a prompt and the game appears while the agent runs in a separate local
PTY. Agent output is continuously read into an off-screen terminal. When the agent
finishes or asks for permission, its screen comes back. Press Enter, Escape, or
F6 to hand the keyboard back. This prevents a held jump key from answering a
permission dialog. F6 also switches views whenever you want.

| Key | Action |
| --- | --- |
| Space / Up | Jump; restart after a collision |
| R | Restart the run |
| Escape / Enter | Return from game to agent |
| F6 | Toggle agent/game; dismiss the keyboard handoff |
| Ctrl-C in game | Interrupt the agent and show it |
| Q in standalone demo | Quit the demo |

Scores last for the current launch. The game pauses in small terminals while the
agent keeps running. At least 80 columns by 24 rows is comfortable. Bracketed paste
is forwarded to the agent and ignored by the game.

## Auto mode

Default behavior is to play during every active turn, including autonomous work.
Your normal options still apply:

```sh
codex --approve-for-me
claude --permission-mode auto
```

To activate only when hooks report an automatic permission mode:

```sh
./agent-dino --auto-only claude --permission-mode auto
```

`--auto-only` recognizes `auto`, `dontAsk`, `bypassPermissions`, and `never`.
Codex's automatic approval review may report `default`; use ordinary activation
for that mode. Activity follows lifecycle events, not private model reasoning.

## Native plugin packages

Manifests, hooks, and local marketplace catalogs for both agents are included.
The launcher supplies the display and keyboard handling; the plugins supply
lifecycle events. Hook installation alone cannot draw over an existing agent UI.

Claude local development:

```sh
./agent-dino --installed-hooks claude --plugin-dir /path/to/agent-dino
```

Claude marketplace installation:

```sh
claude plugin marketplace add /path/to/agent-dino
claude plugin install agent-dino@agent-dino-local
./agent-dino --installed-hooks claude
```

Codex marketplace installation:

```sh
codex plugin marketplace add /path/to/agent-dino
codex plugin add agent-dino@agent-dino-local
./agent-dino --installed-hooks codex
```

Use `--installed-hooks` for manually installed plugins to avoid duplicate handlers.
The default shell integration uses session-scoped hooks and needs no native plugin
installation. Plugin hooks do nothing outside an Agent Dino session. Their scripts
use `python3` from PATH. Review/trust Codex plugin hooks through `/hooks`.

## Other agents and optional tmux

`agent-dino run -- your-agent` wraps another terminal application. For automatic
activation it must invoke `agent_dino/hook.py` with lifecycle JSON on stdin,
inheriting the `AGENT_DINO_EVENTS` environment variable:

```sh
printf '%s\n' '{"session_id":"my-session","hook_event_name":"UserPromptSubmit"}' \
  | python3 /path/to/agent-dino/agent_dino/hook.py
```

Send `SessionStart`, `UserPromptSubmit`, `PermissionRequest`, `PostToolUse`,
`Stop`, and `SessionEnd` as appropriate, with a consistent `session_id`.
There is no universal thinking signal for arbitrary AI tools.

The older split-pane renderer is available with `agent-dino --backend tmux codex`.
It requires tmux 3.2+, permits viewing both screens at once, and uses an isolated
server. Ctrl-G then D exits that managed session. This backend is optional.

## Testing and limitations

If Claude accepts a prompt but no game appears, check the bottom strip. It says
`DINO CONNECTING` until a hook arrives, then `DINO READY | Hooks connected`.
An existing Claude session cannot pick up a newly installed terminal wrapper.
To eliminate shell setup differences, start a fresh session explicitly:

```sh
~/Code/agent-dino/agent-dino claude
```

While that session is open, this command in another terminal reports its view,
received event counts, and whether an event was ignored:

```sh
~/Code/agent-dino/agent-dino status
```

Status is temporary metadata only; it contains no prompts or answers. Sessions
started before the status feature was added must be restarted to report status.
On a Mac with media-key defaults, use **Fn+F6** for the manual game shortcut.

```sh
./agent-dino doctor
.venv/bin/python -m unittest discover -s tests -v
claude plugin validate .
```

Tests cover collisions, concurrent hooks, permission pauses, session isolation,
stale turns, keyboard/paste handling, terminal restoration, shell installation,
and command passthrough. The default renderer's integration test runs a local
fake agent in a real PTY and checks automatic activation, keyboard handoff,
resizing, exit status, and temporary-file cleanup. A separate test checks the
plain `codex` shell command. These tests need no AI account or network. The
optional tmux test skips when sockets are prohibited.

The default renderer emulates common ANSI output. Advanced graphics, Kitty
keyboard enhancements, and mouse-driven agent interaction are not supported.
Unsupported negotiation sequences are filtered out of the prompt display.

Hooks disabled by agent policy or safe/bare modes cannot trigger automatic play.
Continuations without prompt events and Claude interruptions without Stop events
may require F6. A Stop hook that immediately continues can briefly pause the game.

Only lifecycle metadata is written to a private temporary inbox. Prompts, answers,
tool inputs, and transcripts are not copied there. Agent screen contents stay in
memory. Events are consumed and deleted; the inbox is removed on exit. The game
makes no network requests and uses your agent's normal authentication.

References: [Codex hooks](https://developers.openai.com/codex/hooks),
[Codex plugin packaging](https://developers.openai.com/codex/plugins/build),
[Claude hooks](https://code.claude.com/docs/en/hooks).

Original ASCII artwork, inspired by Chrome's offline game. MIT licensed.
Not affiliated with Google, Anthropic, or OpenAI.
