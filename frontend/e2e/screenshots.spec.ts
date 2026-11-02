import { test, expect } from '@playwright/test';
import * as path from 'path';

const demoDir = path.resolve(process.cwd(), '../demo');

async function enterAsOperator(page: import('@playwright/test').Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'Open response console' }).click();
  await page.locator('.role-btn').filter({ hasText: 'Operator' }).click();
  await page.getByRole('button', { name: 'Enter Command Console' }).click();
  await expect(page.locator('header button[title="Click to switch role"]')).toContainText('operator', { timeout: 15000 });
}

test('Refresh current ResQ interface screenshots', async ({ page }) => {
  test.setTimeout(90000);
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /When the river rises/ })).toBeVisible();
  await page.screenshot({ path: path.join(demoDir, 'screenshot_landing.png'), fullPage: true });

  await page.getByRole('button', { name: 'Open response console' }).click();
  await expect(page.getByRole('heading', { name: 'Sign in to ResQ' })).toBeVisible();
  await page.screenshot({ path: path.join(demoDir, 'screenshot_login.png'), fullPage: true });

  await page.locator('.role-btn').filter({ hasText: 'Operator' }).click();
  await page.getByRole('button', { name: 'Enter Command Console' }).click();
  await expect(page.locator('header button[title="Click to switch role"]')).toContainText('operator', { timeout: 15000 });
  await page.waitForSelector('.maplibregl-canvas', { timeout: 15000 });
  await expect(page.locator('.resq-zone-marker')).toHaveCount(16, { timeout: 15000 });
  const facilityLabels = page.getByTestId('facility-map-label');
  await expect(facilityLabels).toHaveCount(2, { timeout: 15000 });
  const facilityLabelOverlap = await facilityLabels.evaluateAll((labels) => {
    const boxes = labels.map((label) => label.getBoundingClientRect());
    return boxes.some((box, index) => boxes.slice(index + 1).some((other) =>
      box.left < other.right && box.right > other.left && box.top < other.bottom && box.bottom > other.top,
    ));
  });
  expect(facilityLabelOverlap).toBe(false);
  await page.waitForTimeout(1300);
  await expect(page.getByText('MOD 10', { exact: true })).toHaveCount(0);
  await expect(page.locator('.maplibregl-ctrl-top-right')).toBeHidden();
  const legend = page.getByRole('complementary', { name: 'Map legend' });
  await expect(legend).toBeVisible();
  const legendOverlap = await legend.evaluate((element) => {
    const legendBox = element.getBoundingClientRect();
    const leftRailBox = document.querySelector('.console-left-rail')?.getBoundingClientRect();
    const bottomBoxes = Array.from(document.querySelectorAll('.stock-sensitivity, .step-timeline')).map((item) => item.getBoundingClientRect());
    const intersects = (box: DOMRect) => legendBox.left < box.right && legendBox.right > box.left && legendBox.top < box.bottom && legendBox.bottom > box.top;
    return Boolean((leftRailBox && intersects(leftRailBox)) || bottomBoxes.some(intersects));
  });
  expect(legendOverlap).toBe(false);
  const mapAttribution = page.locator('.maplibregl-ctrl-attrib');
  await expect(mapAttribution).toBeVisible();
  const attributionOverlapsLayerControls = await mapAttribution.evaluate((attribution) => {
    const attributionBox = attribution.getBoundingClientRect();
    const controlsBox = document.querySelector('.map-layer-controls')?.getBoundingClientRect();
    return Boolean(controlsBox && attributionBox.left < controlsBox.right && attributionBox.right > controlsBox.left && attributionBox.top < controlsBox.bottom && attributionBox.bottom > controlsBox.top);
  });
  expect(attributionOverlapsLayerControls).toBe(false);
  const overlayAlignment = await page.locator('.console-bottom-overlays').evaluate((container) => {
    const stock = container.querySelector('.stock-sensitivity')?.getBoundingClientRect();
    const timeline = container.querySelector('.step-timeline')?.getBoundingClientRect();
    const controls = document.querySelector('.map-layer-controls')?.getBoundingClientRect();
    return {
      sameLeft: Boolean(stock && timeline && Math.abs(stock.left - timeline.left) < 1),
      sameRight: Boolean(stock && timeline && Math.abs(stock.right - timeline.right) < 1),
      controlsGap: stock && controls ? controls.left - stock.right : -1,
    };
  });
  expect(overlayAlignment.sameLeft).toBe(true);
  expect(overlayAlignment.sameRight).toBe(true);
  expect(overlayAlignment.controlsGap).toBeGreaterThanOrEqual(12);
  const resourcePool = page.getByLabel('Assumed Resource Pool');
  await expect(resourcePool.getByText('This round +25,000')).toBeVisible();
  await expect(resourcePool.getByText('This round +75,000')).toBeVisible();
  await expect(resourcePool.getByText('This round +697')).toBeVisible();
  await page.getByRole('button', { name: 'Go to round 2, closure scenario step' }).click();
  await expect(resourcePool.getByText('This round +0').first()).toBeVisible();
  await expect(resourcePool.getByText('This round +16')).toBeVisible();
  await page.getByRole('button', { name: 'Go to round 1' }).click();
  const timelineOverlaps = await page.locator('.step-timeline-toolbar').evaluate((toolbar) => {
    const boxes = Array.from(toolbar.children).map((child) => child.getBoundingClientRect());
    return boxes.some((box, index) => boxes.slice(index + 1).some((other) =>
      box.left < other.right && box.right > other.left && box.top < other.bottom && box.bottom > other.top,
    ));
  });
  expect(timelineOverlaps).toBe(false);
  const stepperAlignment = await page.locator('.step-scrubber').evaluate((scrubber) => {
    const track = scrubber.querySelector('.step-track')?.getBoundingClientRect();
    const points = Array.from(scrubber.querySelectorAll('.step-point'));
    if (!track || points.length < 2) return { aligned: false };
    const trackCenterY = track.top + track.height / 2;
    const first = points[0].getBoundingClientRect();
    const last = points[points.length - 1].getBoundingClientRect();
    return {
      aligned: Math.abs(trackCenterY - (first.top + first.height / 2)) <= 1
        && Math.abs(trackCenterY - (last.top + last.height / 2)) <= 1,
    };
  });
  expect(stepperAlignment.aligned).toBe(true);
  await page.mouse.move(1200, 500);
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(demoDir, 'screenshot_console_main.png') });

  const targets = [
    { button: 'View curves', close: 'Close Curves Modal', file: 'screenshot_scarcity_curves.png' },
    { button: 'Scenarios', close: 'Close Scenario Deck', file: 'screenshot_scenario_deck.png' },
    { button: 'Shelters', close: 'Close Shelter Inventory', file: 'screenshot_shelter_inventory.png' },
    { button: 'Override', close: 'Close Admin Override', file: 'screenshot_admin_override.png' },
    { button: 'Compare', close: 'Close comparison', file: 'screenshot_compare_view.png' },
    { button: 'Alerts', close: 'Close Alerts', file: 'screenshot_escalations.png' },
  ];
  for (const item of targets) {
    const button = page.getByRole('button', { name: item.button, exact: true });
    if (!(await button.isVisible().catch(() => false))) continue;
    await button.click();
    await page.waitForTimeout(350);
    if (item.file === 'screenshot_shelter_inventory.png') {
      await expect(page.getByText(/Showing \d+ of \d+ event-confirmed sites/)).toBeVisible();
      await expect(page.getByText(/ddmp-designated/)).toHaveCount(0);
    }
    await page.screenshot({ path: path.join(demoDir, item.file) });
    await page.getByRole('button', { name: item.close }).click();
  }
});

test('Shelter names remain readable and do not overlap on the map', async ({ page }) => {
  test.setTimeout(60000);
  await enterAsOperator(page);
  await expect(page.locator('.maplibregl-canvas')).toBeVisible({ timeout: 15000 });
  const labels = page.getByTestId('facility-map-label');
  await expect(labels).toHaveCount(2, { timeout: 15000 });
  await expect(labels.filter({ hasText: 'SVS Kannada Medium School' })).toBeVisible();
  await expect(labels.filter({ hasText: 'Panemangaluru relief centre' })).toBeVisible();
  const geometry = await labels.evaluateAll((elements) => {
    const boxes = elements.map((element) => {
      const rect = element.getBoundingClientRect();
      return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
    });
    const [first, second] = boxes;
    return {
      overlap: first.left < second.right && first.right > second.left
        && first.top < second.bottom && first.bottom > second.top,
      readableSize: elements.every((element) => Number.parseFloat(getComputedStyle(element).fontSize) >= 12),
    };
  });
  expect(geometry.overlap).toBe(false);
  expect(geometry.readableSize).toBe(true);
  await page.screenshot({ path: path.join(demoDir, 'screenshot_console_shelter_labels.png') });
});

test('Selecting a scenario executes it live and loads an allocation run into the console', async ({ page }) => {
  test.setTimeout(120000);
  await enterAsOperator(page);
  await page.getByRole('button', { name: 'Scenarios', exact: true }).click();
  const scenarioRun = page.waitForResponse((response) =>
    response.url().endsWith('/scenarios/run') && response.request().method() === 'POST', { timeout: 60000 });
  const allocationRun = page.waitForResponse((response) =>
    response.url().endsWith('/simulate') && response.request().method() === 'POST', { timeout: 60000 });
  await page.getByRole('button', { name: /Run scenario: Documented Replay.*2019/ }).click();
  const [scenarioResponse, allocationResponse] = await Promise.all([scenarioRun, allocationRun]);
  expect(scenarioResponse.ok()).toBeTruthy();
  expect(allocationResponse.ok()).toBeTruthy();
  const allocation = await allocationResponse.json();
  expect(allocation.run_id).not.toMatch(/^offline_run_/);
  await expect(page.getByText('Live API run')).toBeVisible();
  await expect(page.getByText(/Unmet demand \d+(?:\.\d+)?%/)).toBeVisible();
});

test('Verified road closure recalculates routes against the cached OSM graph', async ({ page }) => {
  test.setTimeout(240000);
  const runtimeErrors: string[] = [];
  page.on('pageerror', (error) => { runtimeErrors.push(error.message); });
  page.on('console', (message) => { if (message.type() === 'error') console.error('Browser console error:', message.text()); });
  await enterAsOperator(page);
  await expect(page.getByRole('button', { name: 'ONLINE' })).toBeVisible({ timeout: 10000 });
  await expect(page.locator('.maplibregl-canvas')).toBeVisible({ timeout: 15000 });
  const responsePromise = page.waitForResponse((response) =>
    response.url().endsWith('/closures') && response.request().method() === 'POST', { timeout: 220000 });
  await page.getByRole('button', { name: 'Apply Verified Closure' }).click();
  await expect(page.getByRole('button', { name: 'Applying Verified Closure' })).toBeVisible();
  const response = await responsePromise;
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  expect(payload.applied_closure_id).toBeTruthy();
  expect(payload.module7_routes.zone_count).toBe(16);
  expect(payload.module7_routes.road_count + payload.module7_routes.secondary_count + payload.module7_routes.unreachable_count).toBe(16);
  await expect(page.getByRole('button', { name: 'Closure Applied' })).toBeVisible({ timeout: 30000 });
  await expect(page.getByRole('status')).toContainText('16 routes recalculated', { timeout: 30000 });
  await page.waitForFunction(() => {
    const map = (window as any).__resq_map;
    return map?.getLayoutProperty('closure_marker_label_layer', 'visibility') === 'visible'
      && map.querySourceFeatures('closure_marker_source').length > 0;
  });
  const allocationPanel = await page.getByText('Allocated vs Need', { exact: true }).locator('..').locator('..').innerText();
  for (const resource of ['Food Rations', 'Water (Litres)', 'Medical Kits']) {
    const escapedResource = resource.replace('(', '\\(').replace(')', '\\)');
    const match = allocationPanel.match(new RegExp(`${escapedResource}\\s+([\\d,]+)\\s*\\/\\s*([\\d,]+)`));
    expect(match, `${resource} should show one consistent demand value`).toBeTruthy();
    expect(Number(match![1].replaceAll(',', ''))).toBeLessThanOrEqual(Number(match![2].replaceAll(',', '')));
  }
  expect(runtimeErrors).toEqual([]);
  await page.screenshot({ path: path.join(demoDir, 'screenshot_timeline_closure.png') });
});
