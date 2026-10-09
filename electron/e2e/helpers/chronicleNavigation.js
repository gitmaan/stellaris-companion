const { expect } = require('@playwright/test')

// The same workflows run with a pinned rail or the compact chapter drawer.
async function openChapterNavigation(page) {
  const opener = page.locator('button[aria-controls="chronicle-navigation"]')
  if (await opener.isVisible() && await opener.getAttribute('aria-expanded') !== 'true') {
    await opener.click()
  }
  const navigation = page.getByRole('complementary')
  await expect(navigation).toBeVisible()
  return navigation
}

async function closeChapterNavigation(page) {
  const opener = page.locator('button[aria-controls="chronicle-navigation"]')
  if (await opener.isVisible() && await opener.getAttribute('aria-expanded') === 'true') {
    await page.keyboard.press('Escape')
    await expect(opener).toHaveAttribute('aria-expanded', 'false')
  }
}

module.exports = { openChapterNavigation, closeChapterNavigation }
