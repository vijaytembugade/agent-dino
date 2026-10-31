import { GAMES, findGame } from './games/index.js'

const PANE = 'agent-dino-game'
const instances = new Map()
let enabled = true
let gameId = GAMES[0].id
let game = instanceOf(gameId)
let activeTurn = null
let dismissedTurn = null
let manual = false
let paneOpen = false
let split = false
let picking = false
let timer = null
const waiting = new Set()

function instanceOf(id) {
  if (!instances.has(id)) instances.set(id, findGame(id).create())
  return instances.get(id)
}

function meta() {
  return findGame(gameId)
}

// Saved: `enabled`; `game`, the chosen id (off forgets it, so the next on asks again);
// `split`, whether the game opens in its own pane instead of right above the prompt.
async function load($) {
  enabled = (await $.store.get('enabled')) !== false
  split = (await $.store.get('split')) === true
  const saved = findGame(await $.store.get('game'))
  gameId = (saved || GAMES[0]).id
  game = instanceOf(gameId)
}

function textControl(text) {
  const match = text.trim().toLowerCase().match(/^(?:please\s+)?(enable|disable|turn on|turn off)\s+(?:agent[- ]?dino|dino)(?:\s+please)?[.!]?$/)
  if (!match) return null
  return match[1] === 'enable' || match[1] === 'turn on'
}

function playing() {
  return enabled && waiting.size === 0 && (manual || (activeTurn !== null && activeTurn !== dismissedTurn))
}

function syncTimer($) {
  if (playing() && !game.over) {
    if (timer === null) {
      timer = $.clock.every(50, () => {
        if (!playing()) return
        game.tick(0.05)
        $.ui.invalidate('ui.render')
        if (game.over && timer) {
          timer.cancel()
          timer = null
        }
      })
    }
  } else if (timer !== null) {
    timer.cancel()
    timer = null
  }
  $.ui.invalidate('ui.render')
}

async function setEnabled($, value, id) {
  enabled = value
  picking = false
  if (value) {
    gameId = id
    game = instanceOf(id)
    await $.store.set('game', id)
  } else {
    await $.store.delete('game')
  }
  dismissedTurn = null
  if (!enabled) {
    manual = false
    if (paneOpen) await $.ui.close({ id: PANE })
    paneOpen = false
    autoPane = false
  }
  syncTimer($)
  await $.store.set('enabled', value)
  return value
    ? `Agent Dino enabled with ${meta().name}. It will play automatically while Claude works.`
    : 'Agent Dino disabled. Use /dino on or type "enable dino" to choose a game again.'
}

// Opens the game list; choosing one enables Agent Dino with it.
async function turnOn($, args = '') {
  const named = findGame(args)
  if (named) return setEnabled($, true, named.id)
  if (args) return `No game "${args}". Games: ${GAMES.map(g => g.id).join(', ')}.`
  // The list draws above the prompt; a digit typed into the empty prompt picks.
  picking = true
  $.ui.invalidate('ui.render')
  return `Choose a game above the prompt: press ${GAMES.length > 1 ? `1-${Math.min(9, GAMES.length)}` : '1'}, or 0 to cancel.`
}

async function choose($, id) {
  picking = false
  $.ui.toast(await setEnabled($, true, id))
}

function pickerTree($, e) {
  const { Box, Text, Button } = $.ui.resolve(e)
  return Box({ flexDirection: 'column', children: [
    Text({ children: ['Agent Dino · pick a game. It stays chosen until /dino off.'], color: '#55dd99' }),
    ...GAMES.map((g, i) => Button({ key: `pick-${g.id}`, label: `${i + 1}. ${g.name} — ${g.description}`, hotkey: i < 9 ? String(i + 1) : undefined, plain: true, onPress: () => choose($, g.id) })),
    Button({ key: 'pick-cancel', label: '0. Cancel', hotkey: '0', plain: true, onPress: () => { picking = false; $.ui.invalidate('ui.render') } }),
  ] })
}

// The automatic game takes the keyboard while Claude works and hands it back after.
// Opening asks for focus; Claude grants it only over an empty composer, so typing is never stolen.
let autoPane = false
async function autoOpen($) {
  if (!split || !playing() || paneOpen) return
  try {
    const placed = await $.ui.open({ id: PANE, title: meta().name, focus: true, closeOnEscape: true, rows: 13, columns: 65 })
    paneOpen = placed.isPlaced
    autoPane = placed.isPlaced
    // Too narrow to place: don't leave a pane waiting; the band shows the game instead.
    if (!placed.isPlaced) await $.ui.close({ id: PANE })
  } catch { /* The band above the prompt still shows the game. */ }
  syncTimer($)
}

async function autoClose($) {
  if (!autoPane || manual) return
  autoPane = false
  paneOpen = false
  try { await $.ui.close({ id: PANE }) } catch { /* Already closed. */ }
  syncTimer($)
}

async function control($, e) {
  let action = (e.args || '').trim().toLowerCase()
  if (e.command === 'enable-dino') action = `on ${action}`.trim()
  if (e.command === 'disable-dino') action = 'off'
  const [verb, ...rest] = action.split(/\s+/)
  if (verb === 'on' || verb === 'enable') return { text: await turnOn($, rest.join(' ')) }
  if (verb === 'off' || verb === 'disable') return { text: await setEnabled($, false) }
  if (verb === 'split') {
    split = rest[0] !== 'off'
    await $.store.set('split', split)
    if (!split) await autoClose($)
    syncTimer($)
    return { text: split
      ? 'Agent Dino will open in its own split pane while Claude works. /dino split off goes back to playing above the prompt.'
      : 'Agent Dino will play right above the prompt. Press Space to jump.' }
  }
  if (verb === 'status') {
    return { text: `Agent Dino: ${enabled ? `enabled (${meta().name}, ${split ? 'split pane' : 'above the prompt'})` : 'disabled'}; ${waiting.size ? 'paused for input' : playing() ? 'playing' : 'ready'}. Games: ${GAMES.map(g => g.id).join(', ')}. /dino on [game] | off | play | split [off]` }
  }
  if (action !== '' && action !== 'play') return { text: 'Use /dino on [game], /dino off, /dino play, /dino split [off], or /dino status.' }
  if (!enabled) return { text: 'Agent Dino is disabled. Run /dino on first.' }
  dismissedTurn = null
  if (game.over) game.reset()
  if (!split) {
    // Play above the prompt; the Stop button (3) ends free play.
    manual = !manual
    syncTimer($)
    return { text: manual ? `${meta().name}: press Space to ${meta().actionLabel.toLowerCase()}, 3 to stop.` : `${meta().name} stopped.` }
  }
  manual = true
  autoPane = false
  const placed = await $.ui.open({ id: PANE, title: meta().name, focus: true, closeOnEscape: true, rows: 13, columns: 65 })
  paneOpen = placed.isPlaced
  syncTimer($)
  return {}
}

function gameTree($, e, pane) {
  const { Box, Text, Button } = $.ui.resolve(e)
  const columns = Math.max(20, Math.min(80, (e.props.bodyColumns || e.viewport.columns) - 2))
  const budget = pane ? Math.min(13, e.props.scroll.bodyRows) : e.props.maxRows
  const rows = Math.min(9, Math.max(4, budget - 3))
  if (!playing() || budget < 7 || columns < 24) {
    const text = waiting.size ? `${meta().name} paused — Claude needs your input.`
      : budget < 7 || columns < 24 ? 'Agent Dino · More room needed. /dino play opens the game.'
      : enabled ? 'Agent Dino · Ready. Starts automatically while Claude works.' : 'Agent Dino disabled.'
    return Text({ children: [text], dimColor: true })
  }
  const { name, actionLabel, hotkey } = meta()
  const act = () => { game.action(); syncTimer($) }
  const restart = () => { game.reset(); syncTimer($) }
  return Box({ flexDirection: 'column', children: [
    Text({ children: [`${name.toUpperCase()}   ${game.over ? `GAME OVER — ${actionLabel.toLowerCase()} to restart` : manual ? 'Free play' : 'Claude is working'}${pane ? `   Enter/${hotkey} ${actionLabel.toLowerCase()} · Esc back` : `   Space ${actionLabel.toLowerCase()}`}   ${game.score} / best ${game.best}`], color: '#55dd99' }),
    Text({ children: [game.frame(columns, rows)], color: '#55dd99', wrap: 'truncate' }),
    Box({ flexDirection: 'row', columnGap: 2, children: [
      Button({ key: 'game-action', label: actionLabel, hotkey: pane ? hotkey : '1', plain: true, autoFocus: true, onPress: act }),
      Button({ key: 'game-restart', label: 'Restart', hotkey: pane ? 'r' : '2', plain: true, onPress: restart }),
      ...(manual && !pane ? [Button({ key: 'game-stop', label: 'Stop', hotkey: '3', plain: true, onPress: () => { manual = false; syncTimer($) } })] : []),
      Button({ key: 'game-off', label: 'Disable Dino', plain: true, onPress: async () => { await setEnabled($, false) } }),
    ] }),
  ] })
}

export function register(on) {
  on('session.start', async ($, e, next) => {
    await load($)
    await $.command.register({ name: 'dino', description: 'Enable, disable, or play Agent Dino', argumentHint: '[on [game]|off|play|split [off]|status]', immediate: true })
    await $.command.register({ name: 'agent-dino', description: 'Control Agent Dino', argumentHint: '[on [game]|off|play|split [off]|status]', immediate: true })
    await $.command.register({ name: 'enable-dino', description: 'Choose a game and enable Agent Dino', immediate: true })
    await $.command.register({ name: 'disable-dino', description: 'Disable Agent Dino', immediate: true })
    syncTimer($)
    return next(e)
  })

  // Replies go to a toast, not the transcript: a transcript line is read by the model on the
  // next turn, so even a status message would cost the person tokens. The game costs none.
  on('command.run', { command: ['dino', 'agent-dino', 'enable-dino', 'disable-dino'] }, async ($, e) => {
    const { text } = await control($, e)
    if (text) $.ui.toast(text, { timeoutMs: 6000 })
    return {}
  })

  // Exact, explicit controls are handled locally. Ordinary prompts pass unchanged.
  on('prompt.submit', async ($, e, next) => {
    const value = textControl(e.text)
    if (value === null) return next(e)
    const message = value ? await turnOn($) : await setEnabled($, false)
    // Claude restores dropped prompts. Clear only this exact control after restoration,
    // preserving a new draft if the person has already started typing something else.
    if (e.origin?.kind === 'composer') {
      $.clock.after(50, async () => {
        try {
          const draft = await $.prompt.read()
          if (draft.text === e.text) await $.prompt.fill({ text: '' })
        } catch { /* Clearing a local control is optional if the editor is unavailable. */ }
      })
    }
    return { drop: message }
  }).catch(($, e, next) => next(e))

  on('turn.start', async ($, e, next) => {
    if (e.agentId) return next(e)
    await load($)
    activeTurn = e.turnId
    if (game.over) game.reset()
    dismissedTurn = null
    waiting.clear()
    syncTimer($)
    const result = await next(e)
    await autoOpen($)
    return result
  })

  on('turn.complete', async ($, e, next) => {
    if (!e.agentId && e.turnId === activeTurn) {
      activeTurn = null
      waiting.clear()
      syncTimer($)
      await autoClose($)
    }
    return next(e)
  })

  // Observe permission decisions, without approving, denying, or rewriting one.
  on('tool.check', async ($, e, next) => {
    const decision = await next(e)
    if (!e.agentId && e.tool_use_id && decision.decision === 'ask') {
      waiting.add(e.tool_use_id)
      syncTimer($)
      await autoClose($)
    }
    return decision
  }).catch(($, e, next) => next(e))

  on('tool.call', async ($, e, next) => {
    if (e.agentId) return next(e)
    const id = e.tool_use_id || e.tool
    if (e.tool === 'AskUserQuestion') {
      waiting.add(id)
      syncTimer($)
      await autoClose($)
    }
    try {
      return await next(e)
    } finally {
      if (waiting.delete(id)) {
        syncTimer($)
        await autoOpen($)
      }
    }
  }).catch(($, e, next) => next(e))

  // Space in an empty prompt plays the game above it, so the keyboard never has to move.
  // Only that one key, only while the game runs and the prompt is empty: typing is never eaten.
  on('prompt.edit', async ($, e, next) => {
    if (e.inputText !== ' ' || e.text !== '' || paneOpen || !playing()) return next(e)
    game.action()
    syncTimer($)
    return { text: '', cursor: 0 }
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const theirs = await next(e)
    if (e.props.hasSurvey || e.props.view?.agentId) return theirs
    const { Box, Text, Button } = $.ui.resolve(e)
    if (picking) return Box({ flexDirection: 'column', children: [theirs, pickerTree($, e)] })
    if (!enabled) return theirs
    const ours = playing() && !paneOpen
      ? gameTree($, e, false)
      : Box({ flexDirection: 'row', columnGap: 2, children: [
          Text({ children: [waiting.size ? 'Agent Dino paused — Claude needs you.' : `Agent Dino ON · ${meta().name} · /dino off to disable`], dimColor: true }),
          Button({ key: 'dino-play', label: 'Play', plain: true, onPress: async () => { await control($, { command: 'dino', args: 'play' }) } }),
        ] })
    return Box({ flexDirection: 'column', children: [theirs, ours] })
  })

  on('ui.render', { component: 'Pane' }, async ($, e, next) => {
    if (e.requestId !== PANE) return next(e)
    return gameTree($, e, true)
  })

  on('ui.close', async ($, e, next) => {
    if (e.id === PANE) {
      paneOpen = false
      autoPane = false
      if (e.origin.kind === 'person') {
        manual = false
        dismissedTurn = activeTurn
      }
      syncTimer($)
    }
    return next(e)
  }).catch(($, e, next) => next(e))

  on('session.end', async ($, e, next) => {
    activeTurn = null
    manual = false
    waiting.clear()
    if (timer) timer.cancel()
    timer = null
    return next(e)
  })
}
