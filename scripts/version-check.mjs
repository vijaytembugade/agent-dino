#!/usr/bin/env node
// Fails a pull request that changes plugin code without raising the version, because
// users only receive an update when `version` goes up (see README, "Updates").
// Runs on every PR (.github/workflows/security.yml) and before every push (.githooks/pre-push).
//
//   node scripts/version-check.mjs [base]   base defaults to origin/$GITHUB_BASE_REF, else origin/main
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// What users download and run. Changing any of it is a release.
const RELEASED = /^(hooks\/|\.claude-plugin\/marketplace\.json$)/
const MANIFESTS = ['plugin.json', '.claude-plugin/plugin.json']

const parse = version => (/^(\d+)\.(\d+)\.(\d+)$/.exec(version || '') || []).slice(1).map(Number)
export function newer(a, b) {
  const [x, y] = [parse(a), parse(b)]
  if (x.length !== 3 || y.length !== 3) return false
  for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] > y[i]
  return false
}

// Pure decision, for the self-test: the problems with this change, or none.
export function check({ changed, base, head }) {
  const problems = []
  if (new Set(head).size > 1) problems.push(`the two manifests disagree: ${MANIFESTS.map((m, i) => `${m} ${head[i]}`).join(', ')}`)
  const released = changed.filter(path => RELEASED.test(path))
  if (released.length && !newer(head[0], base)) {
    problems.push(`plugin code changed (${released.slice(0, 3).join(', ')}${released.length > 3 ? ', ...' : ''}) but the version is ${head[0]}, not above ${base} on the base branch. Bump "version" in ${MANIFESTS.join(' and ')} (x.y.Z for fixes, x.Y.0 for features).`)
  }
  return problems
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const git = (...args) => execFileSync('git', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()
  const base = process.argv[2] || `origin/${process.env.GITHUB_BASE_REF || 'main'}`
  let baseVersion
  let changed
  try {
    git('rev-parse', '--verify', base)
    baseVersion = JSON.parse(git('show', `${base}:plugin.json`)).version
    changed = git('diff', '--name-only', `${base}...HEAD`).split('\n').filter(Boolean)
  } catch {
    console.log(`- version check skipped: base ${base} not found (new repository or no remote yet)`)
    process.exit(0)
  }
  const head = MANIFESTS.map(path => JSON.parse(readFileSync(path, 'utf8')).version)
  const problems = check({ changed, base: baseVersion, head })
  for (const problem of problems) console.error(`✘ version: ${problem}`)
  if (problems.length) process.exit(1)
  console.log(changed.some(path => RELEASED.test(path))
    ? `✔ version: ${baseVersion} → ${head[0]}`
    : `✔ version: no plugin code changed, no bump needed (${head[0]})`)
}
