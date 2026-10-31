#!/usr/bin/env node
// Agent Dino security check. Enforces SECURITY.md; runs before every push (.githooks/pre-push)
// and on every pull request (.github/workflows/security.yml). No dependencies.
//
//   node scripts/security-check.mjs           static rules, then `claude plugin validate` and `test`
//   node scripts/security-check.mjs --static  static rules only
import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

// What the plugin may ask of Claude Code. Every entry is local UI, local storage or the
// prompt box. Adding one needs a maintainer's review (SECURITY.md, "Changing the rules").
export const ALLOWED_CALLS = new Set([
  'clock.after', 'clock.every', 'command.register', 'prompt.fill', 'prompt.read',
  'store.delete', 'store.get', 'store.set',
  'ui.close', 'ui.invalidate', 'ui.open', 'ui.resolve', 'ui.toast',
])
export const ALLOWED_EVENTS = new Set([
  'command.run', 'prompt.edit', 'prompt.submit', 'session.end', 'session.start',
  'tool.call', 'tool.check', 'turn.complete', 'turn.start', 'ui.close', 'ui.render',
])

const CODE = /\.(m?js|ts|tsx)$/
// The only binaries allowed: the plugin icon and README images in docs/.
const IMAGE = /^(\.claude-plugin\/icon\.png|docs\/[\w.-]+\.(png|jpe?g|gif))$/
const BINARY = /\.(zip|whl|tar|gz|tgz|exe|dll|so|dylib|node|wasm|bin|jar|pyc)$/i
const SKIP = new Set(['.git', '.venv', '.tools', 'node_modules', 'build', 'dist', '__pycache__', '.claude-plugin/types'])
const SECRETS = [
  [/sk-ant-[A-Za-z0-9_-]{20,}/, 'Anthropic API key'],
  [/\bAKIA[0-9A-Z]{16}\b/, 'AWS access key'],
  [/\bgh[pousr]_[A-Za-z0-9]{36,}\b/, 'GitHub token'],
  [/\bxox[abprs]-[A-Za-z0-9-]{10,}/, 'Slack token'],
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----/, 'private key'],
]
// Anywhere in plugin code: no dynamic code, no network, no reaching outside the sandbox.
const NEVER = [
  [/\beval\s*\(/, 'eval()'],
  [/\bnew\s+Function\b|\bFunction\s*\(/, 'Function constructor'],
  [/\bimport\s*\(/, 'dynamic import()'],
  [/\brequire\s*\(/, 'require()'],
  [/\b(fetch|XMLHttpRequest|WebSocket|EventSource)\b/, 'network API'],
  [/https?:\/\//, 'URL (the plugin makes no network requests)'],
  [/\b(globalThis|process\.|Deno\.|Bun\.)/, 'host global'],
  [/\batob\s*\(|\\x[0-9a-f]{2}.*\\x[0-9a-f]{2}.*\\x[0-9a-f]{2}/i, 'encoded or obfuscated text'],
]
const PYTHON_NEVER = [
  [/^\s*(import|from)\s+(socket|urllib|requests|http|ftplib|smtplib|telnetlib|xmlrpc|pickle|marshal)\b/m, 'network or unsafe-deserialisation module'],
  [/\b(eval|exec)\s*\(/, 'eval/exec'],
  [/shell\s*=\s*True/, 'subprocess with shell=True'],
  [/\bos\.system\s*\(/, 'os.system'],
]

// Pure rules over { path: text }, so the self-test can feed them bad input.
export function scan(files) {
  const problems = []
  const fail = (path, why) => problems.push(`${path}: ${why}`)
  for (const [path, text] of Object.entries(files)) {
    if (text === null) { if (!IMAGE.test(path)) fail(path, 'binary file; commit source only (images go in docs/; see SECURITY.md)'); continue }
    for (const [re, what] of SECRETS) if (re.test(text)) fail(path, `looks like a ${what}`)
    if (path === 'scripts/security-check.mjs' || path.startsWith('scripts/')) continue
    if (path.startsWith('hooks/') && CODE.test(path)) {
      for (const [re, what] of NEVER) if (re.test(text)) fail(path, `uses ${what}`)
      for (const [, spec] of text.matchAll(/\bfrom\s+['"]([^'"]+)['"]/g)) {
        if (!spec.startsWith('./') && !spec.startsWith('../')) fail(path, `imports package "${spec}"; plugin code imports only its own files`)
      }
    }
    if (path.startsWith('hooks/games/') && CODE.test(path)) {
      if (/\$\s*\.|\bon\s*\(/.test(text)) fail(path, 'a game touches the engine ($ or on); games are pure simulation')
      if (/\b(setTimeout|setInterval|queueMicrotask)\b/.test(text)) fail(path, 'a game runs its own timer; the plugin calls tick()')
    }
    if (path === 'hooks/register.js') {
      for (const [, noun, method] of text.matchAll(/\$\.(\w+)\.(\w+)/g)) {
        if (!ALLOWED_CALLS.has(`${noun}.${method}`)) fail(path, `calls $.${noun}.${method}, not on the allowlist`)
      }
      for (const [, event] of text.matchAll(/\bon\(\s*['"]([\w.]+)['"]/g)) {
        if (!ALLOWED_EVENTS.has(event)) fail(path, `hooks "${event}", not on the allowlist`)
      }
      if (/\bcontext\s*:/.test(text)) fail(path, 'returns `context`, which the model reads (costs the user tokens)')
      if (/\b(deny|decision)\s*:/.test(text)) fail(path, 'sets a permission decision; the plugin only observes them')
    }
    if (path.endsWith('.py')) for (const [re, what] of PYTHON_NEVER) if (re.test(text)) fail(path, `uses ${what}`)
    if (path.endsWith('package.json')) {
      const pkg = JSON.parse(text)
      for (const field of ['dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies']) {
        if (pkg[field] && Object.keys(pkg[field]).length) fail(path, `declares ${field}; the plugin has no npm dependencies`)
      }
      if (pkg.scripts && Object.keys(pkg.scripts).some(s => /^(pre|post)?install$/.test(s))) fail(path, 'declares an install script')
    }
  }
  const hooks = files['hooks/hooks.json']
  if (hooks && JSON.stringify(JSON.parse(hooks).modules) !== '["./register.js"]') fail('hooks/hooks.json', 'modules must be exactly ["./register.js"]')
  const versions = ['plugin.json', '.claude-plugin/plugin.json'].filter(p => files[p]).map(p => JSON.parse(files[p]).version)
  if (new Set(versions).size > 1) fail('plugin.json', `versions differ: ${versions.join(' vs ')}`)
  return problems
}

function listFiles(root) {
  try {
    // In a git checkout, check exactly what would be committed.
    return execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard'], { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).split('\n').filter(Boolean)
  } catch {
    const out = []
    const walk = dir => {
      for (const name of readdirSync(dir)) {
        const full = join(dir, name)
        const rel = relative(root, full)
        if (SKIP.has(name) || SKIP.has(rel) || name.endsWith('.egg-info')) continue
        statSync(full).isDirectory() ? walk(full) : out.push(rel)
      }
    }
    walk(root)
    return out
  }
}

function read(root, path) {
  if (BINARY.test(path)) return null
  const buffer = readFileSync(join(root, path))
  return buffer.includes(0) ? null : buffer.toString('utf8')
}

function claude(root, args) {
  try {
    execFileSync('claude', ['plugin', ...args, '.'], { cwd: root, stdio: 'inherit' })
    return true
  } catch (error) {
    if (error.code === 'ENOENT') { console.error('✘ claude CLI not found: install Claude Code, or run with --static'); return false }
    return false
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = join(fileURLToPath(import.meta.url), '..', '..')
  const files = Object.fromEntries(listFiles(root).filter(p => existsSync(join(root, p))).map(p => [p, read(root, p)]))
  const problems = scan(files)
  for (const problem of problems) console.error(`✘ ${problem}`)
  if (problems.length) { console.error(`\n${problems.length} security problem(s). See SECURITY.md.`); process.exit(1) }
  console.log(`✔ static security rules: ${Object.keys(files).length} files clean`)
  if (!process.argv.includes('--static')) {
    if (!claude(root, ['validate', '--strict']) || !claude(root, ['test'])) process.exit(1)
  }
}
