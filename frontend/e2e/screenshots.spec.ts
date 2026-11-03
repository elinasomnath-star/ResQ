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
  const attributionLayout = await mapAttribution.evaluate((attribution) => {
    const attributionBox = attribution.getBoundingClientRect();
    const controlsBox = document.querySelector('.map-layer-controls')?.getBoundingClientRect();
    return {
      overlaps: Boolean(controlsBox && attributionBox.left < controlsBox.right && attributionBox.right > controlsBox.left && attributionBox.top < controlsBox.bottom && attributionBox.bottom > controlsBox.top),
      attribution: { left: attributionBox.left, top: attributionBox.top, right: attributionBox.right, bottom: attributionBox.bottom },
      controls: controlsBox && { left: controlsBox.left, top: controlsBox.top, right: controlsBox.right, bottom: controlsBox.bottom },
    };
  });
  expect(attributionLayout.overlaps, `map attribution must not cover layer controls: ${JSON.stringify(attributionLayout)}`).toBe(false);
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
  await expect(resourcePool.getByText('25,000 allocated')).toBeVisible();
  await expect(resourcePool.getByText('75,000 allocated')).toBeVisible();
  await expect(resourcePool.getByText('697 allocated')).toBeVisible();
  await page.getByRole('button', { name: 'Round 2', exact: true }).click();
  await expect(resourcePool.getByText('0 allocated').first()).toBeVisible();
  await expect(resourcePool.getByText('16 allocated')).toBeVisible();
  await page.getByRole('button', { name: 'Round 1', exact: true }).click();
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
    { selector: 'button[title="Shortage alerts"]', close: 'Close Alerts', file: 'screenshot_escalation.png' },
  ];
  for (const item of targets) {
    const button = 'selector' in item
      ? page.locator(item.selector)
      : page.getByRole('button', { name: item.button, exact: true });
    if (!(await button.isVisible().catch(() => false))) continue;
    await button.click();
    await page.waitForTimeout(350);
    if (item.file === 'screenshot_scenario_deck.png') {
      await expect(page.getByText('5 Bantwal Road Blockage Scenarios')).toBeVisible();
      await expect(page.getByRole('button', { name: 'Run scenario: Block Netravati Bridge + Kalladka Highway' })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Run scenario: Block Three Bantwal Main Roads' })).toBeVisible();
    }
    if (item.file === 'screenshot_shelter_inventory.png') {
      await expect(page.getByText(/Showing \d+ of \d+ event-confirmed sites/)).toBeVisible();
      await expect(page.getByText(/ddmp-designated/)).toHaveCount(0);
    }
    await page.screenshot({ path: path.join(demoDir, item.file) });
    await page.getByRole('button', { name: item.close }).click();
  }

  await page.locator('header button[title="Data sources & limitations"]').click();
  await expect(page.getByRole('heading', { name: 'About ResQ & Analytical Boundaries' })).toBeVisible();
  await page.screenshot({ path: path.join(demoDir, 'screenshot_about_limits.png') });
  await page.locator('.glass-panel-elevated button').first().click();
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

test('Selecting each road scenario recalculates all Bantwal routes live', async ({ page }) => {
  test.setTimeout(180000);
  await enterAsOperator(page);
  await page.getByRole('button', { name: 'Scenarios', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Run scenario: Block Netravati Bridge', exact: true })).toBeVisible();
  const scenarios: [string, string, number][] = [
    ['bantwal_netravati_bridge', 'Block Netravati Bridge', 1],
    ['bantwal_kalladka_highway', 'Block Kalladka-Kanhangad Highway', 1],
    ['bantwal_bakrabail_road', 'Block Bakrabail-Salethur-Vitla Road', 1],
    ['bantwal_netravati_kalladka_multi', 'Block Netravati Bridge + Kalladka Highway', 2],
    ['bantwal_three_main_roads_multi', 'Block Three Bantwal Main Roads', 3],
  ];
  const closureDataResponse = await page.request.get('/data/bantwal_scenario_closures.geojson');
  expect(closureDataResponse.ok()).toBe(true);
  const closureFeatures = (await closureDataResponse.json()).features as Array<{
    properties: { closure_id: string; closure_points: number[][] };
    geometry: { type: string; coordinates: number[][][] };
  }>;
  for (const [scenarioId, , blockedRoadCount] of scenarios) {
    const feature = closureFeatures.find((item) => item.properties.closure_id === scenarioId);
    expect(feature, `${scenarioId} red map feature should exist`).toBeDefined();
    expect(feature?.properties.closure_points).toHaveLength(blockedRoadCount);
    expect(feature?.geometry.type).toBe('MultiLineString');
  }
  for (const [scenarioId, title, blockedRoadCount] of scenarios) {
    const reroute = page.waitForResponse((response) =>
      response.url().endsWith('/scenario-reroutes') && response.request().method() === 'POST'
      && response.request().postDataJSON()?.scenario_id === scenarioId, { timeout: 60000 });
    await page.getByRole('button', { name: `Run scenario: ${title}`, exact: true }).click();
    const response = await reroute;
    expect(response.ok(), `${title} should reroute successfully`).toBeTruthy();
    const result = await response.json();
    expect(result.blocked_roads, `${scenarioId} blocked road response: ${JSON.stringify(result)}`).toHaveLength(blockedRoadCount);
    expect(result.closure_points, `${scenarioId} closure marker response: ${JSON.stringify(result.closure_points)}`).toHaveLength(blockedRoadCount);
    const usesMiniTownHall = result.blocked_roads.includes('Netravati Bridge');
    const miniTownHallRoutes = result.zone_routes.filter(
      (route: { origin_id: string }) => route.origin_id === 'mini_town_hall_mangaluru',
    );
    if (usesMiniTownHall) {
      expect(result.routing_origin_ids).toContain('mini_town_hall_mangaluru');
      expect(miniTownHallRoutes.length, `${scenarioId} should route at least one zone from Mini Town Hall`).toBeGreaterThan(0);
      await expect(page.getByTestId('mini-town-hall-map-label')).toBeVisible();
    } else {
      expect(result.routing_origin_ids, `${scenarioId} should omit Mini Town Hall`).not.toContain('mini_town_hall_mangaluru');
      expect(miniTownHallRoutes).toHaveLength(0);
      await expect(page.getByTestId('mini-town-hall-map-label')).toBeHidden();
    }
    expect(result.route_count).toBe(16);
    expect(result.zone_routes).toHaveLength(16);
    expect(new Set(result.zone_routes.map((route: { zone_id: string }) => route.zone_id)).size).toBe(16);
    expect(result.routes.length).toBeLessThanOrEqual(16);
    for (const zoneRoute of result.zone_routes) {
      const hasMapGeometry = result.routes.some((route: { properties: { zone_id: string } }) =>
        route.properties.zone_id === zoneRoute.zone_id,
      );
      expect(hasMapGeometry).toBe(zoneRoute.delivery_mode !== 'none');
    }
    await expect(page.getByRole('status')).toContainText('16 routes recalculated', { timeout: 15000 });
  }
  const nonNetravatiReroute = page.waitForResponse((response) =>
    response.url().endsWith('/scenario-reroutes') && response.request().method() === 'POST'
    && response.request().postDataJSON()?.scenario_id === 'bantwal_kalladka_highway', { timeout: 60000 });
  await page.getByRole('button', { name: 'Run scenario: Block Kalladka-Kanhangad Highway', exact: true }).click();
  const nonNetravatiResult = await nonNetravatiReroute;
  expect(nonNetravatiResult.ok()).toBe(true);
  expect((await nonNetravatiResult.json()).blocked_roads).toEqual(['Kalladka-Kanhangad Highway']);
  await expect(page.getByTestId('mini-town-hall-map-label')).toBeHidden();
  await page.getByRole('button', { name: 'Close Scenario Deck' }).click();
  await expect(page.locator('aside.w-80')).toBeVisible();
  await page.locator('.resq-zone-marker').nth(15).click();
  await page.waitForTimeout(250);
  await expect(page.getByRole('heading', { name: 'Bantwal zone 16' })).toBeVisible();
  await page.screenshot({ path: path.join(demoDir, 'screenshot_zone_drawer.png') });
  await page.screenshot({ path: path.join(demoDir, 'screenshot_timeline_closure.png') });
});
