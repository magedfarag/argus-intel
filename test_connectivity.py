"""Quick connectivity test for all remote backend APIs."""
import requests, time

BASE = "http://localhost:8000"
GEOM = {"type": "Polygon", "coordinates": [[[31.2,30.0],[31.3,30.0],[31.3,30.1],[31.2,30.1],[31.2,30.0]]]}

print("=" * 60)
print("  SERVICE CONNECTIVITY TEST")
print("=" * 60)

# Health
h = requests.get(f"{BASE}/api/health").json()
print(f"\nHealth: {h['status']} | Redis: {h['redis']} | Celery: {h['celery_worker']}")
for p, s in h["providers"].items():
    status = "OK" if s == "ok" else "FAIL: " + s
    print(f"  {p:12s} {status}")

# Sentinel-2
print("\n--- Sentinel-2 (Copernicus STAC) ---")
t0 = time.time()
r = requests.post(f"{BASE}/api/search", json={
    "geometry": GEOM, "start_date": "2026-02-27", "end_date": "2026-03-28",
    "provider": "sentinel2", "cloud_threshold": 30, "max_results": 3
})
dt = time.time() - t0
if r.ok:
    d = r.json()
    print(f"  OK ({dt:.1f}s) | Provider: {d['provider']} | Scenes: {d['total']}")
    for s in d["scenes"]:
        print(f"    {s['scene_id'][:50]} | cloud={s['cloud_cover']}% | {s['acquired_at']}")
else:
    print(f"  FAIL ({r.status_code}) {r.text[:200]}")

# Landsat
print("\n--- Landsat (USGS STAC) ---")
t0 = time.time()
r2 = requests.post(f"{BASE}/api/search", json={
    "geometry": GEOM, "start_date": "2026-02-27", "end_date": "2026-03-28",
    "provider": "landsat", "cloud_threshold": 30, "max_results": 3
})
dt = time.time() - t0
if r2.ok:
    d2 = r2.json()
    print(f"  OK ({dt:.1f}s) | Provider: {d2['provider']} | Scenes: {d2['total']}")
    for s in d2["scenes"]:
        print(f"    {s['scene_id'][:50]} | cloud={s['cloud_cover']}% | {s['acquired_at']}")
else:
    print(f"  FAIL ({r2.status_code}) {r2.text[:200]}")

# Demo sync analysis
print("\n--- Demo Provider (sync analysis) ---")
t0 = time.time()
r3 = requests.post(f"{BASE}/api/analyze", json={
    "geometry": GEOM, "start_date": "2026-02-27", "end_date": "2026-03-28",
    "provider": "demo"
})
dt = time.time() - t0
if r3.ok:
    d3 = r3.json()
    print(f"  OK ({dt:.1f}s) | Analysis: {d3['analysis_id'][:20]}... | Changes: {len(d3['changes'])}")
    for c in d3["changes"]:
        print(f"    {c['change_type']} | confidence={c['confidence']}%")
else:
    print(f"  FAIL ({r3.status_code}) {r3.text[:200]}")

print("\n" + "=" * 60)
print("  DONE")
print("=" * 60)
