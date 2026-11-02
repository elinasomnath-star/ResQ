import { test, expect } from '@playwright/test';

test('Landing event selector reports the correct gauge thresholds', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '2026' }).click();
  await expect(page.locator('.gauge-status-pill')).toContainText('Warning level reached');
  await expect(page.locator('.gauge-summary')).toContainText('8.5');
  await page.getByRole('button', { name: '2019' }).click();
  await expect(page.locator('.gauge-status-pill')).toContainText('Danger level reached');
});
