import { chromium } from '@playwright/test';
import * as path from 'path';
import * as fs from 'fs';

async function capture() {
  const demoDir = path.resolve(__dirname, '../../demo');
  if (!fs.existsSync(demoDir)) {
    fs.mkdirSync(demoDir, { recursive: true });
  }

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();

  console.log('1. Capturing Landing Page...');
  await page.goto('http://localhost:5173');
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(demoDir, 'screenshot_landing.png') });

  console.log('2. Capturing Login Page...');
  const launchBtn = page.locator('button:has-text("Launch Command Console")');
  await launchBtn.click();
  await page.waitForTimeout(800);
  await page.screenshot({ path: path.join(demoDir, 'screenshot_login.png') });

  console.log('3. Logging in as Operator & Capturing Console...');
  const opPreset = page.locator('button:has-text("Operator")');
  await opPreset.click();
  const enterBtn = page.locator('button:has-text("Enter Command Console")');
  await enterBtn.click();
  await page.waitForTimeout(2500); // Wait for map and layers to render
  await page.screenshot({ path: path.join(demoDir, 'screenshot_console_main.png') });

  console.log('4. Capturing Zone Drawer...');
  // Click on the map center or trigger zone drawer
  const zoneBtn = page.locator('div:has-text("Zone 10"), div:has-text("Bantwal_Z10")').first();
  if (await zoneBtn.isVisible()) {
    await zoneBtn.click();
  } else {
    // Click center of map canvas
    await page.mouse.click(960, 540);
  }
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(demoDir, 'screenshot_zone_drawer.png') });

  console.log('5. Capturing Step Timeline & Closure...');
  // Click on Step 2 node or trigger closure
  const step2Btn = page.locator('span:has-text("Closure")').first();
  if (await step2Btn.isVisible()) {
    await step2Btn.click();
  }
  const triggerClosureBtn = page.locator('button:has-text("Trigger Closure")');
  if (await triggerClosureBtn.isVisible()) {
    await triggerClosureBtn.click();
  }
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(demoDir, 'screenshot_timeline_closure.png') });

  console.log('6. Capturing Compare View...');
  const compareNavBtn = page.locator('button:has-text("Compare")');
  await compareNavBtn.click();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(demoDir, 'screenshot_compare_view.png') });
  const closeCompare = page.locator('button:has-text("Close")').first();
  await closeCompare.click();
  await page.waitForTimeout(500);

  console.log('7. Capturing Escalations Modal...');
  const alertsBtn = page.locator('button:has-text("Alerts")');
  await alertsBtn.click();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(demoDir, 'screenshot_escalations.png') });
  const dismissEsc = page.locator('button:has-text("Dismiss")').first();
  if (await dismissEsc.isVisible()) {
    await dismissEsc.click();
  } else {
    await page.keyboard.press('Escape');
  }
  await page.waitForTimeout(500);

  console.log('8. Capturing About & Limits Modal...');
  const aboutBtn = page.locator('button[title*="architecture"], button[title*="Data sources"]').first();
  await aboutBtn.click();
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(demoDir, 'screenshot_about_limits.png') });
  const dismissAbout = page.locator('button:has-text("Dismiss")').first();
  await dismissAbout.click();
  await page.waitForTimeout(500);

  console.log('9. Capturing Guided Walkthrough Stepper...');
  const walkBtn = page.locator('button:has-text("Walkthrough"), button[title*="Walkthrough"]').first();
  if (await walkBtn.isVisible()) {
    await walkBtn.click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(demoDir, 'screenshot_guided_walkthrough.png') });
  }

  await browser.close();
  console.log('All screenshots captured successfully into demo/');
}

capture().catch((err) => {
  console.error('Screenshot error:', err);
  process.exit(1);
});
