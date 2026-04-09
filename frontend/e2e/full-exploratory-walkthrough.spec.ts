import fs from "node:fs";
import path from "node:path";
import type { Locator, Page } from "@playwright/test";
import { test, expect } from "./fixtures";

const DEMO_VIEWPORT = { width: 1920, height: 1080 };
const DEMO_PACING = {
  short: 700,
  medium: 1_400,
  long: 2_400,
  scene: 3_800,
};

function logDemo(message: string): void {
  if (process.env.DEMO_DEBUG) {
    console.log(`[demo] ${message}`);
  }
}

// Run exploratory walkthrough serially - it's a comprehensive GPU-intensive demo
test.describe.configure({ mode: 'serial' });

test.use({
  headless: true,
  viewport: DEMO_VIEWPORT,
  video: {
    mode: "on",
    size: DEMO_VIEWPORT,
  },
});

const DEFAULT_LAYERS = {
  showAois: true,
  showImagery: true,
  showEvents: true,
  showGdelt: true,
  showShips: true,
  showAircraft: true,
  trackDensity: 1.0,
  imageryOpacity: 0.1,
  showOrbits: false,
  showAirspace: false,
  showJamming: false,
  showStrikes: false,
  showTerrain: false,
  show3dBuildings: false,
  showDetections: false,
  showSignals: true,
};

const TWO_D_SHIP_LAYERS = ["entity-ships-civilian", "entity-ships-military"] as const;
const TWO_D_AIRCRAFT_LAYERS = ["entity-aircraft-civilian", "entity-aircraft-military"] as const;
const TWO_D_CONTEXT_LAYERS = [
  ...TWO_D_SHIP_LAYERS,
  ...TWO_D_AIRCRAFT_LAYERS,
  "events-circle",
  "gdelt-point",
  "signals-point",
  "imagery-fill",
] as const;

const AUTH_ENV_KEYS = ["ANALYST_API_KEY", "OPERATOR_API_KEY", "ADMIN_API_KEY", "API_KEY"] as const;
type WalkthroughAoiSummary = {
  id: string;
  name: string;
  tags?: string[];
};

function cleanEnvValue(raw: string): string {
  const trimmed = raw.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function resolveBackendApiKey(): string {
  for (const key of AUTH_ENV_KEYS) {
    const value = process.env[key];
    if (value?.trim()) return value.trim();
  }

  const envCandidates = [
    path.resolve(process.cwd(), ".env"),
    path.resolve(process.cwd(), "..", ".env"),
    path.resolve(process.cwd(), "..", "..", ".env"),
  ];

  for (const envPath of envCandidates) {
    if (!fs.existsSync(envPath)) continue;

    const envFile = fs.readFileSync(envPath, "utf8");
    for (const key of AUTH_ENV_KEYS) {
      const match = envFile.match(new RegExp(`^${key}=(.*)$`, "m"));
      if (match?.[1]) return cleanEnvValue(match[1]);
    }
  }

  return "";
}

const backendApiKey = resolveBackendApiKey();

function resolvePreferredWalkthroughAoiId(
  aois: WalkthroughAoiSummary[] | undefined,
): string | null {
  if (!aois || aois.length === 0) return null;

  return (
    aois.find((aoi) => /^strait of hormuz$/i.test(aoi.name))?.id ??
    aois.find((aoi) => aoi.tags?.some((tag) => /demo/i.test(tag)) && /hormuz/i.test(aoi.name))?.id ??
    aois.find((aoi) => /hormuz/i.test(aoi.name) && !/inspection/i.test(aoi.name))?.id ??
    aois.find((aoi) => /hormuz/i.test(aoi.name))?.id ??
    aois[0]?.id ??
    null
  );
}

type ProjectedFeature = {
  x: number;
  y: number;
  props: Record<string, unknown>;
  geometryType: string;
};

async function primeAppState(page: Page): Promise<void> {
  if (backendApiKey) {
    await page.context().addCookies([
      {
        name: "api_key",
        value: backendApiKey,
        domain: "localhost",
        path: "/",
        sameSite: "Lax",
      },
      {
        name: "api_key",
        value: backendApiKey,
        domain: "127.0.0.1",
        path: "/",
        sameSite: "Lax",
      },
    ]).catch(() => {});
  }

  const aoisResponse = await page.request.get("http://127.0.0.1:8000/api/v1/aois", {
    headers: backendApiKey ? { Authorization: `Bearer ${backendApiKey}` } : undefined,
  });
  const aoisPayload = (await aoisResponse.json()) as {
    items?: WalkthroughAoiSummary[];
  };
  const preferredAoiId = resolvePreferredWalkthroughAoiId(aoisPayload.items);

  await page.addInitScript(({ layers, preferredAoiId, apiKey }) => {
    localStorage.setItem("geoint:activePanel", JSON.stringify("aoi"));
    localStorage.setItem("geoint:viewMode", JSON.stringify("3d"));
    localStorage.setItem("geoint:layers", JSON.stringify(layers));
    if (apiKey) {
      localStorage.setItem("geoint_api_key", apiKey);
      document.cookie = `api_key=${encodeURIComponent(apiKey)}; path=/; SameSite=Lax`;
    }
    if (preferredAoiId) {
      localStorage.setItem("geoint:selectedAoiId", JSON.stringify(preferredAoiId));
    }
    window.open = () => null;
  }, { layers: DEFAULT_LAYERS, preferredAoiId, apiKey: backendApiKey });
}

async function waitForArgusMap(page: Page): Promise<void> {
  await expect
    .poll(
      async () =>
        page.evaluate(
          () => !!(window as Window & { __argusMap?: unknown }).__argusMap,
        ),
      { timeout: 35_000 },
    )
    .toBe(true);
}

async function pause(page: Page, ms: number): Promise<void> {
  await page.waitForTimeout(ms);
}

async function slowClick(
  page: Page,
  locator: Locator,
  waitAfter = DEMO_PACING.medium,
): Promise<void> {
  await locator.scrollIntoViewIfNeeded();
  await locator.click({ delay: 180 });
  await pause(page, waitAfter);
}

async function openPanel(page: Page, label: string): Promise<void> {
  await slowClick(page, page.locator(`.sidebar-btn:has-text("${label}")`), DEMO_PACING.short);
}

async function switchView(page: Page, mode: "2d" | "3d"): Promise<void> {
  if (mode === "2d") {
    await slowClick(page, page.getByRole("button", { name: "2D" }), DEMO_PACING.short);
    await expect(page.getByTestId("map-container")).toBeVisible({ timeout: 15_000 });
  } else {
    await slowClick(page, page.getByRole("button", { name: "🌐 3D" }), DEMO_PACING.short);
    await expect(page.getByTestId("globe-container")).toBeVisible({ timeout: 15_000 });
  }
  await waitForArgusMap(page);
  await pause(page, DEMO_PACING.medium);
}

async function jumpMap(
  page: Page,
  options: { center: [number, number]; zoom: number; pitch?: number; bearing?: number },
): Promise<void> {
  await page.evaluate(({ center, zoom, pitch, bearing }) => {
    const map = (window as Window & { __argusMap?: any }).__argusMap;
    if (!map) throw new Error("ARGUS map is not available");
    map.stop?.();
    map.jumpTo({
      center,
      zoom,
      pitch: pitch ?? map.getPitch?.() ?? 0,
      bearing: bearing ?? map.getBearing?.() ?? 0,
    });
  }, options);
  await pause(page, DEMO_PACING.medium);
}

async function flyMap(
  page: Page,
  options: { center: [number, number]; zoom: number; pitch?: number; bearing?: number },
  duration = 3_600,
): Promise<void> {
  await page.evaluate(
    ({ center, zoom, pitch, bearing, duration }) =>
      new Promise<void>((resolve) => {
        const map = (window as Window & { __argusMap?: any }).__argusMap;
        if (!map) throw new Error("ARGUS map is not available");

        let resolved = false;
        const finish = () => {
          if (resolved) return;
          resolved = true;
          resolve();
        };

        map.stop?.();
        map.once?.("moveend", finish);
        map.easeTo({
          center,
          zoom,
          pitch: pitch ?? map.getPitch?.() ?? 0,
          bearing: bearing ?? map.getBearing?.() ?? 0,
          duration,
          essential: true,
        });
        window.setTimeout(finish, duration + 500);
      }),
    { ...options, duration },
  );
  await pause(page, DEMO_PACING.medium);
}

async function getRenderedFeature(
  page: Page,
  layerId: string,
  index = 0,
): Promise<ProjectedFeature | null> {
  return page.evaluate(
    ({ layerId, index }) => {
      const map = (window as Window & { __argusMap?: any }).__argusMap;
      if (!map) return null;

      const features = map.queryRenderedFeatures(undefined, { layers: [layerId] });
      const feature = features[index];
      if (!feature) return null;

      let lngLat: [number, number] | null = null;
      const geometry = feature.geometry as GeoJSON.Geometry;

      if (geometry.type === "Point") {
        lngLat = (geometry as GeoJSON.Point).coordinates as [number, number];
      } else if (geometry.type === "Polygon") {
        const ring = (geometry as GeoJSON.Polygon).coordinates[0];
        const lngs = ring.map(([lng]) => lng);
        const lats = ring.map(([, lat]) => lat);
        lngLat = [
          (Math.min(...lngs) + Math.max(...lngs)) / 2,
          (Math.min(...lats) + Math.max(...lats)) / 2,
        ];
      } else if (geometry.type === "MultiPolygon") {
        const ring = (geometry as GeoJSON.MultiPolygon).coordinates[0][0];
        const lngs = ring.map(([lng]) => lng);
        const lats = ring.map(([, lat]) => lat);
        lngLat = [
          (Math.min(...lngs) + Math.max(...lngs)) / 2,
          (Math.min(...lats) + Math.max(...lats)) / 2,
        ];
      }

      if (!lngLat) return null;
      const projected = map.project(lngLat);
      return {
        x: projected.x,
        y: projected.y,
        props: feature.properties ?? {},
        geometryType: geometry.type,
      };
    },
    { layerId, index },
  );
}

async function clickRenderedFeature(
  page: Page,
  layerId: string,
  index = 0,
  canvas: Locator = page.locator(".maplibregl-canvas").first(),
): Promise<ProjectedFeature> {
  const feature = await getRenderedFeature(page, layerId, index);
  if (!feature) throw new Error(`No rendered feature found for layer ${layerId}`);

  const box = await canvas.boundingBox();
  if (!box) throw new Error(`Canvas bounds are unavailable for layer ${layerId}`);

  await page.mouse.click(box.x + feature.x, box.y + feature.y);
  await pause(page, DEMO_PACING.medium);
  return feature;
}

async function waitForRenderedFeatureCount(
  page: Page,
  layerId: string,
  minCount = 1,
  timeout = 30_000,
): Promise<void> {
  await expect
    .poll(
      async () =>
        page.evaluate((layerId) => {
          const map = (window as Window & { __argusMap?: any }).__argusMap;
          if (!map || !map.getLayer?.(layerId)) return 0;
          return map.queryRenderedFeatures(undefined, { layers: [layerId] }).length;
        }, layerId),
      { timeout },
    )
    .toBeGreaterThanOrEqual(minCount);
}

async function waitForAnyRenderedFeatureCount(
  page: Page,
  layerIds: string[],
  minCount = 1,
  timeout = 30_000,
): Promise<number> {
  const deadline = Date.now() + timeout;
  let latestCount = 0;

  while (Date.now() < deadline) {
    latestCount = await page.evaluate((layerIds) => {
      const map = (window as Window & { __argusMap?: any }).__argusMap;
      if (!map) return 0;

      return layerIds.reduce((total, layerId) => {
        if (!map.getLayer?.(layerId)) return total;
        return total + map.queryRenderedFeatures(undefined, { layers: [layerId] }).length;
      }, 0);
    }, layerIds);

    if (latestCount >= minCount) return latestCount;
    await pause(page, 1_000);
  }

  return latestCount;
}

function sumLayerCounts(
  counts: Record<string, number>,
  layerIds: readonly string[],
): number {
  return layerIds.reduce((sum, layerId) => sum + (counts[layerId] ?? 0), 0);
}

async function clickFirstRenderedFeature(
  page: Page,
  layerIds: readonly string[],
  counts: Record<string, number>,
): Promise<string | null> {
  const targetLayer = layerIds.find((layerId) => (counts[layerId] ?? 0) > 0);
  if (!targetLayer) return null;

  await clickRenderedFeature(page, targetLayer);
  return targetLayer;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function dragMap(
  page: Page,
  options: {
    from: [number, number];
    to: [number, number];
    steps?: number;
    canvas?: Locator;
  },
): Promise<void> {
  const canvas = options.canvas ?? page.locator(".maplibregl-canvas").first();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("Map canvas bounds are unavailable");

  const startX = box.x + box.width * options.from[0];
  const startY = box.y + box.height * options.from[1];
  const endX = box.x + box.width * options.to[0];
  const endY = box.y + box.height * options.to[1];

  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(endX, endY, { steps: options.steps ?? 28 });
  await page.mouse.up();
  await pause(page, DEMO_PACING.medium);
}

async function zoomMap(
  page: Page,
  options: {
    deltaY: number;
    repeats?: number;
    canvas?: Locator;
  },
): Promise<void> {
  const canvas = options.canvas ?? page.locator(".maplibregl-canvas").first();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("Map canvas bounds are unavailable");

  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
  for (let i = 0; i < (options.repeats ?? 1); i += 1) {
    await page.mouse.wheel(0, options.deltaY);
    await pause(page, DEMO_PACING.short);
  }
}

async function clickZoomControls(
  page: Page,
  direction: "in" | "out",
  repeats = 1,
): Promise<void> {
  const control = page.locator(
    direction === "in" ? ".maplibregl-ctrl-zoom-in" : ".maplibregl-ctrl-zoom-out",
  ).first();
  for (let i = 0; i < repeats; i += 1) {
    await slowClick(page, control, DEMO_PACING.short);
  }
}

async function setLayer(page: Page, label: string, checked: boolean): Promise<void> {
  const toggle = page
    .getByTestId("layer-panel")
    .locator("label", { hasText: new RegExp(`^\\s*${escapeRegExp(label)}\\s*$`) })
    .locator('input[type="checkbox"]');

  if ((await toggle.isChecked()) !== checked) {
    if (checked) {
      await toggle.check();
    } else {
      await toggle.uncheck();
    }
    await pause(page, DEMO_PACING.short);
  }
}

async function closeMapPopup(page: Page): Promise<void> {
  const visibleButtons = page.locator(".maplibregl-popup-close-button:visible");
  for (let attempt = 0; attempt < 3; attempt += 1) {
    if ((await visibleButtons.count()) === 0) break;
    await visibleButtons.last().click({ delay: 120, force: true });
    await pause(page, 250);
  }
  await page.evaluate(() => {
    document.querySelectorAll(".maplibregl-popup").forEach((popup) => popup.remove());
  });
  await pause(page, 150);
}

async function setRangeValue(locator: Locator, value: number): Promise<void> {
  await locator.evaluate((element, nextValue) => {
    const input = element as HTMLInputElement;
    input.value = String(nextValue);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
}

async function cycleBasemaps(page: Page): Promise<void> {
  const buttons = page.locator(".basemap-picker .basemap-btn");
  const count = await buttons.count();
  for (let i = 0; i < count; i += 1) {
    await slowClick(page, buttons.nth(i), DEMO_PACING.short);
  }
}

async function exerciseZoneToolButtons(page: Page): Promise<void> {
  await openPanel(page, "Zones");
  await expect(page.getByTestId("aoi-panel")).toBeVisible();

  const bboxBtn = page.getByTestId("aoi-panel").getByRole("button", { name: /BBox/i });
  const polygonBtn = page.getByTestId("aoi-panel").getByRole("button", { name: /Polygon/i });

  await slowClick(page, bboxBtn, DEMO_PACING.short);
  await expect(page.locator(".draw-hint")).toContainText(/corners/i);
  await slowClick(page, bboxBtn, DEMO_PACING.short);

  await slowClick(page, polygonBtn, DEMO_PACING.short);
  await expect(page.locator(".draw-hint")).toContainText(/vertices|double-click/i);
  await slowClick(page, polygonBtn, DEMO_PACING.short);
}

async function createInspectionAoi(
  page: Page,
  options: {
    name: string;
    center: [number, number];
    zoom: number;
    firstCorner: [number, number];
    secondCorner: [number, number];
  },
): Promise<{ saved: boolean; selected: boolean }> {
  logDemo(`AOI create start: ${options.name}`);
  await switchView(page, "2d");
  await openPanel(page, "Zones");
  await flyMap(page, { center: options.center, zoom: options.zoom, pitch: 0, bearing: 0 }, 3_200);

  await slowClick(
    page,
    page.getByTestId("aoi-panel").getByRole("button", { name: /BBox/i }),
    DEMO_PACING.short,
  );

  const projected = await page.evaluate(({ firstCorner, secondCorner }) => {
    const map = (window as Window & { __argusMap?: any }).__argusMap;
    if (!map) throw new Error("2D map not available");
    return {
      p1: map.project(firstCorner),
      p2: map.project(secondCorner),
    };
  }, options);

  const canvas = page.locator(".maplibregl-canvas").first();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("2D map canvas bounds not available");

  await page.mouse.click(box.x + projected.p1.x, box.y + projected.p1.y);
  await pause(page, DEMO_PACING.short);
  await page.mouse.click(box.x + projected.p2.x, box.y + projected.p2.y);
  await expect(page.getByTestId("aoi-name-input")).toBeVisible({ timeout: 5_000 });
  await page.getByTestId("aoi-name-input").fill(options.name);
  await slowClick(page, page.getByRole("button", { name: "Save AOI" }), DEMO_PACING.long);
  logDemo(`AOI save clicked: ${options.name}`);

  const createdItem = page.getByTestId("aoi-item").filter({ hasText: options.name }).first();
  const itemVisible = await createdItem
    .waitFor({ state: "visible", timeout: 12_000 })
    .then(() => true)
    .catch(() => false);

  if (itemVisible) {
    await slowClick(page, createdItem, DEMO_PACING.scene);
    logDemo(`AOI selected from list: ${options.name}`);
  } else {
    logDemo(`AOI row did not appear in time: ${options.name}`);
  }

  return { saved: true, selected: itemVisible };
}

async function getVisibleLayerCounts(
  page: Page,
  layerIds: string[],
): Promise<Record<string, number>> {
  return page.evaluate((layerIds) => {
    const map = (window as Window & { __argusMap?: any }).__argusMap;
    if (!map) throw new Error("ARGUS map is not available");

    const counts: Record<string, number> = {};
    for (const layerId of layerIds) {
      if (!map.getLayer?.(layerId)) {
        counts[layerId] = 0;
        continue;
      }
      counts[layerId] = map.queryRenderedFeatures(undefined, { layers: [layerId] }).length;
    }
    return counts;
  }, layerIds);
}

test.describe("Exploratory Full Walkthrough", () => {
  test("records a full cross-panel exploratory pass", async ({ page }, testInfo) => {
    test.slow();

    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    const observations: string[] = [];

    observations.push(`Auth configured for walkthrough: ${Boolean(backendApiKey)}`);

    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => pageErrors.push(err.message));

    await primeAppState(page);
    await page.goto("/?demoMode=true");
    logDemo("app loaded");

    await expect(page.getByRole("heading", { name: "ARGUS" })).toBeVisible({ timeout: 20_000 });
    await expect(page.locator(".live-badge")).toContainText("LIVE");
    await waitForArgusMap(page);
    await expect(page.getByTestId("globe-container")).toBeVisible();
    await pause(page, DEMO_PACING.scene);

    await test.step("3D globe navigation with slow cinematic interactions", async () => {
      logDemo("3D step start");
      await openPanel(page, "Sensors");
      await expect(page.getByTestId("layer-panel")).toBeVisible();
      await setLayer(page, "AOI Boundaries", true);
      await setLayer(page, "Imagery Footprints", true);
      await setLayer(page, "Events", true);
      await setLayer(page, "GDELT Context", true);
      await setLayer(page, "Maritime (AIS)", true);
      await setLayer(page, "Aviation (ADS-B)", true);
      await setLayer(page, "Satellite Orbits", true);
      await setLayer(page, "Airspace NFZ/TFR", true);
      await setLayer(page, "GPS Jamming", true);
      await setLayer(page, "Strike Events", true);
      await setLayer(page, "3D Buildings", true);
      await setLayer(page, "Detections (AI)", true);
      await setLayer(page, "Intel Signals", true);
      await setRangeValue(page.getByTestId("density-slider"), 0.8);
      await setRangeValue(page.getByTestId("imagery-opacity-slider"), 0.35);
      await pause(page, DEMO_PACING.short);

      await switchView(page, "3d");
      await flyMap(page, { center: [48.5, 22.5], zoom: 3.1, pitch: 28, bearing: 8 }, 4_800);
      await flyMap(page, { center: [54.8, 25.1], zoom: 4.8, pitch: 42, bearing: -10 }, 4_600);
      await zoomMap(page, { deltaY: -340, repeats: 2 });
      await dragMap(page, { from: [0.68, 0.56], to: [0.48, 0.48], steps: 34 });
      await flyMap(page, { center: [56.52, 26.35], zoom: 6.5, pitch: 48, bearing: -20 }, 4_000);
      const visible3dFeatures = await waitForAnyRenderedFeatureCount(
        page,
        ["g-entity-ships", "g-events", "g-gdelt", "g-signals", "g-dark-ships", "g-choke-fill"],
        1,
        45_000,
      );
      if (visible3dFeatures === 0) {
        observations.push("3D globe navigation completed without queryable rendered features in the current run.");
      }

      const globeCounts = await getVisibleLayerCounts(page, [
        "g-entity-ships",
        "g-events",
        "g-gdelt",
        "g-signals",
        "g-dark-ships",
        "g-choke-fill",
      ]);
      observations.push(`3D Hormuz visible layer counts: ${JSON.stringify(globeCounts)}`);

      if (globeCounts["g-entity-ships"] > 0) {
        await clickRenderedFeature(page, "g-entity-ships");
        await expect(page.locator(".maplibregl-popup-content").last()).toContainText("SHIP");
        await expect(page.locator(".maplibregl-popup-content").last()).toContainText(/Speed|Last seen/);
        await pause(page, DEMO_PACING.long);
        await closeMapPopup(page);
      } else {
        observations.push("3D ship layer was not rendered in the current headed run.");
      }

      if (globeCounts["g-dark-ships"] > 0) {
        await clickRenderedFeature(page, "g-dark-ships");
        await expect(page.locator(".maplibregl-popup-content").last()).toContainText("DARK SHIP");
        await expect(page.locator(".maplibregl-popup-content").last()).toContainText("Confidence");
        await pause(page, DEMO_PACING.long);
        await closeMapPopup(page);
      }

      if (globeCounts["g-events"] > 0) {
        await clickRenderedFeature(page, "g-events");
        await expect(page.locator(".maplibregl-popup-content").last()).toContainText("INTEL EVENT");
        await expect(page.locator(".maplibregl-popup-content").last()).toContainText(/Type|Confidence/);
        await pause(page, DEMO_PACING.long);
        await closeMapPopup(page);
      } else {
        observations.push("3D event layer was not rendered in the current headed run.");
      }

      if (globeCounts["g-signals"] > 0) {
        observations.push("3D signal layer detected; detailed signal popup validation is covered in the 2D map step to avoid globe instability.");
      } else {
        observations.push("3D signal layer was not rendered in the current headed run.");
      }

      if (globeCounts["g-gdelt"] > 0) {
        observations.push("3D GDELT layer detected; detailed news popup validation is covered in the 2D map step to avoid globe instability.");
      } else {
        observations.push("3D GDELT layer was not rendered in the current headed run.");
      }

      const globeBriefingToggle = page.locator(".globe-intel-toggle");
      if (await globeBriefingToggle.isVisible().catch(() => false)) {
        await slowClick(page, globeBriefingToggle, DEMO_PACING.short);
        const globeAlert = page.locator(".globe-intel-overlay .vessel-alert").first();
        if (await globeAlert.isVisible({ timeout: 10_000 }).catch(() => false)) {
          await slowClick(page, globeAlert, DEMO_PACING.medium);
          const globeBriefingModal = page.getByTestId("vessel-modal");
          if (await globeBriefingModal.isVisible({ timeout: 3_000 }).catch(() => false)) {
            await pause(page, DEMO_PACING.long);
            await slowClick(page, page.locator(".modal-close").last(), DEMO_PACING.short);
          } else {
            observations.push("Globe briefing alert click did not open a vessel modal in the compact overlay.");
          }
        }
        await slowClick(page, globeBriefingToggle, DEMO_PACING.short);
      }

      const playPause = page.locator(".anim-controls .btn").first();
      const reset = page.locator(".anim-controls .btn").nth(1);
      await slowClick(page, playPause, 5_000);
      await slowClick(page, playPause, DEMO_PACING.short);
      await slowClick(page, reset, DEMO_PACING.short);

      for (const mode of ["LOW LIGHT", "NIGHT VISION", "THERMAL", "DAY"]) {
        await slowClick(page, page.getByRole("button", { name: mode }), 1_800);
      }
      logDemo("3D step done");
    });

    await test.step("2D map aircraft, event, signal, GDELT, and imagery inspection", async () => {
      logDemo("2D inspection step start");
      await switchView(page, "2d");
      await clickZoomControls(page, "in", 2);
      await clickZoomControls(page, "out", 1);
      await cycleBasemaps(page);
      await flyMap(page, { center: [55.9, 26.0], zoom: 7.2, pitch: 0, bearing: 0 }, 3_200);
      await zoomMap(page, { deltaY: -260, repeats: 2 });
      await dragMap(page, { from: [0.58, 0.54], to: [0.46, 0.5], steps: 24 });
      await flyMap(page, { center: [56.1, 26.2], zoom: 8, pitch: 0, bearing: 0 }, 2_600);
      const visible2dFeatures = await waitForAnyRenderedFeatureCount(page, [...TWO_D_CONTEXT_LAYERS]);
      if (visible2dFeatures === 0) {
        observations.push("2D inspection view completed without queryable rendered features in the current run.");
      }

      const mapCounts = await getVisibleLayerCounts(page, [...TWO_D_CONTEXT_LAYERS]);
      observations.push(`2D Hormuz visible layer counts: ${JSON.stringify(mapCounts)}`);
      expect(
        sumLayerCounts(mapCounts, TWO_D_CONTEXT_LAYERS),
        "2D monitored area should show visible tracked objects and contextual overlays.",
      ).toBeGreaterThan(0);

      if (sumLayerCounts(mapCounts, TWO_D_SHIP_LAYERS) > 0) {
        await clickFirstRenderedFeature(page, TWO_D_SHIP_LAYERS, mapCounts);
        await expect(page.locator(".maplibregl-popup-content").last()).toContainText("SHIP");
        await expect(page.locator(".maplibregl-popup-content").last()).toContainText(/Speed|Last seen/);
        await pause(page, DEMO_PACING.long);
        await closeMapPopup(page);
        logDemo("2D ship popup done");
      } else {
        observations.push("2D ship layer was not rendered in the current run.");
      }

      if (sumLayerCounts(mapCounts, TWO_D_AIRCRAFT_LAYERS) > 0) {
        await clickFirstRenderedFeature(page, TWO_D_AIRCRAFT_LAYERS, mapCounts);
        await expect(page.locator(".maplibregl-popup-content").last()).toContainText("AIRCRAFT");
        await expect(page.locator(".maplibregl-popup-content").last()).toContainText("Altitude");
        await pause(page, DEMO_PACING.long);
        await closeMapPopup(page);
        logDemo("2D aircraft popup done");
      } else {
        observations.push("2D aircraft layer was not rendered in the current run.");
      }

      if (mapCounts["events-circle"] > 0) {
        await clickRenderedFeature(page, "events-circle");
        await expect(page.locator(".event-detail-card")).toBeVisible();
        await expect(page.locator(".event-detail-card")).toContainText("Collection");
        await pause(page, DEMO_PACING.long);
        await page.locator(".event-detail-card .close-btn").click();
        logDemo("2D event popup done");
      }

      if (mapCounts["gdelt-point"] > 0) {
        await clickRenderedFeature(page, "gdelt-point");
        await expect(page.locator(".maplibregl-popup-content").last()).toContainText("GDELT NEWS");
        await expect(page.locator(".maplibregl-popup-content").last()).toContainText(/Publication|Source/);
        await pause(page, DEMO_PACING.long);
        await closeMapPopup(page);
        logDemo("2D gdelt popup done");
      }

      if (mapCounts["signals-point"] > 0) {
        await clickRenderedFeature(page, "signals-point");
        await expect(page.locator(".maplibregl-popup-content").last()).toContainText("Confidence");
        await pause(page, DEMO_PACING.long);
        await closeMapPopup(page);
        const signalOverlay = page.locator(".event-detail-card");
        if (await signalOverlay.isVisible().catch(() => false)) {
          await signalOverlay.locator(".close-btn").click();
        }
        logDemo("2D signal popup done");
      }

      if (mapCounts["imagery-fill"] > 0) {
        await clickRenderedFeature(page, "imagery-fill");
        await expect(page.locator(".maplibregl-popup-content").last()).toContainText("IMAGERY FOOTPRINT");
        await expect(page.locator(".maplibregl-popup-content").last()).toContainText("Collection");
        await pause(page, DEMO_PACING.long);
        await closeMapPopup(page);
        logDemo("2D imagery popup done");
      }
    });

    await test.step("Zones panel controls and draw mode buttons", async () => {
      logDemo("Zones control step start");
      await switchView(page, "2d");
      await exerciseZoneToolButtons(page);
      logDemo("Zones control step done");
    });

    await test.step("Signals search panel", async () => {
      logDemo("Signals panel step start");
      await openPanel(page, "Signals");
      await expect(page.getByTestId("search-panel")).toBeVisible();
      await slowClick(page, page.getByTestId("search-btn"), DEMO_PACING.long);
      const hasEvents = await page
        .getByTestId("event-item")
        .first()
        .waitFor({ state: "visible", timeout: 20_000 })
        .then(() => true)
        .catch(() => false);
      await pause(page, DEMO_PACING.medium);

      if (hasEvents && await page.getByTestId("pagination-next").isVisible().catch(() => false)) {
        if (!(await page.getByTestId("pagination-next").isDisabled())) {
          await slowClick(page, page.getByTestId("pagination-next"), DEMO_PACING.short);
          await slowClick(page, page.getByTestId("pagination-prev"), DEMO_PACING.short);
        }
      }

      if (hasEvents) {
        await slowClick(page, page.getByTestId("event-item").first(), DEMO_PACING.medium);
        await expect(page.locator(".event-detail-card")).toBeVisible();
        await pause(page, DEMO_PACING.long);
        await page.locator(".event-detail-card .close-btn").click();
      } else {
        observations.push("Signals search completed without visible event rows in the current run.");
      }
      logDemo("Signals panel step done");
    });

    await test.step("Playback panel workflow", async () => {
      logDemo("Replay step start");
      await openPanel(page, "Replay");
      await expect(page.getByTestId("playback-panel")).toBeVisible();
      const loadButtonVisible = await page.getByRole("button", { name: "Load Frames" }).isVisible().catch(() => false);
      observations.push(`Replay load button visible: ${loadButtonVisible}`);

      const selectedAoiId = await page.evaluate(() => {
        const raw = window.localStorage.getItem("geoint:selectedAoiId");
        return raw ? JSON.parse(raw) : null;
      });
      const playbackResponse = await page.request.post("http://127.0.0.1:8000/api/v1/playback/query", {
        headers: backendApiKey ? { Authorization: `Bearer ${backendApiKey}` } : undefined,
        data: {
          ...(selectedAoiId ? { aoi_id: selectedAoiId } : {}),
          start_time: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
          end_time: new Date().toISOString(),
          limit: 50,
        },
      }).catch(() => null);

      if (playbackResponse) {
        const playbackBody = await playbackResponse.json().catch(() => null) as { frames?: unknown[] } | null;
        observations.push(
          `Replay backend query: HTTP ${playbackResponse.status()} with ${playbackBody?.frames?.length ?? 0} frame(s)`,
        );
      } else {
        observations.push("Replay backend query failed to return a response in the current run.");
      }

      await pause(page, DEMO_PACING.long);
      logDemo("Replay step done");
    });

    await test.step("Intel change detection", async () => {
      logDemo("Intel step start");
      await openPanel(page, "Intel");
      await expect(page.getByTestId("analytics-panel")).toBeVisible();
      await slowClick(page, page.getByTestId("submit-change-job-btn"), 2_800);

      const candidate = page.locator(".candidate, .change-candidate").first();
      if (await candidate.isVisible({ timeout: 20_000 }).catch(() => false)) {
        await slowClick(page, candidate.getByRole("button", { name: /Confirm/i }), DEMO_PACING.medium);
      } else {
        observations.push("Intel panel completed without a visible change candidate to confirm.");
      }
      logDemo("Intel step done");
    });

    await test.step("Routes, Dark Ships, Briefing, Diff, Cameras, Extract, Status, and Cases", async () => {
      logDemo("Multi-panel step start");
      await openPanel(page, "Routes");
      await expect(page.getByTestId("chokepoint-panel")).toBeVisible();
      const chokepoints = page.getByTestId("chokepoint-panel").locator(".chokepoint-item");
      if ((await chokepoints.count()) > 0) {
        const beforeCenter = await page.evaluate(() => {
          const map = (window as Window & { __argusMap?: any }).__argusMap;
          return map ? map.getCenter().toArray() : null;
        });
        await slowClick(page, chokepoints.first(), DEMO_PACING.medium);
        const afterCenter = await page.evaluate(() => {
          const map = (window as Window & { __argusMap?: any }).__argusMap;
          return map ? map.getCenter().toArray() : null;
        });
        if (
          beforeCenter &&
          afterCenter &&
          Math.abs(beforeCenter[0] - afterCenter[0]) < 0.001 &&
          Math.abs(beforeCenter[1] - afterCenter[1]) < 0.001
        ) {
          observations.push("Routes panel card click did not move the map in the current build.");
        }
      } else {
        observations.push("Routes panel rendered without chokepoint cards in the current run.");
      }

      await openPanel(page, "Dark Ships");
      await expect(page.getByTestId("dark-ship-panel")).toBeVisible();
      const darkShipItems = page.locator(".dark-ship-item");
      if ((await darkShipItems.count()) > 0) {
        await slowClick(page, darkShipItems.first(), DEMO_PACING.medium);
        await expect(page.getByTestId("vessel-modal")).toBeVisible({ timeout: 10_000 });
        await pause(page, DEMO_PACING.long);
        await page.locator(".modal-close").click();
      } else {
        observations.push("Dark Ships panel rendered without candidate rows in the current run.");
      }

      await openPanel(page, "Briefing");
      await expect(page.getByTestId("intel-briefing-panel")).toBeVisible();
      const firstAlert = page.locator(".vessel-alert").first();
      if (await firstAlert.isVisible().catch(() => false)) {
        await slowClick(page, firstAlert, DEMO_PACING.medium);
        await expect(page.getByTestId("vessel-modal")).toBeVisible({ timeout: 10_000 });
        await pause(page, DEMO_PACING.long);
        await page.locator(".modal-close").click();
      }

      await openPanel(page, "Diff");
      const diffReady = await page
        .locator('.panel-title:has-text("Imagery Compare"), .ic-empty')
        .first()
        .waitFor({ state: "visible", timeout: 10_000 })
        .then(() => true)
        .catch(() => false);
      if (diffReady) {
        const selects = page.locator(".ic-selectors select");
        if ((await selects.count()) >= 2) {
          await slowClick(page, page.locator(".ic-swap button"), DEMO_PACING.medium);
        } else {
          observations.push("Diff panel opened in empty-state mode without before/after selectors.");
        }
      } else {
        observations.push("Diff panel did not become ready in the current run.");
      }

      await openPanel(page, "Cameras");
      await expect(page.getByTestId("camera-feed-panel")).toBeVisible();
      const cameraItems = page.locator(".cam-list-item");
      if ((await cameraItems.count()) > 0) {
        await slowClick(page, cameraItems.first(), DEMO_PACING.medium);
        const playClip = page.getByRole("button", { name: /PLAY/i }).first();
        if (await playClip.isVisible().catch(() => false)) {
          await slowClick(page, playClip, 2_400);
          const stopClip = page.getByRole("button", { name: /Stop/i }).first();
          if (await stopClip.isVisible().catch(() => false)) {
            await slowClick(page, stopClip, DEMO_PACING.short);
          }
        }
        const jumpBtn = page.getByRole("button", { name: /Jump to map location/i }).first();
        if (await jumpBtn.isVisible().catch(() => false)) {
          await slowClick(page, jumpBtn, DEMO_PACING.medium);
        }
      } else {
        observations.push("Cameras panel rendered without camera list items in the current run.");
      }

      await openPanel(page, "Extract");
      await expect(page.getByTestId("export-panel")).toBeVisible();
      await page.locator('[data-testid="export-panel"] select').selectOption("geojson");
      await slowClick(page, page.getByTestId("export-btn"), DEMO_PACING.medium);
      const exportStatus = await expect
        .poll(
          async () =>
            (await page.getByTestId("export-panel").locator("p").textContent()) ?? "",
          { timeout: 30_000 },
        )
        .toMatch(/Done|failed|Error/i)
        .then(() => page.getByTestId("export-panel").locator("p").textContent())
        .catch(() => null);
      if (!exportStatus) {
        observations.push("Export panel submission did not reach a terminal status within the walkthrough timeout.");
      }
      await pause(page, DEMO_PACING.medium);

      await openPanel(page, "Status");
      await expect(page.getByTestId("system-health-page")).toBeVisible({ timeout: 20_000 });
      await slowClick(page, page.getByRole("button", { name: /Refresh/i }), DEMO_PACING.medium);
      const connectorVisible = await page
        .locator('[data-testid^="sh-connector-"]').first()
        .isVisible()
        .catch(() => false);
      if (!connectorVisible) {
        observations.push("Status dashboard opened, but no connector cards were visible after refresh in the current run.");
      }
      await pause(page, DEMO_PACING.medium);

      await openPanel(page, "Cases");
      await expect(page.getByTestId("investigations-panel")).toBeVisible();
      await slowClick(page, page.getByRole("button", { name: /\+ New/i }), DEMO_PACING.short);
      const caseName = `Op-042 ${Date.now()}`;
      await page.getByPlaceholder("Name *").fill(caseName);
      await page.getByPlaceholder("Description").fill("Exploratory monitoring walkthrough case");
      await page.getByPlaceholder("Tags (comma-separated)").fill("demo, exploratory, monitoring");
      await slowClick(page, page.getByRole("button", { name: /^Create$/ }), DEMO_PACING.medium);
      const createdCaseVisible = await page.getByText(caseName).isVisible().catch(() => false);
      if (createdCaseVisible) {
        await slowClick(page, page.getByText(caseName), DEMO_PACING.short);
        await page.getByPlaceholder("Add a note…").fill("Validated the multi-panel investigative workflow.");
        await page.getByPlaceholder("Author (optional)").fill("Playwright");
        await slowClick(page, page.getByRole("button", { name: /Add Note/i }), DEMO_PACING.medium);
        await slowClick(page, page.getByRole("button", { name: /Absence Signals/i }), DEMO_PACING.medium);

        const caseBriefingBtn = page
          .getByTestId("investigations-panel")
          .locator("button", { hasText: "Briefing" })
          .first();
        if (await caseBriefingBtn.isVisible().catch(() => false)) {
          await slowClick(page, caseBriefingBtn, DEMO_PACING.long);
          const caseModalClose = page.locator(".close-btn").last();
          if (await caseModalClose.isVisible().catch(() => false)) {
            await slowClick(page, caseModalClose, DEMO_PACING.short);
          }
        }
      } else {
        observations.push(`Cases panel did not show the newly created investigation "${caseName}" within the walkthrough timeout.`);
      }
      logDemo("Multi-panel step done");
    });

    await test.step("Hormuz inspection AOI monitoring check", async () => {
      logDemo("Timeline/AOI step start");
      await switchView(page, "2d");
      const inspectionAoiName = `Hormuz Inspection ${Date.now()}`;
      const inspectionAoiResult = await createInspectionAoi(page, {
        name: inspectionAoiName,
        center: [56.25, 26.15],
        zoom: 8.1,
        firstCorner: [55.85, 25.88],
        secondCorner: [56.62, 26.42],
      });
      if (!inspectionAoiResult.selected) {
        observations.push(`Monitoring AOI "${inspectionAoiName}" was saved, but its list row did not appear in time for selection.`);
      }
      logDemo("Timeline/AOI post-create flyback start");
      await flyMap(page, { center: [56.22, 26.12], zoom: 8.4, pitch: 0, bearing: 0 }, 2_800);
      await pause(page, DEMO_PACING.scene);
      const inspectionVisibleFeatures = await waitForAnyRenderedFeatureCount(page, [...TWO_D_CONTEXT_LAYERS]);
      if (inspectionVisibleFeatures === 0) {
        observations.push("Hormuz inspection AOI step completed without visible rendered features in the current run.");
      }

      const inspectionCounts = await getVisibleLayerCounts(page, [...TWO_D_CONTEXT_LAYERS]);

      const inspectionTotal = sumLayerCounts(inspectionCounts, TWO_D_CONTEXT_LAYERS);
      observations.push(`Hormuz inspection visible layer counts: ${JSON.stringify(inspectionCounts)}`);
      await pause(page, DEMO_PACING.scene);
      expect(
        inspectionTotal,
        "Newly created monitoring AOIs should surface intersecting map objects instead of an empty area.",
      ).toBeGreaterThan(0);
      if (inspectionTotal === 0) {
        observations.push("Hormuz inspection AOI did not surface monitoring results on the map in the current run.");
      }
      logDemo("Timeline/AOI step done");
    });

    if (pageErrors.length > 0) {
      observations.push(`Page errors: ${pageErrors.join(" | ")}`);
    }
    if (consoleErrors.length > 0) {
      observations.push(`Console errors: ${consoleErrors.join(" | ")}`);
    }

    await testInfo.attach("exploratory-observations.txt", {
      body: observations.join("\n") || "No additional observations recorded.",
      contentType: "text/plain",
    });
    logDemo("test complete");
  });
});
