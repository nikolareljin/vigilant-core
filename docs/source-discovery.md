# Source Discovery & Regional Coverage

This document explains how VigilantCore discovers sources for outages, utilities, transportation disruptions, weather emergencies, and conflict/crisis scenarios.

## Overview

VigilantCore combines multiple strategies:

1. Curated source URLs (regional + global)
2. Localized Google News RSS feeds (region/language-aware)
3. RSS feed discovery from discovered/curated sites
4. Context-aware emergency search queries (DuckDuckGo / optional APIs)
5. Existing user-provided RSS feeds

The system is designed to work even when you only provide coordinates (`latitude` / `longitude`).

## Coordinate-First Region Inference

If `latitude` and `longitude` are provided, VigilantCore can infer a region without ZIP code or location text.

Current region profiles include:

- `us`
- `canada`
- `europe` (priority international baseline)
- `north_africa`
- `middle_east`
- `china`
- `far_east`
- `south_asia`
- `southeast_asia`
- `australia`
- `south_africa`
- `sub_saharan_africa`
- `central_america`
- `south_america`
- `global` (fallback)

The inference uses broad geographic bounding boxes and then applies region-specific:

- Google News RSS locale settings (`gl`, `hl`, `ceid`)
- Utility / transport / emergency query terms
- Curated source URL seeds

## What Gets Monitored (Examples)

### Utilities & Outages

- Electricity/power outages
- Utility outage maps (`poweroutage.us` search targeting for US)
- Water utility alerts / boil-water advisories
- Gas utility emergencies / pipeline incidents
- Solar / wind / battery-storage incidents (when relevant)

### Transportation & Operations

- Traffic incidents / road closures
- Transit and rail disruptions
- Airport operations alerts
- Airline cancellations / delays
- FAA ground stop signals (US)

### Extreme Weather & Disasters

- Flooding / flash floods
- Tornado / severe storm warnings
- Wildfire / evacuation alerts
- Winter storm / ice disruption
- Earthquakes / seismic events
- Hazmat / industrial incidents

### Conflict / Crisis (Subject-Driven)

If your subject includes terms like `war`, `conflict`, `missile`, `invasion`, etc., VigilantCore expands search/feed generation for:

- Conflict escalation
- Civilian evacuation alerts
- Humanitarian crisis updates
- International crisis/disaster sources (e.g., ReliefWeb, GDACS, UN OCHA)

## Curated Regional Source URL Catalogs

VigilantCore now includes curated regional source URLs for many regions (examples):

- Canada: Environment Canada, CBC, Hydro One, BC Hydro, Hydro-Québec
- Europe: Meteoalarm, Copernicus EMS, Eurocontrol, Network Rail
- North Africa: regional news and emergency-related sources
- China / Far East: weather, national media, and major regional outlets
- Australia: BOM, SES/VicEmergency, state traffic, utilities
- South Africa: Eskom, SAWS, SANRAL, national news
- Central & South America: emergency agencies, weather services, major local news
- Additional broader regions: Middle East, South Asia, Southeast Asia, Sub-Saharan Africa
- Global fallback: ReliefWeb, GDACS, UN OCHA, WHO Emergencies, IFRC, ICAO/EASA

## Setup Page Source Preview

The web setup page now includes a **Regional Source Preview** panel.

It shows:

- inferred region key/label
- curated source URL count
- sample curated source URLs that will be prioritized

This preview updates from:

- location name
- ZIP code
- latitude / longitude

and works **before** saving the configuration.

## API: `/api/source-preview`

Use this endpoint to inspect regional source selection programmatically.

### Example Request (coordinates only)

```bash
curl "http://127.0.0.1:8765/api/source-preview?latitude=48.8566&longitude=2.3522"
```

### Example Request (location text)

```bash
curl "http://127.0.0.1:8765/api/source-preview?location_name=Toronto,%20Ontario,%20Canada"
```

### Example Response (shape)

```json
{
  "region_key": "europe",
  "region_label": "Europe",
  "location_name": "",
  "zip_code": null,
  "latitude": 48.8566,
  "longitude": 2.3522,
  "source_count": 22,
  "urls": [
    "https://www.meteoalarm.org",
    "https://emergency.copernicus.eu"
  ]
}
```

## Operational Notes

- Discovery is best-effort: many sites do not expose stable RSS feeds.
- Curated URLs are used as feed-discovery seeds, not guaranteed direct RSS endpoints.
- Search/API sources complement RSS when feeds are unavailable.
- Region inference is intentionally approximate (fast, offline, and robust).

## Tuning Recommendations

- For local infrastructure monitoring, provide coordinates whenever possible.
- For international crisis monitoring, include a subject with context terms:
  - `war`, `conflict`, `flooding`, `airport delays`, `power outage`, etc.
- Use custom RSS feeds for any high-value local agencies/utilities you rely on regularly.
