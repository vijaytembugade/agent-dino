import { expect, mock, test } from 'claude-code/testing'
import { CopterGame } from '../hooks/games/copter.js'
import { CACTI, DinoGame as Game } from '../hooks/games/dino.js'

const toasts: string[] = []
// /dino replies arrive as toasts; this returns the one a command raised.
async function run($, args: string, command = 'dino') {
  toasts.length = 0
  const result = await $.command.run({ command, args })
  expect(result.text).toBeUndefined()
  return toasts.at(-1) ?? ''
}

const BAND = {
  plugin: 'agent-dino', component: 'AbovePrompt', requestId: 'above-prompt',
  viewport: { columns: 80, rows: 24 },
  props: { hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 80,
    scroll: { offset: 0, bodyRows: 10 }, view: {} },
} as const

const PANE = {
  plugin: 'agent-dino', component: 'Pane', requestId: 'agent-dino-game',
  viewport: { columns: 80, rows: 30 },
  props: { title: 'Agent Dino', isFocused: true, bodyColumns: 60, placement: 'inline',
    scroll: { offset: 0, bodyRows: 13 }, view: {} },
} as const

function setup(on, placed = true) {
  const clock = mock.clock(on)
  const saved = new Map<string, unknown>()
  on('store.get', ($, e) => ({ value: saved.get(e.key) }))
  on('store.set', ($, e) => { saved.set(e.key, e.value); return { value: undefined } })
  on('store.delete', ($, e) => { saved.delete(e.key); return { value: undefined } })
  on('command.register', () => ({ value: undefined }))
  on('session.start', () => ({ cwd: '/work' }))
  on('session.end', () => ({}))
  on('turn.start', ($, e) => ({ turnId: e.turnId }))
  on('turn.complete', ($, e) => ({ text: e.answer }))
  on('ui.render', () => ({ type: 'Text', props: {}, children: ['Other plugin content'] }))
  const opened = []
  const closed = []
  on('ui.open', ($, e) => { opened.push(e); return { value: placed || e.focus !== true ? { isPlaced: true } : { isPlaced: false, reason: 'narrow' } } })
  on('ui.close', ($, e) => { closed.push(e); return { value: undefined } })
  on('ui.toast', ($, e) => { toasts.push(e.text); return { value: undefined } })
  return { clock, saved, opened, closed }
}

async function start($) {
  await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/work' })
}

async function begin($, id = 'turn-1') {
  await $.turn.start({ text: 'Do some work', turnId: id })
}

async function finish($, extra = {}) {
  await $.turn.complete({ turnId: 'turn-1', answer: 'Done', durationMs: 1000,
    isAborted: false, reason: 'answer', ...extra })
}

test('plays above the prompt by default, without opening a pane', async ($, on) => {
  const { opened } = setup(on)
  await start($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /Agent Dino ON/ })).toBeDefined()
  await begin($)
  expect(await ui.find({ type: 'Text', text: /Claude is working/ })).toBeDefined()
  expect(await ui.find({ key: 'game-action' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'Other plugin content' })).toBeDefined()
  expect(opened.length).toBe(0)
  await finish($)
  expect(await ui.find({ key: 'game-action' })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /Agent Dino ON/ })).toBeDefined()
  await ui.unmount()
})

test('off removes the game immediately and remains off at the next session start', async ($, on) => {
  const { saved } = setup(on)
  await start($)
  await begin($)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const answer = await run($, 'off')
  expect(answer).toContain('disabled')
  expect(saved.get('enabled')).toBe(false)
  expect(await ui.find({ key: 'game-action' })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /Agent Dino ON/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: 'Other plugin content' })).toBeDefined()
  await start($)
  expect((await run($, 'status'))).toContain('disabled')
  await $.command.run({ command: 'enable-dino', args: 'dino' })
  expect(saved.get('enabled')).toBe(true)
  expect(await ui.find({ key: 'game-action' })).toBeDefined()
  await ui.unmount()
})

test('literal enable/disable prompts run locally and ordinary prompts pass through', async ($, on) => {
  const { saved } = setup(on)
  let forwarded = 0
  on('prompt.submit', ($, e) => { forwarded++; return { text: e.text } })
  await start($)
  const off = await $.prompt.submit({ text: 'disable agent-dino' })
  expect(off.drop).toContain('disabled')
  expect(saved.get('enabled')).toBe(false)
  const onResult = await $.prompt.submit({ text: 'Please enable dino.' })
  expect(onResult.drop).toContain('Choose a game')
  expect(saved.get('enabled')).toBe(false)
  await $.prompt.submit({ text: 'Document how to disable dino in a README.' })
  expect(forwarded).toBe(1)
})

test('jump and restart work in the native terminal and desktop element trees', async ($, on) => {
  const { clock } = setup(on)
  await start($)
  await $.command.run({ command: 'dino', args: 'split' })
  await $.command.run({ command: 'dino', args: 'play' })
  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    await ui.press({ key: 'game-action' })
    await clock.advance(200)
    expect(await ui.find({ type: 'Text', text: /Free play/ })).toBeDefined()
    await ui.press({ key: 'game-restart' })
    expect(await ui.find({ type: 'Text', text: /0 \/ best/ })).toBeDefined()
    await ui.unmount()
  }
})

test('question tool pauses and resumes without changing the answer', async ($, on) => {
  setup(on)
  let release
  let entered
  const gate = new Promise<void>(resolve => { release = resolve })
  const called = new Promise<void>(resolve => { entered = resolve })
  on('tool.call', async ($, e) => {
    entered()
    await gate
    return { result: { questions: e.questions, answers: { 'Choose one': 'A' } } }
  })
  await start($)
  await begin($)
  const pending = $.tool.call({ tool: 'AskUserQuestion', questions: [{
    question: 'Choose one', header: 'Choice', options: [
      { label: 'A', description: 'First' }, { label: 'B', description: 'Second' },
    ], multiSelect: false,
  }] })
  await called
  expect((await run($, 'status'))).toContain('paused for input')
  release()
  const out = await pending
  expect(out.result.answers['Choose one']).toBe('A')
  expect((await run($, 'status'))).toContain('playing')
})

test('permission decisions remain unchanged', async ($, on) => {
  setup(on)
  on('tool.check', () => ({ decision: 'ask', reason: 'User approval required' }))
  const result = await $.tool.check({ tool: 'Bash', input: { command: 'echo test' } })
  expect(result.decision).toBe('ask')
  expect(result.reason).toBe('User approval required')
})

test('background subagent completion cannot stop the main game', async ($, on) => {
  setup(on)
  await start($)
  await begin($)
  await finish($, { turnId: 'child-turn', agentId: 'child' })
  expect((await run($, 'status'))).toContain('playing')
  await finish($)
  expect((await run($, 'status'))).toContain('ready')
})

test('physics: grounded collision, jump clearance, landing and best score', async () => {
  const game = new Game()
  game.obstacles = [{ x: 7, kind: 'cactus', sprite: ['▌█▐', '▀█▀'], height: 0 }]
  game.tick(0.01)
  expect(game.over).toBe(true)
  game.jump()
  expect(game.over).toBe(false)
  game.tick(0.1)
  expect(game.height > 0).toBe(true)
  const speed = game.velocity
  game.jump()
  expect(game.velocity).toBe(speed)
  for (let i = 0; i < 20; i++) game.tick(0.05)
  expect(game.height).toBe(0)
  const best = game.best
  game.reset()
  expect(game.best).toBe(best)
})


test('clears a restored literal control but preserves a new draft', async ($, on) => {
  const { clock } = setup(on)
  let draft = 'disable dino'
  on('prompt.read', () => ({ value: { text: draft, cursor: draft.length } }))
  on('prompt.fill', ($, e) => { draft = e.text; return { isFilled: true } })
  await start($)
  await $.prompt.submit({ text: 'disable dino', origin: { kind: 'composer' } })
  await clock.advance(100)
  expect(draft).toBe('')
  await $.prompt.submit({ text: 'enable dino', origin: { kind: 'composer' } })
  draft = 'Review my changes'
  await clock.advance(100)
  expect(draft).toBe('Review my changes')
})


test('jump remains visible in the short automatic game', async () => {
  const game = new Game()
  game.jump()
  for (let i = 0; i < 8; i++) game.tick(0.05)
  for (const rows of [4, 5, 7, 9]) {
    const frame = game.frame(78, rows)
    expect(frame).toContain('█')
    expect(frame.split('\n').length).toBe(rows)
  }
})


test('with /dino split, a work turn opens a focused pane and the turn end hands the prompt back', async ($, on) => {
  const { opened, closed, saved } = setup(on)
  await start($)
  await $.command.run({ command: 'dino', args: 'split' })
  expect(saved.get('split')).toBe(true)
  await begin($)
  expect(opened.length).toBe(1)
  expect(opened[0].focus).toBe(true)
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /Claude is working/ })).toBeDefined()
  await ui.unmount()
  await finish($)
  expect(closed.some(e => e.id === 'agent-dino-game')).toBe(true)
})

test('obstacles are random in kind and spacing, and every layout is clearable', async () => {
  const runs = new Set()
  const kinds = new Set()
  for (let run = 0; run < 6; run++) {
    const game = new Game()
    const gaps = []
    for (let i = 0; i < 400; i++) {
      const count = game.obstacles.length
      game.tick(0.05)
      if (game.over) game.over = false
      if (game.obstacles.length > count) { gaps.push(Math.round(game.gap)); kinds.add(JSON.stringify(game.obstacles.at(-1).sprite || 'bird')) }
    }
    runs.add(gaps.join(','))
  }
  expect(runs.size).toBe(6)
  expect(kinds.size > 3).toBe(true)
})


test('on lists the games, the pick is saved until off, and off makes on ask again', async ($, on) => {
  const { saved, opened } = setup(on)
  await start($)
  await $.command.run({ command: 'dino', args: 'off' })
  expect(saved.has('game')).toBe(false)
  const answer = await run($, 'on')
  expect(answer).toContain('Choose a game')
  expect(opened.length).toBe(0)
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await band.press({ key: 'pick-dino' })
  expect(await band.find({ key: 'pick-dino' })).toBeUndefined()
  await band.unmount()
  expect(saved.get('enabled')).toBe(true)
  expect(saved.get('game')).toBe('dino')
  await start($)
  expect((await run($, 'status'))).toContain('enabled (Dino Run, above the prompt)')
  await $.command.run({ command: 'dino', args: 'off' })
  expect(saved.has('game')).toBe(false)
  expect((await run($, 'on nope'))).toContain('No game')
})


test('Space in an empty prompt jumps while Claude works; other typing is untouched', async ($, on) => {
  setup(on)
  on('prompt.edit', ($, e) => {
    const text = e.text.slice(0, e.start) + e.inputText + e.text.slice(e.end)
    return { text, cursor: e.start + e.inputText.length }
  })
  await start($)
  const edit = (text, inputText) => $.prompt.edit({ origin: { kind: 'composer' }, text, cursor: text.length, start: text.length, end: text.length, inputText })
  expect((await edit('', ' ')).text).toBe(' ')
  await begin($)
  expect((await edit('', ' ')).text).toBe('')
  expect((await edit('fix', ' ')).text).toBe('fix ')
  expect((await edit('', 'a')).text).toBe('a')
})

test('every obstacle can be cleared with a well-timed jump at the slowest speed', async () => {
  for (const sprite of CACTI) {
    let cleared = false
    for (let wait = 0; wait < 3 && !cleared; wait += 0.01) {
      const game = new Game()
      game.gap = 1e9
      game.obstacles = [{ x: 30, kind: 'cactus', sprite, height: 0 }]
      let t = 0
      let jumped = false
      while (t < 4 && !game.over && game.obstacles.length) {
        if (!jumped && t >= wait) { game.jump(); jumped = true }
        game.tick(0.01)
        t += 0.01
      }
      cleared = !game.over
    }
    expect(cleared).toBe(true)
  }
})

test('Copter: every gap is reachable, walls kill, and thrust restarts after a crash', async () => {
  for (const rows of [5, 6, 7, 8, 9]) for (let run = 0; run < 20; run++) {
    const game = new CopterGame()
    game.frame(70, rows)
    game.reset()
    game.tick(1)
    expect(game.distance).toBe(0) // hovers until the first Space
    game.action()
    // Autopilot: thrust whenever the copter (rotor over body) sits below the next gap's centre.
    for (let t = 0; t < 90 && !game.over; t += 0.05) {
      const next = game.walls.find(wall => wall.x + 2 > 4)
      if (game.y > (next ? next.center : 0.5) + 0.5 / rows) game.action()
      game.tick(0.05)
    }
    expect(game.over).toBe(false)
    expect(game.score > 20).toBe(true)
  }
  const game = new CopterGame()
  game.action()
  for (let i = 0; i < 80 && !game.over; i++) game.tick(0.05)
  expect(game.over).toBe(true)
  const best = game.best
  game.action()
  expect(game.over).toBe(false)
  expect(game.best).toBe(best)
  expect(game.frame(60, 7).split('\n').length).toBe(7)
})

test('/dino on copter picks Copter directly, and the list shows every game', async ($, on) => {
  const { saved } = setup(on)
  await start($)
  await run($, 'off')
  await run($, 'on')
  const band = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await band.find({ key: 'pick-dino' })).toBeDefined()
  expect(await band.find({ key: 'pick-copter' })).toBeDefined()
  await band.press({ key: 'pick-copter' })
  expect(saved.get('game')).toBe('copter')
  await begin($)
  expect(await band.find({ type: 'Text', text: /COPTER/ })).toBeDefined()
  await band.unmount()
  await run($, 'off')
  expect(await run($, 'on copter')).toContain('Copter')
})
