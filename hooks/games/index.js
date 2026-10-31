// The game catalog. To add a game: write hooks/games/<id>.js and list it here.
//
// Entry:    { id, name, description, actionLabel, hotkey, create }
//           hotkey is one lowercase letter that presses the action in the pane.
// Instance: create() returns an object with
//   action()               the game's single button (jump, flap, drop...); restarts after game over
//   reset()                start a new round, keeping `best`
//   tick(seconds)          advance the simulation
//   frame(columns, rows)   the picture as `rows` lines of at most `columns` characters
//   over, score, best      read by the header
import { CopterGame } from './copter.js'
import { DinoGame } from './dino.js'

export const GAMES = [
  { id: 'dino', name: 'Dino Run', description: 'Jump the cacti and low birds; stay down for high ones', actionLabel: 'Jump', hotkey: 'j', create: () => new DinoGame() },
  { id: 'copter', name: 'Copter', description: 'Hold or tap Space to climb, fly through the gaps', actionLabel: 'Thrust', hotkey: 'k', create: () => new CopterGame() },
]

export const findGame = id => GAMES.find(game => game.id === id)
