import { test, expect } from '@playwright/test';

test.describe('ResQ Role-Based Access Control and Authentication', () => {
  test('Viewer login: verifies role badge, disabled operator controls, and logout', async ({ page }) => {
    // 1. Navigate to App (starts on landing page)
    await page.goto('/');

    // Landing page uses the response-console entry point.
    const launchBtn = page.getByRole('button', { name: 'Open response console' });
    await expect(launchBtn).toBeVisible({ timeout: 10000 });
    await launchBtn.click();

    // 3. Fill Viewer Credentials via preset button
    const viewerPresetBtn = page.locator('button:has-text("Viewer")');
    await expect(viewerPresetBtn).toBeVisible({ timeout: 5000 });
    await viewerPresetBtn.click();

    // Submit Login
    const signInBtn = page.locator('button:has-text("Enter Command Console")');
    await expect(signInBtn).toBeVisible();
    await signInBtn.click();

    // 4. Verify Console is reached and Viewer badge is displayed in header
    const roleBadge = page.locator('header span:has-text("viewer")');
    await expect(roleBadge).toBeVisible({ timeout: 15000 });

    // 5. Check that operator controls (e.g. Closure trigger) are disabled or show operator warning
    const closureBtn = page.locator('button:has-text("Trigger Closure"), button:has-text("Closure Control")');
    if (await closureBtn.isVisible()) {
      await expect(closureBtn).toBeDisabled();
      const title = await closureBtn.getAttribute('title');
      expect(title).toContain('Operator role required');
    }

    // 6. Log out
    const logoutBtn = page.locator('button[title*="Sign out"], button:has-text("Sign out")');
    await expect(logoutBtn).toBeVisible();
    await logoutBtn.click();

    // 7. Verify returned to login view
    await expect(page.locator('button:has-text("Enter Command Console")')).toBeVisible({ timeout: 10000 });
  });

  test('Operator login: verifies role badge, enabled operator controls, and logout', async ({ page }) => {
    await page.goto('/');

    // If on landing, click launch
    const launchBtn = page.getByRole('button', { name: 'Open response console' });
    if (await launchBtn.isVisible()) {
      await launchBtn.click();
    }

    // Fill Operator Credentials via preset button
    const operatorPresetBtn = page.locator('button:has-text("Operator")');
    await expect(operatorPresetBtn).toBeVisible({ timeout: 5000 });
    await operatorPresetBtn.click();

    // Submit Login
    const signInBtn = page.locator('button:has-text("Enter Command Console")');
    await expect(signInBtn).toBeVisible();
    await signInBtn.click();

    // Verify Console is reached and Operator badge is displayed in header
    const operatorBadge = page.locator('header span:has-text("operator")');
    await expect(operatorBadge).toBeVisible({ timeout: 15000 });

    // Check that operator controls (e.g. Trigger Closure) are enabled for operator
    const closureBtn = page.locator('button:has-text("Trigger Closure")');
    if (await closureBtn.isVisible()) {
      await expect(closureBtn).toBeEnabled();
    }

    // Log out
    const logoutBtn = page.locator('button[title*="Sign out"], button:has-text("Sign out")');
    await expect(logoutBtn).toBeVisible();
    await logoutBtn.click();

    // Verify returned to login view
    await expect(page.locator('button:has-text("Enter Command Console")')).toBeVisible({ timeout: 10000 });
  });
});
