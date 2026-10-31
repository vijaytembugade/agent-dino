// Copter: fly through the gaps. Pure simulation and drawing, like every game here.
// Heights are fractions of the field (0 top, 1 bottom), so the game plays the same
// in a short band above the prompt and in a tall split pane.

// Two rows: the rotor (two frames, spinning) over the body. The mast sits on the cabin.
const ROTOR = ['  ━━━━┳━━━━', '  ─━━━┳━━━─']
const BODY = '╺━━━▟███▙▖'
const WRECK = '  ✸ ✸ ┳ ✸ ✸'
const X = 2
const GRAVITY = 1.6 // field heights per second squared
const THRUST = -0.6 // each Space sets the climb speed: tap to rise, let go to sink
const FALL = 1.0 // fastest sink, so a pause between taps is recoverable
const WALL = 2 // wall thickness, in columns

const between = (low, high) => low + Math.random() * (high - low)
// Columns a sprite row covers, from its first to its last drawn character.
const span = text => [text.search(/\S/), text.length - 1]

export class CopterGame {
  constructor() {
    this.best = 0
    this.columns = 60
    this.rows = 7
    this.reset()
  }

  reset() {
    this.y = 0.5
    this.vy = 0
    this.distance = 0
    this.score = 0
    this.over = false
    // Hovers until the first Space, so a game that starts by itself never crashes unseen.
    this.started = false
    this.walls = []
    // The first wall is already on screen, the second close behind.
    this.spawn(Math.round(this.columns * 0.55))
    this.gap = between(8, 14)
  }

  speed() {
    return Math.min(18, 10 + this.distance / 150)
  }

  // Gap size in rows: room for the 2-row copter plus 2, and about 65% of the field.
  gapRows() {
    return Math.min(this.rows - 1, Math.max(4, Math.round(this.rows * 0.65)))
  }

  spawn(x = this.columns + 1) {
    // The next gap moves at most 0.15 of the field from the last, so it is always reachable.
    const last = this.walls.at(-1)?.center ?? 0.5
    const half = this.gapRows() / 2 / this.rows
    const center = Math.min(1 - half, Math.max(half, last + between(-0.15, 0.15)))
    this.walls.push({ x, center, scored: false })
  }

  action() {
    if (this.over) return this.reset()
    this.started = true
    this.vy = THRUST
  }

  // The body's row; the rotor is the row above it.
  row() {
    return Math.floor(this.y * this.rows)
  }

  // Rows the wall leaves open, as [first, last].
  opening(wall) {
    const size = this.gapRows()
    const top = Math.max(0, Math.min(this.rows - size, Math.round(wall.center * this.rows - size / 2)))
    return [top, top + size - 1]
  }

  hits(wall) {
    const left = Math.round(wall.x)
    const [first, last] = this.opening(wall)
    const body = this.row()
    for (const [row, text] of [[body - 1, ROTOR[0]], [body, BODY]]) {
      const [start, end] = span(text)
      const overlaps = left <= X + end && left + WALL - 1 >= X + start
      if (overlaps && (row < first || row > last)) return true
    }
    return false
  }

  tick(seconds) {
    if (!this.started) return
    let remaining = Math.min(Math.max(seconds, 0), 0.25)
    while (remaining > 0 && !this.over) {
      const dt = Math.min(remaining, 1 / 120)
      remaining -= dt
      this.vy = Math.min(FALL, this.vy + GRAVITY * dt)
      this.y += this.vy * dt
      // The rotor must stay below the top edge, the body above the bottom.
      if (this.row() < 1 || this.row() >= this.rows) { this.over = true; break }
      const movement = this.speed() * dt
      this.distance += movement
      this.gap -= movement
      if (this.gap <= 0) {
        this.spawn()
        // Wide enough apart that the 10-column copter has room to line up the next gap.
        this.gap = between(22, 32)
      }
      for (const wall of this.walls) {
        wall.x -= movement
        if (this.hits(wall)) this.over = true
        if (!wall.scored && Math.round(wall.x) + WALL <= X) {
          wall.scored = true
          this.score += 1
          this.best = Math.max(this.best, this.score)
        }
      }
      this.walls = this.walls.filter(wall => wall.x > -WALL)
    }
  }

  frame(columns, rows) {
    this.columns = Math.max(20, Math.min(100, Math.floor(columns)))
    this.rows = Math.max(4, Math.min(10, Math.floor(rows)))
    const canvas = Array.from({ length: this.rows }, () => Array(this.columns).fill(' '))
    const put = (x, y, ch) => { if (y >= 0 && y < this.rows && x >= 0 && x < this.columns) canvas[y][x] = ch }
    for (const wall of this.walls) {
      const [first, last] = this.opening(wall)
      for (let y = 0; y < this.rows; y++) {
        if (y < first || y > last) for (let dx = 0; dx < WALL; dx++) put(Math.round(wall.x) + dx, y, '█')
      }
    }
    const body = Math.min(this.rows - 1, Math.max(1, this.row()))
    const rotor = this.over ? WRECK : ROTOR[Math.floor(this.distance * 3) % 2]
    for (const [y, text] of [[body - 1, rotor], [body, BODY]]) {
      for (let i = 0; i < text.length; i++) if (text[i] !== ' ') put(X + i, y, text[i])
    }
    if (!this.started) {
      const hint = 'Press Space to fly'
      for (let i = 0; i < hint.length; i++) put(X + 14 + i, body, hint[i])
    }
    return canvas.map(line => line.join('')).join('\n')
  }
}
