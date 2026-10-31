# Agent Dino implementation

The primary product is the native Claude plugin, version 1.0.3.

| File | Purpose |
| --- | --- |
| `.claude-plugin/plugin.json` | Native Claude plugin manifest |
| `.claude-plugin/marketplace.json` | Installable local marketplace |
| `hooks/hooks.json` | Loads the native JavaScript module |
| `hooks/register.js` | Commands, saved enabled state, timers, native UI and lifecycle |
| `hooks/games/index.js` | Game catalog shown by `/dino on` |
| `hooks/games/dino.js` | Dino Run: physics, random obstacles, collision and drawing |
| `hooks/games/copter.js` | Copter: thrust and gravity, scrolling walls with reachable gaps |
| `native-tests/dino.test.ts` | Tests through Claude's native mod test runner |

`session.start` loads the plugin-scoped saved setting (default on) and registers
immediate slash commands. Exact enable/disable phrases are consumed by
`prompt.submit`. Main turns start a 50 ms simulation timer and display the game
in `AbovePrompt`; completion stops automatic play. `/dino play` opens a focused
native pane, including on narrow terminals. UI drawing composes with other mods.

Permission decisions and question results pass through unchanged. Pending input
pauses simulation; tool completion or turn completion clears the pause. Gating
hooks use replay-safe fail-open catch handlers, so a game error does not prevent
Claude from handling the event. Disabling or ending the session cancels timers.
The module makes no network, process, filesystem or model calls; only the enabled
setting persists in Claude's plugin store. Scores remain in memory.

The Python package and Codex adapter are retained at 0.2.3 for compatibility.
Their hook manifest is `hooks/legacy-claude.json` (Claude) or `hooks/codex.json`
(Codex). They are not used by the native Claude plugin. See [LEGACY.md](LEGACY.md)
for that architecture's installation and controls.
