# Agent Dino

A native dinosaur game inside Claude Code. Install once, start `claude` normally,
and the game appears above the prompt while Claude works, including auto mode.
Enabled by default; no launcher, Python environment, or shell wrapper is required.

## Install

Requires Claude Code **2.1.287 or newer**, with native mods enabled.
From this checkout:

```sh
claude plugin marketplace add .
claude plugin install agent-dino@agent-dino-local --scope user
```

In an already open Claude session, run `/reload-plugins`, or restart Claude normally.
You should see `Agent Dino ON` above the prompt. Submit a work prompt to start the
game automatically, or use `/dino play` to try it immediately.

This is a local plugin; it has not been published to a public marketplace.
To share it, distribute the native plugin archive, extract it, and run the same
installation commands from the extracted directory.

## Controls inside Claude

| Command | Action |
| --- | --- |
| `/dino on` | Lists the games above the prompt; press its number to pick. Saved until `/dino off` |
| `/dino on <game>` | Pick a game directly, e.g. `/dino on dino` |
| `/dino off` | Disable immediately and forget the pick; the next `/dino on` asks again |
| `/dino play` | Play now, without waiting for Claude (again to stop) |
| `/dino split` | Play in a separate split pane instead; `/dino split off` goes back |
| `/dino status` | Show the saved setting and current activity |
| `/enable-dino`, `/disable-dino` | Shortcuts for on/off |

`/agent-dino` is an alias for `/dino`. You can also type **enable dino**,
**disable dino**, **enable agent-dino**, or **disable agent-dino** as an ordinary
prompt. These exact controls run locally without a model call. Prompts that merely
mention the controls are sent to Claude normally.

The game plays right above the prompt while Claude works. Press **Space** to jump
(it also restarts after a crash) — no clicking needed: Space in an empty prompt goes
to the game, and anything else you type goes to the prompt as usual. **1** jumps and
**2** restarts too; in `/dino play`, **3** stops.

With `/dino split`, the game opens in its own pane instead, takes the keyboard
while Claude works (**Enter** or **j** to jump, **r** to restart, **Escape** to skip
the turn), and hands it back when Claude finishes or needs your answer.
Scores last for the current session.

**Uses no tokens.** The games run entirely on your machine. They make no model,
network, or shell calls and add nothing to the system prompt or the conversation.
`/dino` replies show as short notifications instead of transcript lines, because
Claude would read a transcript line on your next turn. Typed controls like
"enable dino" are handled locally and never sent to Claude.

The automatic game stops when Claude finishes. It pauses for permission requests
and questions, without changing their answers or permission decisions. Other
plugins' content above the prompt is preserved. It follows turn activity rather
than attempting to read private model reasoning.

## Troubleshooting

- Run `/dino status`; use `/dino on` if it was previously disabled.
- Run `/reload-plugins` after installing, or restart `claude`.
- Check `claude plugin list` for enabled `agent-dino@agent-dino-local`.
- Update Claude if native mods are unsupported. A policy disabling plugins or
  mods must be handled through your normal administrator process.
- A short terminal can leave too little space for the automatic game; enlarge
  it or use `/dino play`. A terminal of 80 columns by 24 rows is recommended.
- If you installed the old Python shell integration, run
  `./agent-dino uninstall-default` once. An existing shell can retain the old
  function until a new terminal is opened or `unfunction claude` is run in zsh.

## Adding a game

1. Write `hooks/games/<id>.js` exporting a class with `action()`, `reset()`,
   `tick(seconds)`, `frame(columns, rows)` (returns `rows` lines of text) and the
   fields `over`, `score`, `best`. `hooks/games/dino.js` is a complete example.
2. Add one entry to `GAMES` in `hooks/games/index.js`: `id`, `name`,
   `description`, `actionLabel` (the button, e.g. `Jump`) and `hotkey` (one letter).
3. Run `claude plugin test .`. The game now shows up in `/dino on`.

Each game gets a single action button, so it plays the same in the pane and above
the prompt. Keep games pure: no files, network, or processes.

## Security

Read [SECURITY.md](SECURITY.md) before contributing. Every PR is checked against it
automatically; run the same check locally with `git config core.hooksPath .githooks`
(once), or `node scripts/security-check.mjs`.

## Development

```sh
claude plugin validate .
claude plugin test .
```

`hooks/register.js` implements native commands, lifecycle handling, UI, and the
saved setting. Games live in `hooks/games/`: `dino.js` is the dinosaur run, `copter.js` the helicopter, and
`index.js` is the catalog the `/dino on` list is built from. `native-tests/dino.test.ts` tests the actual mod using Claude's test
runner, without an AI account or network. No npm dependencies are required.
The native game makes no network, shell, or model calls.

Claude native plugin version: **1.3.1**. The older Python adapter remains at
**0.2.3** and is documented separately in [LEGACY.md](LEGACY.md). Codex support
currently uses that optional legacy adapter; this native UI implementation is
for Claude Code.

[Claude mods documentation](https://code.claude.com/docs/en/plugins/mods/overview).
Original ASCII artwork inspired by Chrome's offline game. MIT licensed.
Not affiliated with Google, Anthropic, or OpenAI.
