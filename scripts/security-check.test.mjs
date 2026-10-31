// Proves each rule in security-check.mjs fires: node scripts/security-check.test.mjs
import assert from 'node:assert/strict'
import { scan } from './security-check.mjs'

const clean = {
  'hooks/hooks.json': '{"modules":["./register.js"]}',
  'hooks/register.js': "import { GAMES } from './games/index.js'\non('turn.start', ($, e, next) => { $.ui.toast('hi'); return next(e) })",
  'hooks/games/index.js': "import { DinoGame } from './dino.js'",
  'hooks/games/dino.js': 'export class DinoGame { action() { this.jump() } }',
  'plugin.json': '{"version":"1.0.0"}',
  '.claude-plugin/plugin.json': '{"version":"1.0.0"}',
}
assert.deepEqual(scan({ ...clean, 'docs/screen.png': null, '.claude-plugin/icon.png': null }), [])

const bad = {
  'hooks/games/evil.js': "export class G { tick() { fetch('https://x.example') } }",
  'hooks/games/sneaky.js': "export class G { tick() { $.process.run('rm') } }",
  'hooks/games/eval.js': "export class G { tick() { eval('1') } }",
  'hooks/games/dep.js': "import _ from 'lodash'",
  'hooks/games/timer.js': "export class G { constructor() { setInterval(() => {}, 1) } }",
  'hooks/register.js': "on('prompt.compose', ($, e, next) => next(e)); $.model.complete({}); return { context: ['x'] }; return { decision: 'allow' }",
  'hooks/hooks.json': '{"modules":["./register.js","./extra.js"]}',
  'agent_dino/x.py': 'import requests\nsubprocess.run(cmd, shell=True)',
  'package.json': '{"dependencies":{"left-pad":"1"},"scripts":{"postinstall":"node x"}}',
  'notes.txt': 'key ' + 'sk-ant' + '-api03-abcdefghijklmnopqrstuvwxyz', // split so the repo scan does not flag this file
  'dist/payload.zip': null,
  'hooks/games/sprite.png': null,
  'plugin.json': '{"version":"1.0.0"}',
  '.claude-plugin/plugin.json': '{"version":"1.0.1"}',
}
const found = scan(bad).join('\n')
for (const expected of [
  'evil.js: uses network API', 'evil.js: uses URL', 'sneaky.js: a game touches the engine', 'eval.js: uses eval()',
  'dep.js: imports package "lodash"', 'timer.js: a game runs its own timer', 'hooks "prompt.compose"', 'calls $.model.complete', 'returns `context`',
  'sets a permission decision', 'modules must be exactly', 'x.py: uses network', 'x.py: uses subprocess with shell=True',
  'declares dependencies', 'declares an install script', 'Anthropic API key', 'payload.zip: binary file', 'sprite.png: binary file', 'versions differ',
]) assert.ok(found.includes(expected), `missing: ${expected}\n--- got:\n${found}`)
console.log('✔ security-check self-test: every rule fires')
