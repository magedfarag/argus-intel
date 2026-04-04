# Change Detection — Technical Reference

## 1. Overview

The change detection pipeline compares two satellite scenes (before and after)
to identify construction activity within the AOI. It is implemented in
`backend/app/services/change_detection.py` and called by `AnalysisService`.

---

## 2. Pipeline steps

```
1. Scene pair selection
       rank_scenes()  →  select_scene_pair()
       before: highest-quality scene ≥ 7 days before 'after'
       after:  most recent, lowest cloud cover scene

2. COG streaming (rasterio)
       rasterio.open("https://…asset.tif")
       Reprojects AOI bbox → scene CRS
       Builds rasterio.Window for the AOI area
       Reads Red and NIR bands (clipped to window)

3. Cloud / QA masking
       Scene-specific QA band applied when available
       Pixels flagged as cloud / cloud shadow → NaN

4. NDVI computation
       NDVI = (NIR - Red) / (NIR + Red)
       Applied to both before and after scenes

5. Change map
       delta_NDVI = NDVI_after - NDVI_before
       |delta_NDVI| > 0.12  →  candidate change pixel

6. Morphological filtering (scipy.ndimage)
       Binary closing to fill gaps within patches
       Binary opening to remove isolated noise pixels

7. Connected components (scikit-image label)
       Each connected region = one candidate detection
       Regions < 4 pixels discarded

8. Classification + confidence scoring
       Area, mean delta_NDVI, shape compactness → class + score
       Resolution penalty applied for small AOIs at 30 m (Landsat)

9. Result packaging
       Each detection → ChangeRecord
       Warnings appended for low-confidence scenes or resolution limits
```

---

## 3. Band configuration

| Provider | Red band file | NIR band file |
|---|---|---|
| Sentinel-2 | `B04.tif` (10 m) | `B08.tif` (10 m) |
| Landsat-8/9 | `B4.TIF` (30 m) | `B5.TIF` (30 m) |

Bands are read from the `assets` dictionary of each STAC item.

---

## 4. Change classification

| Class | delta_NDVI signal | Typical construction stage |
|---|---|---|
| Site clearing | Large decrease (vegetation removal) | Earthwork / grading |
| Foundation work | Moderate stable decrease | Slab / foundation pour |
| Structure erection | Mixed signal | Framing / steel |
| Roofing / enclosure | High reflectance increase | Roof membranes / cladding |
| Paving / hardscape | Persistent low NDVI | Parking, roads |

---

## 5. Confidence scoring

```
base_confidence = 60 + (|mean_delta_NDVI| / 0.30) * 40
                       capped at 100

resolution_penalty:
  Sentinel-2 (10 m), AOI > 0.5 km²:   no penalty
  Sentinel-2 (10 m), AOI < 0.5 km²:   -5
  Landsat (30 m),    AOI > 5 km²:      no penalty
  Landsat (30 m),    AOI < 5 km²:      -15

final_confidence = max(0, base_confidence - resolution_penalty)
```

---

## 6. Graceful degradation

When `rasterio` is not importable (e.g. running tests without GDAL):

- `_rasterio_available()` returns `False`
- `run_change_detection()` returns an empty list
- `AnalysisService` appends a warning: `"rasterio not available — change detection skipped"`
- The `AnalyzeResponse` is still returned with `changes=[]` and `is_demo=False`

---

## 7. Performance characteristics

| AOI size | Provider | Typical latency |
|---|---|---|
| < 1 km² | Sentinel-2 | 3–8 s (streaming small window) |
| 1–25 km² | Sentinel-2 | 8–30 s |
| > 25 km² | Any | Auto-promoted to async job |
| Any | Demo | < 100 ms (no I/O) |

Large-area analyses (> `ASYNC_AREA_THRESHOLD_KM2`, default 25 km²) are
automatically promoted to async Celery tasks regardless of `async_execution` flag.

---

## 8. Known limitations

| # | Limitation |
|---|---|
| L1 | Atmospheric correction is assumed; no on-the-fly BRDF / DOS correction |
| L2 | Cloud masking relies on scene QA band — shadow detection is limited |
| L3 | No co-registration between scenes from different orbits |
| L4 | Landsat 30 m resolution misses fine detail on sites < 0.5 km² |
| L5 | Single NDVI threshold (0.12); seasonal baselines are not adjusted |
| L6 | No false-positive suppression for agricultural fields / seasonal vegetation |

---

## 9. Extending the pipeline

To add a new change indicator (e.g. SAR coherence, thermal anomaly):

1. Add a new function in `change_detection.py` following the same
   `_read_band_window()` + threshold + label pattern
2. Accept an additional `mode` parameter in `run_change_detection()`
3. Map the new `processing_mode="thorough"` to the extended pipeline
4. Add the new band keys to the `_BANDS` dictionary for each provider
