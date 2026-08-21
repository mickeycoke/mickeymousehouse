// "We need to eliminate the multiple ports with differing features on dev
// so there is one truth that can be tested."
//
// A port number carries no identity, so the build states what it is. These tests
// guard that mechanism: if the stamp disappears, the whole class of "which
// branch am I even looking at" confusion comes back silently.
import { execSync } from 'node:child_process'
import { test, expect } from './fixtures.js'

const headSha = () => {
  try {
    return execSync('git rev-parse --short HEAD', { encoding: 'utf8' }).trim()
  } catch {
    return ''
  }
}

test.describe('One dev truth — the served build identifies itself', () => {
  test('index.html carries a pt-dev-build stamp matching this checkout', async ({ page }) => {
    const res = await page.request.get('/')
    expect(res.ok()).toBeTruthy()
    const html = await res.text()

    const stamp = /name="pt-dev-build"\s+content="([^"]*)"/.exec(html)?.[1]
    expect(stamp, 'no pt-dev-build meta tag — vite.config.js must stamp it').toBeTruthy()

    const sha = headSha()
    test.skip(!sha, 'not a git checkout')
    expect(stamp, `served "${stamp}" but this checkout is at "${sha}"`).toContain(sha)

    // The checkout path is what distinguishes two worktrees on the SAME branch,
    // which is how 5175 / 5178 / 5180 were indistinguishable from each other.
    const checkout = /name="pt-dev-checkout"\s+content="([^"]*)"/.exec(html)?.[1]
    expect(checkout, 'no pt-dev-checkout meta tag').toBeTruthy()
  })

  test('the badge is visible on screen and names the branch', async ({ page }) => {
    await page.goto('/login')
    const badge = page.locator('[data-testid="dev-build-badge"]')
    await expect(badge, 'the dev badge must be visible on a local surface').toBeVisible()

    const sha = headSha()
    test.skip(!sha, 'not a git checkout')
    // data-build is the machine-readable copy; the visible text is truncated by
    // CSS on narrow screens, so assert against the attribute.
    await expect(badge).toHaveAttribute('data-build', new RegExp(sha))
  })

  test('only ONE frontend dev server is running', async () => {
    // The failure being prevented: six servers, two branches, and the owner
    // testing whichever port they happened to remember. Counted from the OS,
    // not from config, because config is not what was lying.
    let listeners = []
    try {
      const out = execSync(
        "lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | awk '/node/ && $9 ~ /:51[0-9][0-9]$/ {print $9}' | sort -u",
        { encoding: 'utf8', shell: '/bin/bash' },
      ).trim()
      listeners = out ? out.split('\n') : []
    } catch {
      test.skip(true, 'lsof unavailable')
    }
    expect(
      listeners.length,
      `expected exactly one frontend dev server, found ${listeners.length}: ${listeners.join(', ')}. ` +
      'Each extra one may serve a different branch. Stop the strays.',
    ).toBeLessThanOrEqual(1)
  })
})
