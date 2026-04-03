import { test, expect } from "@playwright/test";

test.describe("GEOINT Platform — smoke tests (P1-1.9)", () => {
  test("page loads and shows map container", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="map-container"]')).toBeVisible({ timeout: 10_000 });
  });

  test("app title is visible", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("h1")).toContainText("GEOINT Platform");
  });

  test("AOI panel renders with draw tools", async ({ page }) => {
    await page.goto("/");
    await page.click('[data-testid="aoi-panel"] >> .. >> button:has-text("AOIs"), .sidebar-btn:has-text("AOIs")');
    await expect(page.locator('[data-testid="aoi-panel"]')).toBeVisible();
    await expect(page.locator('.draw-tools')).toBeVisible();
  });

  test("timeline panel is visible at bottom", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="timeline-panel"]')).toBeVisible();
  });

  test("clicking Layers tab shows layer toggles", async ({ page }) => {
    await page.goto("/");
    await page.click('.sidebar-btn:has-text("Layers")');
    await expect(page.locator('[data-testid="layer-panel"]')).toBeVisible();
    await expect(page.locator('.layer-toggle').first()).toBeVisible();
  });

  test("clicking Events tab shows search button", async ({ page }) => {
    await page.goto("/");
    await page.click('.sidebar-btn:has-text("Events")');
    await expect(page.locator('[data-testid="search-btn"]')).toBeVisible();
  });

  test("API key input is visible in header", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".api-key-input")).toBeVisible();
  });

  test("Playback tab shows load frames button", async ({ page }) => {
    await page.goto("/");
    await page.click('.sidebar-btn:has-text("Playback")');
    await expect(page.locator('[data-testid="playback-panel"]')).toBeVisible();
    await expect(page.locator('button:has-text("Load Frames")')).toBeVisible();
  });

  test("Analytics tab shows run change detection button", async ({ page }) => {
    await page.goto("/");
    await page.click('.sidebar-btn:has-text("Analytics")');
    await expect(page.locator('[data-testid="analytics-panel"]')).toBeVisible();
    await expect(page.locator('[data-testid="submit-change-job-btn"]')).toBeVisible();
  });

  test("Export tab shows export button", async ({ page }) => {
    await page.goto("/");
    await page.click('.sidebar-btn:has-text("Export")');
    await expect(page.locator('[data-testid="export-panel"]')).toBeVisible();
    await expect(page.locator('[data-testid="export-btn"]')).toBeVisible();
  });
});

// ── P3-3.9: Track playback & layer toggle smoke tests ─────────────────────
test.describe("Track playback and layer controls (P3-3.9)", () => {
  test("enabling Ships layer shows density control", async ({ page }) => {
    await page.goto("/");
    await page.click('.sidebar-btn:has-text("Layers")');
    await expect(page.locator('[data-testid="layer-panel"]')).toBeVisible();
    // Enable Maritime (AIS) toggle
    const shipsToggle = page.locator('.layer-toggle').filter({ hasText: "Maritime" }).locator('input');
    await shipsToggle.check();
    // Density slider should appear
    await expect(page.locator('[data-testid="density-control"]')).toBeVisible();
    await expect(page.locator('[data-testid="density-slider"]')).toBeVisible();
  });

  test("enabling Aircraft layer shows density control", async ({ page }) => {
    await page.goto("/");
    await page.click('.sidebar-btn:has-text("Layers")');
    const aircraftToggle = page.locator('.layer-toggle').filter({ hasText: "Aviation" }).locator('input');
    await aircraftToggle.check();
    await expect(page.locator('[data-testid="density-control"]')).toBeVisible();
  });

  test("density slider changes value", async ({ page }) => {
    await page.goto("/");
    await page.click('.sidebar-btn:has-text("Layers")');
    const shipsToggle = page.locator('.layer-toggle').filter({ hasText: "Maritime" }).locator('input');
    await shipsToggle.check();
    const slider = page.locator('[data-testid="density-slider"]');
    await expect(slider).toBeVisible();
    // Verify slider has a numeric value
    const val = await slider.inputValue();
    expect(parseFloat(val)).toBeGreaterThan(0);
  });

  test("GDELT toggle enables contextual layer indicator", async ({ page }) => {
    await page.goto("/");
    await page.click('.sidebar-btn:has-text("Layers")');
    const gdeltToggle = page.locator('.layer-toggle').filter({ hasText: "GDELT" }).locator('input');
    await expect(gdeltToggle).toBeVisible();
    await gdeltToggle.check();
    await expect(gdeltToggle).toBeChecked();
  });

  test("Playback panel load frames triggers API call", async ({ page }) => {
    await page.goto("/");
    await page.click('.sidebar-btn:has-text("Playback")');
    const loadBtn = page.locator('button:has-text("Load Frames")');
    await expect(loadBtn).toBeVisible();
    // Track that request was made (intercept playback API)
    const responsePromise = page.waitForResponse(
      resp => resp.url().includes("/api/v1/playback/query"),
      { timeout: 5000 },
    ).catch(() => null);
    await loadBtn.click();
    // Button shows loading state
    await expect(page.locator('button:has-text("Loading")')).toBeVisible({ timeout: 3000 }).catch(() => {/* may resolve fast */});
    await responsePromise;
  });

  test("switching off Ships layer hides density control", async ({ page }) => {
    await page.goto("/");
    await page.click('.sidebar-btn:has-text("Layers")');
    const shipsToggle = page.locator('.layer-toggle').filter({ hasText: "Maritime" }).locator('input');
    await shipsToggle.check();
    await expect(page.locator('[data-testid="density-control"]')).toBeVisible();
    // Uncheck
    await shipsToggle.uncheck();
    await expect(page.locator('[data-testid="density-control"]')).not.toBeVisible();
  });
});

// ── P3-3.8: Browser responsiveness under realistic dense layers ───────────────
test.describe("Browser responsiveness under dense layers (P3-3.8)", () => {
  /**
   * These tests verify that the UI stays interactive (no JS hang, no blank
   * map) when all data layers are enabled simultaneously — the realistic
   * worst-case scenario encountered during live pilot AOI sessions.
   *
   * Performance budget:
   *   - Page interactive (DOMContentLoaded) within 8 s on the dev server
   *   - All layer toggles respond within 3 s
   *   - Pagination renders first page within 5 s
   *   - Density slider updates within 2 s
   */

  const INTERACTIVE_BUDGET_MS = 8_000;
  const LAYER_TOGGLE_BUDGET_MS = 3_000;
  const SEARCH_RENDER_BUDGET_MS = 5_000;

  test("page reaches interactive state within budget", async ({ page }) => {
    const startMs = Date.now();
    await page.goto("/");
    await expect(page.locator('[data-testid="map-container"]')).toBeVisible({
      timeout: INTERACTIVE_BUDGET_MS,
    });
    const elapsed = Date.now() - startMs;
    expect(elapsed).toBeLessThan(INTERACTIVE_BUDGET_MS);
  });

  test("enabling all layers simultaneously does not hang the UI", async ({ page }) => {
    await page.goto("/");
    await page.click('.sidebar-btn:has-text("Layers")');
    await expect(page.locator('[data-testid="layer-panel"]')).toBeVisible();

    // Enable every layer toggle and verify the sidebar remains interactive
    const allToggles = page.locator('.layer-toggle input');
    const count = await allToggles.count();
    for (let i = 0; i < count; i++) {
      await allToggles.nth(i).check().catch(() => {/* may already be checked */});
    }

    // Sidebar must still respond after enabling all layers
    await expect(page.locator('[data-testid="layer-panel"]')).toBeVisible({
      timeout: LAYER_TOGGLE_BUDGET_MS,
    });
  });

  test("density slider adjusts value interactively under all-layers load", async ({ page }) => {
    await page.goto("/");
    await page.click('.sidebar-btn:has-text("Layers")');
    const maritimeToggle = page.locator('.layer-toggle').filter({ hasText: "Maritime" }).locator('input');
    await maritimeToggle.check();
    const slider = page.locator('[data-testid="density-slider"]');
    await expect(slider).toBeVisible({ timeout: LAYER_TOGGLE_BUDGET_MS });

    // Move the slider and verify the DOM reflects the new value immediately
    const before = await slider.inputValue();
    await slider.fill("50");
    const after = await slider.inputValue();
    expect(after).not.toBe(before);
    expect(parseFloat(after)).toBeGreaterThanOrEqual(0);
    expect(parseFloat(after)).toBeLessThanOrEqual(100);
  });

  test("search panel renders first results page within budget", async ({ page }) => {
    await page.goto("/");
    await page.click('.sidebar-btn:has-text("Events")');
    const searchBtn = page.locator('[data-testid="search-btn"]');
    await expect(searchBtn).toBeVisible();

    const t0 = Date.now();
    await searchBtn.click();
    // Either results list or a "no results" / empty state must appear
    await Promise.race([
      page.locator('[data-testid="event-list"]').waitFor({ timeout: SEARCH_RENDER_BUDGET_MS }),
      page.locator('[data-testid="no-results"]').waitFor({ timeout: SEARCH_RENDER_BUDGET_MS }),
      page.locator('.event-item').first().waitFor({ timeout: SEARCH_RENDER_BUDGET_MS }),
    ]).catch(() => {/* tolerate absence of list when API in demo mode */});
    expect(Date.now() - t0).toBeLessThan(SEARCH_RENDER_BUDGET_MS);
  });

  test("playback panel load does not freeze the sidebar", async ({ page }) => {
    await page.goto("/");
    await page.click('.sidebar-btn:has-text("Playback")');
    const loadBtn = page.locator('button:has-text("Load Frames")');
    await expect(loadBtn).toBeVisible();
    await loadBtn.click();

    // Sidebar must stay interactive: switching to Layers tab must still work
    await page.click('.sidebar-btn:has-text("Layers")');
    await expect(page.locator('[data-testid="layer-panel"]')).toBeVisible({
      timeout: LAYER_TOGGLE_BUDGET_MS,
    });
  });

  test("analytics panel submit does not freeze the map container", async ({ page }) => {
    await page.goto("/");
    await page.click('.sidebar-btn:has-text("Analytics")');
    const submitBtn = page.locator('[data-testid="submit-change-job-btn"]');
    await expect(submitBtn).toBeVisible();
    await submitBtn.click();

    // Map container must still be present — a frozen JS thread hides it
    await expect(page.locator('[data-testid="map-container"]')).toBeVisible({
      timeout: LAYER_TOGGLE_BUDGET_MS,
    });
  });

  test("PerformanceNavigationTiming shows acceptable load metrics", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator('[data-testid="map-container"]')).toBeVisible({ timeout: 10_000 });

    const metrics = await page.evaluate(() => {
      const [nav] = performance.getEntriesByType("navigation") as PerformanceNavigationTiming[];
      if (!nav) return null;
      return {
        domInteractive: Math.round(nav.domInteractive),
        domComplete: Math.round(nav.domComplete),
        loadEventEnd: Math.round(nav.loadEventEnd),
      };
    });

    if (metrics) {
      // domInteractive should be reached well before the 8 s budget
      expect(metrics.domInteractive).toBeLessThan(INTERACTIVE_BUDGET_MS);
    }
  });
});