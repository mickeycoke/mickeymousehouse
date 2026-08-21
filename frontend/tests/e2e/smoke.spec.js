import { test, expect } from './fixtures.js'

test('app loads without crashing', async ({ page }) => {
  await page.goto('/')
  await expect(page).not.toHaveTitle('Error')
})
