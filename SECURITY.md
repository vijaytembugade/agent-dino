# Security

Agent Dino runs inside people's Claude Code sessions, next to their code, their
permissions and their tokens. Anyone can propose a change, so every change is held
to the rules below. **They are checked automatically: on your computer before every
push, and again on every pull request.**

## Reporting a vulnerability

Please do not open a public issue. Report it privately through
**GitHub → Security → Report a vulnerability** on this repository. Include the
version (`/dino status`), what you found, and how to reproduce it. We aim to reply
within 7 days and to publish a fix before disclosing details.

## What Agent Dino may and may not do

The plugin is a game. It draws in the terminal, remembers a few settings, and
watches when Claude starts and stops working. That is all it is allowed to do.

| Allowed | Never |
| --- | --- |
| Draw above the prompt or in its own pane | Call a model, or add anything Claude reads (`context`, system prompt). **The game must cost users zero tokens.** |
| Store `enabled`, `game` and `split` with `$.store` | Make network requests, or contain URLs in plugin code |
| Read Claude's turn and tool events to pause and resume | Approve, deny or rewrite a permission decision or a tool call |
| Catch a **Space** typed into an **empty** prompt while a game runs | Read, keep or change any other prompt text; drop any prompt except the exact "enable/disable dino" controls |
| Clear its own exact control text from the prompt | Run processes, read or write files, or use `eval`, `Function`, `require` or dynamic `import()` |
| | Depend on npm packages, or ship binaries, archives or minified code |
| | Draw anything that imitates Claude Code's own permission or question dialogs |

## Rules for contributors

1. **Games are pure.** A file in `hooks/games/` only simulates and returns text
   from `frame()`. It must not use `$`, `on`, timers of its own, or import anything
   outside `hooks/games/`. This keeps a new game unable to harm anyone, even if
   its author meant to.
2. **The engine allowlist is closed.** `hooks/register.js` may only call the
   `$.…` methods and hook the events listed in `scripts/security-check.mjs`
   (`ALLOWED_CALLS`, `ALLOWED_EVENTS`). Needing a new one is a design change; open
   an issue first.
3. **Observe, never decide.** `tool.check` and `tool.call` hooks return exactly
   what `next(e)` returned. The tests in `native-tests/` prove decisions and
   answers pass through unchanged; keep them passing.
4. **Zero tokens.** Command replies go to `$.ui.toast`, never into the
   transcript. Nothing returns `context`.
5. **No dependencies.** No `package.json` dependencies, no install scripts,
   no vendored or minified code. Write the few lines instead.
6. **Source only.** No binaries or archives in the repository (`dist/` and
   `build/` are ignored). The only images are `.claude-plugin/icon.png` and
   screenshots in `docs/` (PNG, JPEG or GIF), shown by the README.
7. **No secrets**, not even "test" keys that look real.
8. **Legacy Python adapter** (`agent_dino/`): no network modules, `pickle`,
   `eval`/`exec`, `os.system` or `shell=True`. It may run tmux and a pty because
   that is its job; keep commands as argument lists.
9. **Write it plainly.** Code a reviewer cannot read quickly (encoded strings,
   clever indirection, one-letter names across a file) will be rejected even if
   the check passes.

## How the checks run

| Where | When | What |
| --- | --- | --- |
| Your computer | `git push` | `.githooks/pre-push` |
| GitHub | every pull request and push to `main` | `.github/workflows/security.yml` |

Both run the same three steps:

```sh
node scripts/security-check.test.mjs   # proves every rule still catches what it should
node scripts/security-check.mjs        # the rules above, then claude plugin validate + test
```

Turn on the local check once per clone:

```sh
git config core.hooksPath .githooks
```

You need Node 18+ and Claude Code (`claude`). `node scripts/security-check.mjs --static`
runs the rules without Claude Code. The tests need no account and no network.

## What a reviewer still checks by hand

The script catches the known-bad; people catch the clever. On every PR, check:

- [ ] Every changed line in `hooks/register.js`: does it still only observe Claude's events?
- [ ] `prompt.submit` and `prompt.edit` still touch only the exact controls and a Space in an empty prompt.
- [ ] Nothing new is stored, and nothing stored can identify the person or their work.
- [ ] Nothing drawn looks like a Claude Code dialog, permission prompt or login.
- [ ] A game's `tick()` and `frame()` stay cheap: bounded loops, bounded output size.
- [ ] No change to the rules themselves slipped in (see below).

## Changing the rules

`SECURITY.md`, `scripts/`, `.githooks/`, `.github/`, `hooks/register.js`,
`hooks/hooks.json` and the plugin manifests are listed in `.github/CODEOWNERS`, so a
maintainer must approve any change to them. A PR that weakens a rule must say why in
its description.

Maintainers: turn on branch protection for `main` with **Require a pull request**,
**Require review from Code Owners**, and **Require status checks: `security / check`**.

## Releasing to the marketplace

1. All checks pass on `main`, from a clean checkout.
2. The version is bumped in `plugin.json`, `.claude-plugin/plugin.json` and the README.
3. The release is built and tagged by a maintainer from that commit, never from a fork.
