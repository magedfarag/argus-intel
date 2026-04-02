import httpx, json

# Test 1: Landsat with minimal payload (no query/sortby)
print("--- Landsat minimal ---")
payload = {
    "collections": ["landsat-c2l2-sr"],
    "intersects": {"type": "Polygon", "coordinates": [[[31.2,30.0],[31.25,30.0],[31.25,30.05],[31.2,30.05],[31.2,30.0]]]},
    "datetime": "2026-02-27T00:00:00Z/2026-03-28T23:59:59Z",
    "limit": 3
}
try:
    r = httpx.post("https://landsatlook.usgs.gov/stac-server/search", json=payload, timeout=30)
    print(f"  Status: {r.status_code}")
    if r.ok:
        d = r.json()
        print(f"  Features: {len(d.get('features',[]))}")
    else:
        print(f"  Error: {r.text[:300]}")
except Exception as e:
    print(f"  Exception: {e}")

# Test 2: Landsat with query extension (what our provider sends)
print("--- Landsat with query/sortby ---")
payload2 = {
    "collections": ["landsat-c2l2-sr"],
    "intersects": {"type": "Polygon", "coordinates": [[[31.2,30.0],[31.25,30.0],[31.25,30.05],[31.2,30.05],[31.2,30.0]]]},
    "datetime": "2026-02-27T00:00:00Z/2026-03-28T23:59:59Z",
    "limit": 3,
    "query": {"eo:cloud_cover": {"lte": 30}},
    "sortby": [{"field": "datetime", "direction": "desc"}]
}
try:
    r2 = httpx.post("https://landsatlook.usgs.gov/stac-server/search", json=payload2, timeout=30)
    print(f"  Status: {r2.status_code}")
    if r2.ok:
        d2 = r2.json()
        print(f"  Features: {len(d2.get('features',[]))}")
    else:
        print(f"  Error: {r2.text[:300]}")
except Exception as e:
    print(f"  Exception: {e}")
