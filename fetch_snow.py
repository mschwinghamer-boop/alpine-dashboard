#!/usr/bin/env python3
"""Collect hourly Open-Meteo estimates for nine North American ski touring zones.

Run with Python 3.11+; no third-party packages or API keys required.
The dashboard reads ./data.json. One daily snapshot per zone is kept in
./snow_history.csv; re-running on the same UTC day updates that day's row.
"""

from __future__ import annotations

import csv
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data.json"
HISTORY_FILE = ROOT / "snow_history.csv"
API = "https://api.open-meteo.com/v1/forecast"
HOURLY = (
    "snowfall", "snow_depth", "temperature_2m", "wind_speed_10m",
    "wind_direction_10m", "wind_gusts_10m",
)
HISTORY_COLUMNS = (
    "date_utc", "zone_id", "zone_name", "fetched_at_utc", "sample_time_utc",
    "snow_24h_cm", "snow_7d_cm", "snow_depth_cm", "temperature_c",
    "wind_speed_kmh", "wind_direction_deg", "wind_gust_kmh",
)

# forecast_kind='resource' signals that no location-specific operational
# avalanche bulletin exists at the linked destination.
ZONES = (
    dict(id="chic-chocs", name="Chic-Chocs", location="Gaspésie, Québec", region="East", lat=48.9436, lon=-66.1211,
         agency="Avalanche Québec", forecast_url="https://avalanchequebec.ca/bulletin-davalanche/", forecast_kind="bulletin",
         forecast_note="Check that the selected route is inside the bulletin's coverage area."),
    dict(id="laurentians", name="Laurentians", location="Montagne Noire · St-Donat, Québec", region="East", lat=46.3264, lon=-74.2625,
         agency="Avalanche Québec", forecast_url="https://avalanchequebec.ca/", forecast_kind="resource",
         forecast_note="No Avalanche Québec bulletin is published for St-Donat; this is a general safety resource."),
    dict(id="tuckerman", name="Tuckerman Ravine", location="Mount Washington, New Hampshire", region="East", lat=44.2611, lon=-71.2981,
         agency="Mount Washington Avalanche Center", forecast_url="https://www.mountwashingtonavalanchecenter.org/", forecast_kind="bulletin",
         forecast_note="Forecasts may be replaced by general avalanche information early or late in the season."),
    dict(id="adirondacks", name="Adirondacks", location="Mount Marcy, New York", region="East", lat=44.1127, lon=-73.9237,
         agency="New York DEC", forecast_url="https://dec.ny.gov/things-to-do/hiking/adirondack-backcountry/backcountry-information-for-adirondack-park", forecast_kind="resource",
         forecast_note="NY DEC backcountry conditions and alerts; not a location-specific avalanche danger bulletin."),
    dict(id="rogers-pass", name="Rogers Pass", location="Glacier National Park, British Columbia", region="West", lat=51.3003, lon=-117.5200,
         agency="Parks Canada / Avalanche Canada", forecast_url="https://avalanche.ca/en/forecasts", forecast_kind="bulletin",
         forecast_note="Select Glacier National Park; check the Parks Canada winter permit and access restrictions."),
    dict(id="loveland-pass", name="Loveland Pass", location="Front Range, Colorado", region="West", lat=39.6636, lon=-105.8792,
         agency="Colorado Avalanche Information Center", forecast_url="https://www.avalanche.state.co.us/forecasts", forecast_kind="bulletin",
         forecast_note="Select the applicable Front Range avalanche forecast zone."),
    dict(id="wasatch", name="Wasatch Backcountry", location="Alta · Brighton, Utah", region="West", lat=40.5885, lon=-111.6380,
         agency="Utah Avalanche Center", forecast_url="https://utahavalanchecenter.org/forecast/salt-lake", forecast_kind="bulletin",
         forecast_note="Salt Lake Area Mountains bulletin."),
    dict(id="tetons", name="Tetons", location="Teton Pass, Wyoming", region="West", lat=43.4975, lon=-110.9552,
         agency="Bridger-Teton Avalanche Center", forecast_url="https://bridgertetonavalanchecenter.org/", forecast_kind="bulletin",
         forecast_note="Select the Teton forecast area and consult current access alerts."),
    dict(id="mount-baker", name="Mount Baker", location="North Cascades, Washington", region="West", lat=48.8570, lon=-121.6695,
         agency="Northwest Avalanche Center", forecast_url="https://nwac.us/", forecast_kind="bulletin",
         forecast_note="Choose the West Slopes North / Mt. Baker forecast area."),
)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def numeric(value):
    """Return a real finite number, treating absent and invalid values as missing."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def rounded(value, digits=1):
    return round(value, digits) if value is not None else None


def load_forecast(zone):
    params = {
        "latitude": zone["lat"], "longitude": zone["lon"],
        "hourly": ",".join(HOURLY), "timezone": "UTC",
        "temperature_unit": "celsius", "wind_speed_unit": "kmh",
        "past_days": 8, "forecast_days": 1,
    }
    req = Request(
        API + "?" + urlencode(params),
        headers={"User-Agent": "AlpineDashboard/1.0 (personal noncommercial snow tracker)", "Accept": "application/json"},
    )
    for attempt in range(3):
        try:
            with urlopen(req, timeout=25) as response:
                payload = json.load(response)
            if payload.get("error"):
                raise ValueError(payload.get("reason", "Open-Meteo API error"))
            return payload
        except (HTTPError, URLError, TimeoutError) as exc:
            # Fail fast on non-retryable 4xx errors. Retry 429 and transient errors.
            if isinstance(exc, HTTPError) and 400 <= exc.code < 500 and exc.code != 429:
                raise
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Unreachable retry state")


def extract_zone(zone, payload, end_hour):
    """Aggregate seven complete, consecutive 24-hour windows in UTC.

    Open-Meteo hourly snowfall is the total during the PRECEDING hour.
    An hour marked 10:00 contributes snowfall from 09:00 through 10:00.
    The final window includes [end_hour-23h, ..., end_hour] exactly.
    Incomplete windows are null, never incorrectly presented as zero.
    """
    hourly = payload["hourly"]
    times = [datetime.fromisoformat(value).replace(tzinfo=timezone.utc) for value in hourly["time"]]
    lookup = {value: i for i, value in enumerate(times)}
    for field in HOURLY:
        if field not in hourly or len(hourly[field]) != len(times):
            raise ValueError(f"Missing or misaligned hourly field: {field}")

    daily = []
    for days_ago in range(6, -1, -1):
        bucket_end = end_hour - timedelta(days=days_ago)
        measurements = []
        for delta in range(23, -1, -1):
            moment = bucket_end - timedelta(hours=delta)
            i = lookup.get(moment)
            amount = numeric(hourly["snowfall"][i]) if i is not None else None
            measurements.append(amount if amount is None or amount >= 0 else None)
        total = sum(measurements) if all(value is not None for value in measurements) else None
        daily.append({"date": bucket_end.date().isoformat(), "snowfall_cm": rounded(total)})

    last_i = lookup.get(end_hour)
    if last_i is None:
        raise ValueError(f"No model data for last completed hour {iso_utc(end_hour)}")

    def instant(field):
        return numeric(hourly[field][last_i])

    depth_m = instant("snow_depth")
    compass = instant("wind_direction_10m")
    snow_7d = (
        rounded(sum(day["snowfall_cm"] for day in daily))
        if all(day["snowfall_cm"] is not None for day in daily) else None
    )
    return {
        **zone,
        "grid_elevation_m": rounded(numeric(payload.get("elevation")), 0),
        "sample_time_utc": iso_utc(end_hour),
        "snow_24h_cm": daily[-1]["snowfall_cm"],
        "snow_7d_cm": snow_7d,
        "snow_depth_cm": rounded(depth_m * 100 if depth_m is not None else None),
        "temperature_c": rounded(instant("temperature_2m")),
        "wind_speed_kmh": rounded(instant("wind_speed_10m")),
        "wind_direction_deg": rounded(compass % 360 if compass is not None else None, 0),
        "wind_gust_kmh": rounded(instant("wind_gusts_10m")),
        "snowfall_7d": daily,
        "error": None,
    }


def fallback_zone(zone, message):
    return {
        **zone,
        "grid_elevation_m": None, "sample_time_utc": None,
        "snow_24h_cm": None, "snow_7d_cm": None, "snow_depth_cm": None,
        "temperature_c": None, "wind_speed_kmh": None,
        "wind_direction_deg": None, "wind_gust_kmh": None,
        "snowfall_7d": [], "error": message,
    }


def save_history(zones, fetched_at):
    existing = {}
    if HISTORY_FILE.exists():
        with HISTORY_FILE.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("date_utc") and row.get("zone_id"):
                    existing[(row["date_utc"], row["zone_id"])] = row

    day = fetched_at.date().isoformat()
    for zone in zones:
        if zone["error"] is not None:
            continue
        existing[(day, zone["id"])] = {
            "date_utc": day, "zone_id": zone["id"], "zone_name": zone["name"],
            "fetched_at_utc": iso_utc(fetched_at), "sample_time_utc": zone["sample_time_utc"],
            **{field: zone[field] for field in HISTORY_COLUMNS if field in zone},
        }

    # Atomic replacement prevents a partially written history from being published.
    temporary = HISTORY_FILE.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for key in sorted(existing):
            writer.writerow(existing[key])
    temporary.replace(HISTORY_FILE)


def main():
    now = datetime.now(timezone.utc)
    end_hour = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    by_id = {}

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(load_forecast, zone): zone for zone in ZONES}
        for future in as_completed(futures):
            zone = futures[future]
            try:
                by_id[zone["id"]] = extract_zone(zone, future.result(), end_hour)
                print(f"OK   {zone['name']}")
            except (ValueError, KeyError, IndexError, TypeError, HTTPError, URLError, TimeoutError) as exc:
                print(f"FAIL {zone['name']}: {exc}", file=sys.stderr)
                by_id[zone["id"]] = fallback_zone(zone, str(exc))

    result = [by_id[zone["id"]] for zone in ZONES]
    successful = sum(zone["error"] is None for zone in result)
    if successful == 0:
        print("No zones succeeded; keeping the last good files and failing this run.", file=sys.stderr)
        return 1

    document = {
        "schema_version": 1,
        "generated_at": iso_utc(now),
        "reference_time_utc": iso_utc(end_hour),
        "source": "Open-Meteo Forecast API (modeled / interpolated data, not station observations)",
        "period_note": "Seven consecutive 24-hour periods, each ending at the same UTC hour; last period is the past 24 hours.",
        "zones": result,
        "errors": [{"zone": z["name"], "message": z["error"]} for z in result if z["error"]],
    }
    temporary = DATA_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(DATA_FILE)
    save_history(result, now)
    print(f"Saved {successful}/{len(ZONES)} zones to data.json and snow_history.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
