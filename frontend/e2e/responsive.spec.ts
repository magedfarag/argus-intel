import { test, expect } from "./fixtures";
import { BasePage } from "./pages";

/**
 * Viewport and responsive behavior tests.
 * Verifies the app renders correctly at different viewport sizes.
 */

test.describe("Responsive — desktop viewport", () => {
  test("standard desktop (1920x1080) renders correctly", async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    const base = new BasePage(page);
    await base.goto();
    await expect(base.header).toBeVisible();
    await expect(base.sidebar).toBeVisible();
    await expect(
      base.mapContainer.or(base.globeContainer).first(),
    ).toBeVisible();
  });

  test("small desktop (1366x768) renders correctly", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    const base = new BasePage(page);
    await base.goto();
    await expect(base.header).toBeVisible();
    await expect(base.sidebar).toBeVisible();
  });
});

test.describe("Responsive — narrow viewport", () => {
  test("narrow viewport (800x600) does not crash", async ({ page }) => {
    await page.setViewportSize({ width: 800, height: 600 });
    const base = new BasePage(page);
    await base.goto();
    // Header and core layout should still render
    await expect(base.header).toBeVisible();
  });

  test("panels operate correctly at narrow width", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    const base = new BasePage(page);
    await base.goto();

    // Open a panel and verify it renders
    await base.openPanel("Sensors");
    const layerPanel = page.locator('[data-testid="layer-panel"]');
    await expect(layerPanel).toBeVisible();
  });

  test("map shell shrinks with the viewport without horizontal overflow", async ({ page }) => {
    const base = new BasePage(page);

    await page.setViewportSize({ width: 1280, height: 800 });
    await base.goto();

    const mapSurface = base.mapContainer.or(base.globeContainer).first();
    const wideBox = await mapSurface.boundingBox();

    await page.setViewportSize({ width: 800, height: 600 });
    await page.waitForTimeout(300);

    const narrowBox = await mapSurface.boundingBox();
    const hasHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    );

    expect(wideBox?.width ?? 0).toBeGreaterThan(0);
    expect(narrowBox?.width ?? 0).toBeGreaterThan(0);
    expect(narrowBox?.width ?? 0).toBeLessThan(wideBox?.width ?? Number.POSITIVE_INFINITY);
    expect(hasHorizontalOverflow).toBeFalsy();
  });
});

test.describe("Responsive — large viewport", () => {
  test("ultra-wide (2560x1440) renders without layout breakage", async ({ page }) => {
    await page.setViewportSize({ width: 2560, height: 1440 });
    const base = new BasePage(page);
    await base.goto();
    await expect(base.header).toBeVisible();
    await expect(base.sidebar).toBeVisible();
    await expect(
      base.mapContainer.or(base.globeContainer).first(),
    ).toBeVisible();
  });
});
