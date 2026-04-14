# External Data Sources Inventory

Last verified: 2026-04-13

This is the repo-level inventory of external data providers, feeds, and catalogs that ARGUS can currently talk to, plus the local stub connectors that look external in code but are not actually calling live third-party systems yet.

Primary code-backed inventory sources:

- `app/main.py` for runtime-registered providers/connectors
- `app/workers/tasks.py` for worker-only pollers
- `.env.example` and `app/config.py` for configuration and auth expectations
- `app/providers/` and `src/connectors/` for integration contracts

Important caveats:

- Pricing pages move often. Where a vendor exposes only contact-sales or JS-rendered pricing, this document records that instead of guessing.
- Some repo comments are now older than the current vendor docs. Those mismatches are called out explicitly.
- "Registration URL" means the best current entrypoint we could verify for account creation, trial signup, or contact-sales onboarding.

## Summary

| Domain | Count | Notes |
|---|---:|---|
| Live/runtime imagery endpoints | 6 | 4 STAC-style external catalogs plus 2 optional commercial providers |
| Live/runtime telemetry feeds | 2 | AIS and aviation |
| Live/runtime context/public/environmental feeds | 9 | News, conflict, weather, hazards, public records |
| Worker-only external feeds | 2 | Both are RapidAPI-based vessel feeds |
| Local-only stubs excluded from "external" totals | 5 | Demo, FAA/NOTAM stub, CelesTrak stub, strike stub, jamming stub |

## Imagery Sources

| Source | Repo status | Repo IDs / code | Data types | Registration / homepage | Fees / access | Auth | Notes |
|---|---|---|---|---|---|---|---|
| Copernicus Data Space Ecosystem (CDSE) | Live when `SENTINEL2_CLIENT_ID` and `SENTINEL2_CLIENT_SECRET` are set | V1 `sentinel2` provider in `app/providers/sentinel2.py`; V2 `cdse-sentinel2` connector in `src/connectors/sentinel2.py` | Sentinel-2 L2A optical multispectral imagery, STAC catalog search, COG asset access | Homepage: <https://dataspace.copernicus.eu/> | Free and open access according to CDSE homepage; account registration required for richer use and OAuth client creation | OAuth2 client credentials | Repo docs say 10 m resolution and about 5-day revisit. This is the only Sentinel source in the repo that requires first-party Copernicus credentials. |
| Earth Search (Element 84) | Always registered at app startup | `earth-search` in `src/connectors/earth_search.py` | Public STAC catalog for open AWS geospatial datasets including Sentinel-2 and Landsat Collection 2 | Homepage: <https://element84.com/earth-search> API root: <https://earth-search.aws.element84.com/v1> | Free-to-use public STAC API; Element 84 explicitly notes no guaranteed service for the public endpoint | None | Best fit when we want open cloud-native COG access without Copernicus auth. Repo comments and Element 84 docs align closely here. |
| Microsoft Planetary Computer | Always registered at app startup | `planetary-computer` in `src/connectors/planetary_computer.py` | Public STAC metadata catalog for Earth science datasets; in this repo it is used as an imagery catalog connector | Homepage: <https://planetarycomputer.microsoft.com/> STAC root: <https://planetarycomputer.microsoft.com/api/stac/v1> | Public STAC catalog is reachable without auth; no stable public pricing page was found for dedicated/commercial capacity. Repo supports optional token-based higher-limit access via `PLANETARY_COMPUTER_TOKEN`. | None by default; optional subscription key | Useful as a second open imagery/catalog path. Treat commercial/support terms as separate from the public catalog endpoint. |
| USGS LandsatLook / Landsat Collection 2 | Always available in repo; V1 and V2 are always considered configurable for search | V1 `landsat` provider in `app/providers/landsat.py`; V2 `usgs-landsat` connector in `src/connectors/landsat.py` | Landsat Collection 2 Level-2 optical multispectral imagery via STAC | Data access overview: <https://www.usgs.gov/landsat-missions/landsat-data-access> ERS / account entrypoint: <https://ers.cr.usgs.gov/> | USGS says Landsat products can be searched/downloaded at no charge; ERS account may still be needed for some USGS archive tools and workflows | None for STAC search; optional USGS account for ERS/M2M-style access | Repo docs say 30 m resolution and about 16-day revisit. Good large-area fallback when Sentinel is unavailable. |
| Vantor / former Maxar SecureWatch / MGP Pro | Optional commercial provider; only registered when `MAXAR_API_KEY` is set | `app/providers/maxar.py` | Commercial high-resolution optical imagery | Product lineage: repo still says SecureWatch; current official contact and company pages are at <https://vantor.com/> and <https://vantor.com/contact-us> | Quote-based / contact sales; no current public self-serve price sheet located | API key / subscription | Important mismatch: repo naming is stale. Official 2025-2026 branding is Vantor, and older "SecureWatch" pages now redirect. Treat endpoint, product name, and licensing as re-validation items before production use. |
| Planet Insights Platform / PlanetScope / SkySat | Optional commercial provider; only registered when `PLANET_API_KEY` is set | `app/providers/planet.py` | Commercial near-daily PlanetScope imagery, SkySat tasking/archive, subscriptions, public-data processing via Planet platform | Trial signup: <https://insights.planet.com/sign-up/> Homepage: <https://www.planet.com/> | Official Planet support shows: 30-day free trial for Planet Insights Platform; annual AUM pricing depends on country/tier; support pages list self-serve SkySat pricing at $6/km2 archive, $12/km2 flexible tasking, and $40/km2 assured tasking | API key / account | Planet now has both enterprise/contact-sales motion and self-serve purchasing for some products. Public imagery processed inside Planet still consumes Planet processing units even when the underlying data are free. |

## Telemetry Sources

| Source | Repo status | Repo IDs / code | Data types | Registration / homepage | Fees / access | Auth | Notes |
|---|---|---|---|---|---|---|---|
| AISStream.io | Live when `AISSTREAM_API_KEY` is set; registered in app startup and polled by workers | `ais-stream` in `src/connectors/ais_stream.py` | AIS vessel positions, vessel/voyage metadata, maritime incidents/danger reports, SAR aircraft positions, ship-to-ship AIS messages | Homepage: <https://aisstream.io/> Signup/auth: <https://aisstream.io/authenticate> Docs: <https://aisstream.io/documentation.html> | Official homepage markets the websocket feed as real-time and free. No public paid tiers were surfaced during verification. | API key over WebSocket | Strong repo/official alignment: their docs explicitly recommend backend-only consumption so API keys are not exposed in browsers, which matches our server-side relay design. |
| OpenSky Network | Always registered in app startup; also polled by workers | `opensky` in `src/connectors/opensky.py` | Aircraft state vectors and related aviation telemetry from ADS-B, Mode-S, ADS-C, FLARM, and VHF sources | Homepage: <https://opensky-network.org/> Data page: <https://opensky-network.org/data/> | Public API is usable for personal and non-profit use; full historical dataset is free for eligible research/government/aviation users; commercial entities must contact OpenSky for a license | Optional username/password in repo; public API also exists without commercial rights | This feed is legally sensitive. OpenSky terms are explicitly non-commercial/research-first unless licensed otherwise. If we productize aviation features commercially, this source needs legal review. |

## Context, Public Record, and Environmental Sources

| Source | Repo status | Repo IDs / code | Data types | Registration / homepage | Fees / access | Auth | Notes |
|---|---|---|---|---|---|---|---|
| GDELT 2.0 | Always registered at app startup and polled by workers | `gdelt-doc` in `src/connectors/gdelt.py` | Global news-derived event/context feed: locations, themes, tone, people, organizations, images, quotes | Homepage: <https://www.gdeltproject.org/> API base used by repo: <https://api.gdeltproject.org/api/v2> | Free and open; GDELT describes the entire database as 100% free and open | None | High-value context layer for correlating construction, conflict, or incident reporting around AOIs. Updates every 15 minutes per GDELT site. |
| ACLED | Live only when ACLED credentials are configured | `acled` in `src/connectors/acled.py` | Conflict, protest, political violence, and crisis event records | Homepage: <https://acleddata.com/> Registration: <https://acleddata.com/user/register> Access info: <https://acleddata.com/myacled-faqs> | Free public access exists but is category-limited; corporate/commercial users need a corporate license; API/data access limits vary by user class | Repo expects account credentials; public docs show access is now managed via myACLED and current credentials-based auth flows | Important mismatch area. Repo comments still describe email/password OAuth2. Current ACLED public docs show an evolving access model and stronger usage restrictions, including competitive/AI-use limits. Re-verify before relying on this connector in production. |
| USGS Earthquake Catalog / FDSN Event API | Always registered and polled by workers | `usgs-earthquake` in `src/connectors/usgs_earthquake.py` | Earthquake event records, magnitude, depth, location, update metadata | Homepage: <https://www.usgs.gov/programs/earthquake-hazards> API docs: <https://earthquake.usgs.gov/fdsnws/event/1> | Free/public US government data | None | Straightforward public-record feed. Good reliability profile and clear API documentation. |
| NASA EONET | Always registered and polled by workers | `nasa-eonet` in `src/connectors/nasa_eonet.py` | Curated natural-event metadata linked to related imagery sources | Homepage/API: <https://eonet.gsfc.nasa.gov/> | Free/open NASA API | None | Good contextual hazard layer for storms, fires, volcanoes, dust events, etc. |
| Open-Meteo | Always registered and polled by workers | `open-meteo` in `src/connectors/open_meteo.py` | Weather forecast context; Open-Meteo also exposes marine, air-quality, flood, and climate APIs | Homepage: <https://open-meteo.com/> Pricing: <https://open-meteo.com/en/pricing> | Free non-commercial tier with no API key; commercial customer API plans exist. Published free-tier limits include 600/min, 5,000/hour, 10,000/day, and 300,000/month. | None for free tier; API key for customer/commercial API | Repo currently uses only forecast context, but the provider also offers adjacent APIs that could support future layers. |
| NGA Maritime Safety Information | Always registered and polled by workers | `nga-msi` in `src/connectors/nga_msi.py` | Maritime safety / broadcast warning records, NAVAREA notices | Homepage: <https://msi.nga.mil/> | Free/public US government data | None | Strong fit for Gulf and chokepoint monitoring because the repo already defaults to NAVAREA IX and III. |
| OpenStreetMap via Overpass API | Always registered and polled by workers | `osm-military` in `src/connectors/osm_military.py` | OSM military features and facilities pulled through Overpass queries | Homepage: <https://overpass-api.de/> Usage guidance: <https://wiki.openstreetmap.org/Overpass_API> | Free public service; shared infrastructure, not a guaranteed managed service | None for the query pattern we use | Important operational note: public guidance says under 10,000 queries/day and under 1 GB/day is generally safe on the main instance. Heavy production usage should self-host. ODbL attribution/share-alike obligations apply. |
| NASA FIRMS | Always registered and polled by workers | `nasa-firms` in `src/connectors/nasa_firms.py` | Fire and thermal anomaly detections from VIIRS/MODIS products | API overview: <https://firms.modaps.eosdis.nasa.gov/api/> MAP_KEY page: <https://firms.modaps.eosdis.nasa.gov/api/map_key/> | Free MAP_KEY by email signup; `DEMO_KEY` is usable for testing at lower limits | MAP_KEY | Official limits page shows 5,000 transactions per 10-minute interval for MAP_KEY users. Good environmental alert source for industrial incidents and wildfire context. |
| NOAA Space Weather Prediction Center | Always registered and polled by workers | `noaa-swpc` in `src/connectors/noaa_swpc.py` | Space weather alerts, warnings, watches, forecasts, and product feeds | Homepage: <https://www.swpc.noaa.gov/> Data root used by repo: <https://services.swpc.noaa.gov/> Email subscription service: <https://www.swpc.noaa.gov/content/subscription-services> | Free public HTTP products; optional registration only if you want email subscriptions | None for HTTP feeds | Valuable if we later correlate GNSS degradation, comms impacts, or satellite drag risk with other layers. |
| OpenAQ | Always registered and polled by workers | `openaq` in `src/connectors/openaq.py` | Air quality station/location/measurement data | Homepage: <https://openaq.org/> Docs: <https://docs.openaq.org/> Signup: <https://explore.openaq.org/register> | General-use API access is free; official docs publish 60/min and 2,000/hour rate limits; custom higher-limit pricing is available on request | API key required per current hosted API docs | Important mismatch: repo comments say the API key is optional, but current official OpenAQ docs say the hosted API requires an API key even for normal use. This connector should be updated to match current platform reality. |

## Worker-Only Marketplace Sources

These do not register in `app/main.py`, but they are present in `app/workers/tasks.py` and can populate the event/telemetry stores when their API keys are configured.

| Source | Repo status | Repo IDs / code | Data types | Registration / homepage | Fees / access | Auth | Notes |
|---|---|---|---|---|---|---|---|
| RapidAPI AIS (generic bbox endpoint) | Worker-only, used by `poll_rapidapi_ais` when `RAPID_API_KEY` is set | `rapidapi-ais` in `src/connectors/rapidapi_ais.py` | AIS vessel positions from a third-party RapidAPI marketplace endpoint | RapidAPI Hub: <https://rapidapi.com/hub> | Pricing is marketplace-provider-defined, not fixed by our repo. RapidAPI supports monthly subscription, pay-per-use, and tiered plans depending on the listing. | RapidAPI key plus host header | This is a marketplace wrapper, not a first-party data owner integration. Use only if AISStream is unavailable or a commercial RapidAPI source is explicitly preferred. |
| Vessel Data (RapidAPI) | Worker-only, used by `poll_vessel_data` when `VESSEL_DATA_API_KEY` is set | `vessel-data` in `src/connectors/vessel_data.py` | Vessel positions and related vessel data via `vessel-data.p.rapidapi.com` | Listing: <https://rapidapi.com/ai-box-ai-box-default/api/vessel-data> | Pricing varies by listing plan on RapidAPI; no stable public flat fee could be extracted from the static listing view during verification | RapidAPI key | Similar caution as generic RapidAPI AIS: this is marketplace-dependent and operational terms can change outside our control. |

## Operational Layer Live Connectors (Wave 1)

These connectors were added in Wave 1 of the Free/Open-Source API implementation plan. They replace the previously stub-only paths for orbit, airspace, and strike data.

| Source | Connector ID | Repo code | Config keys | Registration | Fallback if unconfigured |
|---|---|---|---|---|---|
| CelesTrak GP (active satellites) | `celestrak-gp-live` | `src/connectors/celestrak_connector.py` | `CELESTRAK_FETCH_TIMEOUT_SEC` (default 30) | Open data, no registration required: <https://celestrak.org/> | Falls back to seeded TLE stub in `OrbitLayerService` |
| FAA NOTAM Search API | `faa-notam-live` | `src/connectors/faa_notam_connector.py` | `FAA_NOTAM_CLIENT_ID` (required) | Free key at <https://api.faa.gov/> | `ConnectorError` raised at startup if `FAA_NOTAM_CLIENT_ID` is absent; `AirspaceLayerService` falls back to stub |
| ACLED Strike Layer | `acled-strike-live` | `src/connectors/acled_strike_connector.py` | `ACLED_EMAIL`, `ACLED_PASSWORD` | Free via myACLED: <https://acleddata.com/user/register> — non-commercial only; AI/ML use requires written agreement | `StrikeLayerService` falls back to stub when credentials are absent |

## Local Stubs And Non-External Sources

These appear in code, but they are not current live external data sources:

| Source | Repo IDs / code | Why excluded from external inventory |
|---|---|---|
| Demo imagery provider | `app/providers/demo.py` | Synthetic deterministic construction scenarios only |
| FAA NOTAM / airspace stub | `src/connectors/airspace_connector.py` (`faa-notam-stub`) | Fallback/demo path; superseded by `faa-notam-live` connector when `FAA_NOTAM_CLIENT_ID` is set |
| CelesTrak TLE stub | `src/connectors/orbit_connector.py` (`celestrak-tle-stub`) | Fallback/demo path; superseded by `celestrak-gp-live` connector |
| GNSS jamming monitor stub | `src/connectors/jamming_connector.py` | Permanently demo-only (JAM-01 decision — no approved live GNSS jamming source) |
| Strike reconstruction stub | `src/connectors/strike_connector.py` | Fallback/demo path; superseded by `acled-strike-live` connector when ACLED credentials are set |

## Most Important Mismatches To Fix

| Area | What changed | Why it matters |
|---|---|---|
| Maxar branding | Repo says Maxar/SecureWatch, official branding has moved to Vantor and older SecureWatch pages redirect | Sales process, legal docs, and possibly API/program naming are stale in repo documentation |
| OpenAQ auth | Repo comments say API key optional, official docs now require API keys for hosted API access | Connector docs/config guidance are inaccurate for current onboarding |
| ACLED access model | Repo assumes legacy-style credentials flow; current public docs emphasize myACLED account model and stricter terms | Access and license assumptions should be revalidated before rollout |
| Overpass capacity | Public Overpass is shared best-effort infra, not a commercial SLA source | Heavy automated production usage can be throttled or blocked |
| Planet pricing model | Planet now mixes self-serve plans, processing-unit pricing, and classic enterprise sales | Any budget estimate must distinguish public-data processing from licensed commercial imagery |

## Source Links Used For Verification

### Repo / local sources

- `app/main.py`
- `app/workers/tasks.py`
- `app/config.py`
- `.env.example`
- `docs/PROVIDERS.md`
- `docs/reference/environment.md`

### External sources

- CDSE: <https://dataspace.copernicus.eu/>
- Earth Search: <https://element84.com/earth-search>
- Earth Search public STAC: <https://earth-search.aws.element84.com/v1>
- Planetary Computer public STAC: <https://planetarycomputer.microsoft.com/api/stac/v1>
- USGS Landsat data access: <https://www.usgs.gov/landsat-missions/landsat-data-access>
- USGS Landsat FAQ: <https://www.usgs.gov/faqs/how-do-i-search-for-and-download-landsat-data>
- Vantor homepage: <https://vantor.com/>
- Vantor contact: <https://vantor.com/contact-us>
- Planet trial signup: <https://insights.planet.com/sign-up/>
- Planet self-serve pricing overview blog: <https://www.planet.com/pulse/planet-enables-self-service-purchasing-for-small-customers-on-planet-insights-platform/>
- Planet support pricing references surfaced in search:
  <https://support.planet.com/hc/en-us/articles/27016165868957-What-s-the-Difference-Between-Monitoring-and-Tasking-Subscriptions>
  <https://support.planet.com/hc/en-us/articles/18675352704029-How-Does-Planetscope-Areas-Under-Management-Work>
- AISStream homepage: <https://aisstream.io/>
- AISStream docs: <https://aisstream.io/documentation.html>
- OpenSky homepage: <https://opensky-network.org/>
- OpenSky data access pages:
  <https://opensky-network.org/data/>
  <https://opensky-network.org/data/trino>
  <https://opensky-network.org/about/faq>
  <https://opensky-network.org/about/terms-of-use?tmpl=component>
- GDELT: <https://www.gdeltproject.org/>
- ACLED pages:
  <https://acleddata.com/myacled-faqs>
  <https://acleddata.com/eula>
  <https://acleddata.com/knowledge-base/how-can-i-access-and-use-acled-data/>
- USGS Earthquake Hazards Program: <https://www.usgs.gov/programs/earthquake-hazards>
- USGS Earthquake API docs: <https://earthquake.usgs.gov/fdsnws/event/1>
- NASA EONET: <https://eonet.gsfc.nasa.gov/>
- Open-Meteo homepage: <https://open-meteo.com/>
- Open-Meteo pricing: <https://open-meteo.com/en/pricing>
- NGA MSI: <https://msi.nga.mil/>
- Overpass API homepage: <https://overpass-api.de/>
- Overpass API usage guidance: <https://wiki.openstreetmap.org/Overpass_API>
- NASA FIRMS API: <https://firms.modaps.eosdis.nasa.gov/api/>
- NASA FIRMS MAP_KEY page: <https://firms.modaps.eosdis.nasa.gov/api/map_key/>
- NOAA SWPC homepage: <https://www.swpc.noaa.gov/>
- NOAA SWPC data root: <https://services.swpc.noaa.gov/>
- NOAA SWPC subscription services: <https://www.swpc.noaa.gov/content/subscription-services>
- OpenAQ docs:
  <https://docs.openaq.org/>
  <https://docs.openaq.org/using-the-api/api-key>
  <https://docs.openaq.org/using-the-api/rate-limits>
  <https://docs.openaq.org/about/terms>
- RapidAPI marketplace:
  <https://rapidapi.com/hub>
  <https://rapidapi.com/ai-box-ai-box-default/api/vessel-data>
