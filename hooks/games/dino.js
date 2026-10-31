// Pure simulation and drawing: no files, processes, network, or model calls.
// Sprites use Unicode block elements; two leg frames animate the run.
export const DINO = [
  ['     ▄█▀█▄', ' █▄▄████▀▀', '  ▀█▀▀█▀  '],
  ['     ▄█▀█▄', ' █▄▄████▀▀', '  ▀▀█▀▀█  '],
]
const DINO_SMALL = [['  ▄█▀█▄', '▀██▀▌▐▘'], ['  ▄█▀█▄', '▀██▀▐▌ ']]
// Collision box, a little smaller than the drawing, as in the classic game.
const HITBOX = ['      ██  ', '   █████  ', '    █ █   ']
const X = 4
// A long, floaty jump: about 4 rows high and a second in the air.
const JUMP = 16
const GRAVITY = 30

// height: rows above the ground of the sprite's bottom row.
// At most 2 rows tall and 5 wide, so each one is clearable at the slowest speed (tested).
export const CACTI = [
  ['▄█▄'],
  ['▌█▐', '▀█▀'],
  ['▄█▄ ▄█▄'],
  ['▌██▐', '▀██▀'],
]
const BIRD = [['▀▄█▄▀'], ['▄▀█▀▄']]
const pick = list => list[Math.floor(Math.random() * list.length)]

export class DinoGame {
  constructor() {
    this.best = 0
    this.columns = 60
    this.reset()
  }

  reset() {
    this.distance = 0
    this.height = 0
    this.velocity = 0
    this.obstacles = []
    this.gap = 12 + Math.random() * 14
    this.over = false
  }

  speed() {
    return Math.min(25, 12 + this.distance / 180)
  }

  spawn() {
    // Birds join once the run is underway: low ones must be jumped, high ones must not.
    if (this.distance > 200 && Math.random() < 0.25) {
      return { x: this.columns + 1, kind: 'bird', height: pick([1, 1, 3]) }
    }
    return { x: this.columns + 1, kind: 'cactus', sprite: pick(CACTI), height: 0 }
  }

  sprite(obstacle) {
    return obstacle.kind === 'bird' ? BIRD[Math.floor(this.distance) % 2] : obstacle.sprite
  }

  get score() {
    return Math.floor(this.distance)
  }

  // The one button every game has: here, jump.
  action() {
    this.jump()
  }

  jump() {
    if (this.over) this.reset()
    if (this.height === 0) this.velocity = JUMP
  }

  tick(seconds) {
    let remaining = Math.min(Math.max(seconds, 0), 0.25)
    while (remaining > 0 && !this.over) {
      const dt = Math.min(remaining, 1 / 120)
      remaining -= dt
      this.velocity -= GRAVITY * dt
      this.height = Math.max(0, this.height + this.velocity * dt)
      if (this.height === 0) this.velocity = Math.max(0, this.velocity)
      const movement = this.speed() * dt
      this.distance += movement
      this.best = Math.max(this.best, Math.floor(this.distance))
      this.gap -= movement
      if (this.gap <= 0) {
        this.obstacles.push(this.spawn())
        // Gap scales with speed so every layout stays clearable; the spread keeps it unpredictable.
        this.gap = this.speed() * (1 + Math.random() * 1.8) + 8 + Math.random() * 6
      }
      const lift = Math.round(this.height)
      for (const obstacle of this.obstacles) {
        obstacle.x -= movement
        if (this.hits(HITBOX, lift, this.sprite(obstacle), Math.round(obstacle.x), obstacle.height)) this.over = true
      }
      this.obstacles = this.obstacles.filter(obstacle => obstacle.x > -12)
    }
  }

  hits(dino, lift, sprite, left, height) {
    for (let y = 0; y < dino.length; y++) {
      const level = dino.length - 1 - y + lift
      const oy = sprite.length - 1 - (level - height)
      if (oy < 0 || oy >= sprite.length) continue
      for (let x = 0; x < dino[y].length; x++) {
        const ox = X + x - left
        if (dino[y][x] !== ' ' && ox >= 0 && ox < sprite[oy].length && sprite[oy][ox] !== ' ') return true
      }
    }
    return false
  }

  frame(columns, rows) {
    this.columns = Math.max(20, Math.min(100, Math.floor(columns)))
    rows = Math.max(4, Math.min(10, Math.floor(rows)))
    const canvas = Array.from({ length: rows }, () => Array(this.columns).fill(' '))
    const draw = (sprite, left, top) => {
      for (let y = 0; y < sprite.length; y++) {
        for (let x = 0; x < sprite[y].length; x++) {
          if (top + y >= 0 && top + y < rows && left + x >= 0 && left + x < this.columns && sprite[y][x] !== ' ') {
            canvas[top + y][left + x] = sprite[y][x]
          }
        }
      }
    }
    const ground = rows - 1
    const step = this.height > 0 || this.over ? 0 : Math.floor(this.distance * 1.5) % 2
    const dino = (rows < 7 ? DINO_SMALL : DINO)[step]
    // Drawn at the true height, so what you see is what collides; only a short band clamps the peak.
    draw(dino, X, Math.max(0, ground - dino.length - Math.round(this.height)))
    for (const obstacle of this.obstacles) {
      const sprite = this.sprite(obstacle)
      draw(sprite, Math.round(obstacle.x), ground - sprite.length - Math.round(obstacle.height))
    }
    canvas[ground] = canvas[ground].map((cell, i) => cell !== ' ' ? cell : (i + Math.floor(this.distance)) % 11 === 0 ? '·' : '▔')
    return canvas.map(row => row.join('')).join('\n')
  }
}
