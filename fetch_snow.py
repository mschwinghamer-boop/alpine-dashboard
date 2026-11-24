#!/usr/bin/env python3
"""Collect hourly Open-Meteo estimates for 100 North American ski touring zones.

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
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
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
    "snow_14d_cm", "forecast_start_utc", "sample_kind", "sample_lat", "sample_lon", "grid_elevation_m", "country", "region", "province_state",
)

# forecast_kind='resource' signals that no location-specific operational
# avalanche bulletin exists at the linked destination.
ZONES = (
    {'id': 'ca-01', 'name': 'Rogers Pass (Glacier National Park)', 'country': 'Canada', 'region': 'Selkirks & Glacier NP', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 51.252, 'lon': -117.509, 'upper_reference': 'Mount Abbott upper mountain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-02', 'name': 'Asulkan Cabin', 'country': 'Canada', 'region': 'Selkirks & Glacier NP', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 51.229, 'lon': -117.483, 'upper_reference': 'Asulkan basin alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-03', 'name': 'A.O. Wheeler Hut', 'country': 'Canada', 'region': 'Selkirks & Glacier NP', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 51.263, 'lon': -117.489, 'upper_reference': 'Illecillewaet / Avalanche Mountain upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-04', 'name': 'Revelstoke Backcountry (MacPherson & Frisby Ridge)', 'country': 'Canada', 'region': 'Monashees', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 51.067, 'lon': -118.295, 'upper_reference': 'Frisby Ridge upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-05', 'name': 'Kootenay Pass', 'country': 'Canada', 'region': 'Southern Selkirks & Valhallas', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 49.067, 'lon': -117.037, 'upper_reference': 'Cornice Ridge upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-06', 'name': 'Whitewater Backcountry (Ymir Peak & Five Mile)', 'country': 'Canada', 'region': 'Southern Selkirks & Valhallas', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 49.447, 'lon': -117.139, 'upper_reference': 'Ymir upper alpine', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-07', 'name': 'Red Mountain Backcountry (Mount Roberts & Granite)', 'country': 'Canada', 'region': 'Southern Selkirks & Valhallas', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 49.105, 'lon': -117.846, 'upper_reference': 'Granite Mountain upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-08', 'name': 'Sorcerer Lodge', 'country': 'Canada', 'region': 'Selkirks & Glacier NP', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 51.44809, 'lon': -117.70228, 'upper_reference': 'Sorcerer Lodge vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Published lodge vicinity', 'coordinate_source': 'https://mapcarta.com/W754352050'},
    {'id': 'ca-09', 'name': 'Battle Abbey Backcountry Lodge', 'country': 'Canada', 'region': 'Selkirks & Glacier NP', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 50.98006, 'lon': -117.34301, 'upper_reference': 'Battle Abbey lodge vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Published lodge vicinity', 'coordinate_source': 'https://mapcarta.com/W967086429'},
    {'id': 'ca-10', 'name': 'Fairy Meadows (Bill Putnam Hut)', 'country': 'Canada', 'region': 'Selkirks & Glacier NP', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 51.758, 'lon': -117.8727, 'upper_reference': 'Fairy Meadow hut vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Published lodge vicinity', 'coordinate_source': 'https://latitude.to/articles-by-country/ca/canada/90670/bill-putnam-hut'},
    {'id': 'ca-11', 'name': 'Golden Alpine Holidays (Sentry, Meadow, Vista & Sunrise Lodges)', 'country': 'Canada', 'region': 'Selkirks & Glacier NP', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 51.51, 'lon': -117.39, 'upper_reference': 'Northern Selkirks lodge terrain (regional proxy)', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-12', 'name': 'Purcell Mountain Lodge', 'country': 'Canada', 'region': 'Purcells', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 51.22, 'lon': -117.06, 'upper_reference': 'Bald Mountain alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-13', 'name': 'Selkirk Lodge', 'country': 'Canada', 'region': 'Selkirks & Glacier NP', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 51.02, 'lon': -117.96, 'upper_reference': 'Albert Icefield alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-14', 'name': 'Valhalla Mountain Touring', 'country': 'Canada', 'region': 'Southern Selkirks & Valhallas', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 49.7833, 'lon': -117.7333, 'upper_reference': 'Valhalla lodge vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Published lodge vicinity', 'coordinate_source': 'https://hutatlas.com/hut/valhalla-mountain-lodge'},
    {'id': 'ca-15', 'name': 'Mount Carlyle Lodge', 'country': 'Canada', 'region': 'Southern Selkirks & Valhallas', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 50.0, 'lon': -117.16, 'upper_reference': 'Mount Carlyle alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-16', 'name': 'Ice Creek Lodge', 'country': 'Canada', 'region': 'Southern Selkirks & Valhallas', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 49.91, 'lon': -117.87, 'upper_reference': 'Northwest Valhalla alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-17', 'name': 'Sol Mountain Touring', 'country': 'Canada', 'region': 'Monashees', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 50.4833, 'lon': -118.15, 'upper_reference': 'Sol Mountain lodge vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Published lodge vicinity', 'coordinate_source': 'https://hutatlas.com/hut/sol-mountain-lodge'},
    {'id': 'ca-18', 'name': 'Blanket Glacier Chalet', 'country': 'Canada', 'region': 'Monashees', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 50.79813, 'lon': -118.24797, 'upper_reference': 'Blanket Glacier Chalet vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Published lodge vicinity', 'coordinate_source': 'https://mapcarta.com/W1134668261'},
    {'id': 'ca-19', 'name': 'Campbell Icefield Chalet', 'country': 'Canada', 'region': 'Canadian Rockies', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 51.95, 'lon': -116.91, 'upper_reference': 'Campbell Icefield alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-20', 'name': 'Boulder Hut Adventures', 'country': 'Canada', 'region': 'Purcells', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 49.7167, 'lon': -115.7833, 'upper_reference': 'Boulder Hut vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Published lodge vicinity', 'coordinate_source': 'https://hutatlas.com/hut/boulder-hut-adventures'},
    {'id': 'ca-21', 'name': 'Wapta Traverse (Peyto, Bow, Balfour & Scott Duncan Huts)', 'country': 'Canada', 'region': 'Canadian Rockies', 'province_state': 'AB/BC', 'location': 'AB/BC, Canada', 'lat': 51.63, 'lon': -116.51, 'upper_reference': 'Wapta Icefield representative alpine point', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-22', 'name': 'Bow Summit & Peyto Glacier', 'country': 'Canada', 'region': 'Canadian Rockies', 'province_state': 'AB', 'location': 'AB, Canada', 'lat': 51.714, 'lon': -116.463, 'upper_reference': 'Observation Peak upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-23', 'name': 'Parker Ridge & Hilda Glacier', 'country': 'Canada', 'region': 'Canadian Rockies', 'province_state': 'AB', 'location': 'AB, Canada', 'lat': 52.18, 'lon': -117.12, 'upper_reference': 'Parker Ridge alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-24', 'name': 'Crowfoot Glades & Helen Shoulder', 'country': 'Canada', 'region': 'Canadian Rockies', 'province_state': 'AB', 'location': 'AB, Canada', 'lat': 51.65, 'lon': -116.39, 'upper_reference': 'Helen Shoulder alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-25', 'name': 'Lake Louise Backcountry (Pipestone & Skoki Valley)', 'country': 'Canada', 'region': 'Canadian Rockies', 'province_state': 'AB', 'location': 'AB, Canada', 'lat': 51.493, 'lon': -116.164, 'upper_reference': 'Mount Richardson upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-26', 'name': 'Skoki Lodge', 'country': 'Canada', 'region': 'Canadian Rockies', 'province_state': 'AB', 'location': 'AB, Canada', 'lat': 51.527, 'lon': -116.082, 'upper_reference': 'Skoki alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-27', 'name': 'Sunshine Village Sidecountry (Healy Pass & Quartz Ridge)', 'country': 'Canada', 'region': 'Canadian Rockies', 'province_state': 'AB', 'location': 'AB, Canada', 'lat': 51.1, 'lon': -115.85, 'upper_reference': 'Healy Pass alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-28', 'name': 'Mount Assiniboine Lodge & Naiset Huts', 'country': 'Canada', 'region': 'Canadian Rockies', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 50.91, 'lon': -115.63, 'upper_reference': 'Assiniboine lodge alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-29', 'name': 'Kananaskis Country (Highwood Pass & Burstall Pass)', 'country': 'Canada', 'region': 'Canadian Rockies', 'province_state': 'AB', 'location': 'AB, Canada', 'lat': 50.602, 'lon': -114.986, 'upper_reference': 'Mount Rae upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-30', 'name': 'Stanley Mitchell Hut (Little Yoho Valley)', 'country': 'Canada', 'region': 'Canadian Rockies', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 51.526, 'lon': -116.562, 'upper_reference': 'Little Yoho alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-31', 'name': 'Emerald Lake & President Range', 'country': 'Canada', 'region': 'Canadian Rockies', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 51.49, 'lon': -116.56, 'upper_reference': 'President Range alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-32', 'name': 'Mistaya Lodge', 'country': 'Canada', 'region': 'Canadian Rockies', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 51.78, 'lon': -116.77, 'upper_reference': 'Wildcat basin alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-33', 'name': 'Icefall Lodge', 'country': 'Canada', 'region': 'Canadian Rockies', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 51.87347, 'lon': -117.13077, 'upper_reference': 'Icefall Lodge vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Published lodge vicinity', 'coordinate_source': 'https://mapcarta.com/N6370657041'},
    {'id': 'ca-34', 'name': 'Amiskwi Lodge', 'country': 'Canada', 'region': 'Canadian Rockies', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 51.617989, 'lon': -116.670567, 'upper_reference': 'Amiskwi lodge vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Published lodge vicinity', 'coordinate_source': 'https://www.amiskwi.com/location'},
    {'id': 'ca-35', 'name': 'Talus Lodge', 'country': 'Canada', 'region': 'Canadian Rockies', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 50.72236, 'lon': -115.49147, 'upper_reference': 'Talus lodge vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Published lodge vicinity', 'coordinate_source': 'https://mapcarta.com/fr/W554551091'},
    {'id': 'ca-36', 'name': 'Jasper National Park (Marmot Pass & Tonquin Valley)', 'country': 'Canada', 'region': 'Canadian Rockies', 'province_state': 'AB', 'location': 'AB, Canada', 'lat': 52.79, 'lon': -118.14, 'upper_reference': 'Marmot Basin upper mountain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-37', 'name': 'Duffey Lake Road (Joffre Lakes, Cayoosh & Marriott Basin)', 'country': 'Canada', 'region': 'South Coast & Duffey', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 50.389, 'lon': -122.448, 'upper_reference': 'Cayoosh upper alpine', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-38', 'name': 'Whistler Blackcomb Backcountry (Spearhead Traverse)', 'country': 'Canada', 'region': 'South Coast & Duffey', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 50.087, 'lon': -122.841, 'upper_reference': 'Spearhead Range alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-39', 'name': 'Kees and Claire Hut (Russet Lake)', 'country': 'Canada', 'region': 'South Coast & Duffey', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 50.037, 'lon': -122.861, 'upper_reference': 'Russet Lake alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-40', 'name': 'Garibaldi Provincial Park (Elfin Lakes & Paul Ridge)', 'country': 'Canada', 'region': 'South Coast & Duffey', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 49.75, 'lon': -123.02, 'upper_reference': 'Paul Ridge upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-41', 'name': 'Pemberton Icecap', 'country': 'Canada', 'region': 'South Coast & Duffey', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 50.39, 'lon': -123.16, 'upper_reference': 'Pemberton Icecap alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-42', 'name': 'Callaghan Country & Journeyman Lodge', 'country': 'Canada', 'region': 'South Coast & Duffey', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 50.21, 'lon': -123.21, 'upper_reference': 'Callaghan alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-43', 'name': 'Whitecap Alpine (McGillivray Pass)', 'country': 'Canada', 'region': 'South Coast & Duffey', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 50.72, 'lon': -122.9, 'upper_reference': 'McGillivray Pass lodge vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Published lodge vicinity', 'coordinate_source': 'https://hutatlas.com/hut/mcgillivray-pass-lodge-whitecap-alpine'},
    {'id': 'ca-44', 'name': 'Chilcotin Mountains (Taseko & Tyaughton Lake)', 'country': 'Canada', 'region': 'Chilcotin', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 51.02, 'lon': -122.97, 'upper_reference': 'South Chilcotin alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-45', 'name': 'Coquihalla Summit (Zopkios & Needle Peak)', 'country': 'Canada', 'region': 'South Coast & Duffey', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 49.58, 'lon': -121.13, 'upper_reference': 'Needle Peak upper alpine', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-46', 'name': 'Shames Mountain Backcountry (Terrace)', 'country': 'Canada', 'region': 'Northern BC', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 54.48, 'lon': -128.98, 'upper_reference': 'Shames upper mountain vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-47', 'name': 'Hankin-Evelyn Backcountry Recreation Area (Smithers)', 'country': 'Canada', 'region': 'Northern BC', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 54.98, 'lon': -127.44, 'upper_reference': 'Hankin alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-48', 'name': 'Burnie Glacier Chalet (Howson Range)', 'country': 'Canada', 'region': 'Northern BC', 'province_state': 'BC', 'location': 'BC, Canada', 'lat': 54.16, 'lon': -127.72, 'upper_reference': 'Howson Range alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-49', 'name': 'White Pass (Skagway/Fraser)', 'country': 'Canada', 'region': 'Northern BC & Yukon passes', 'province_state': 'BC/YT', 'location': 'BC/YT, Canada', 'lat': 59.63, 'lon': -135.15, 'upper_reference': 'White Pass upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'ca-50', 'name': 'Haines Pass (Tatshenshini-Alsek)', 'country': 'Canada', 'region': 'Northern BC & Yukon passes', 'province_state': 'BC/YT', 'location': 'BC/YT, Canada', 'lat': 59.77, 'lon': -136.6, 'upper_reference': 'Haines Pass upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche Canada', 'forecast_url': 'https://avalanche.ca/en/forecasts', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-01', 'name': 'Wasatch Range (Little & Big Cottonwood Canyons)', 'country': 'USA', 'region': 'Utah', 'province_state': 'UT', 'location': 'UT, USA', 'lat': 40.57, 'lon': -111.65, 'upper_reference': 'Mount Baldy upper alpine', 'sample_kind': 'representative-alpine-v3', 'agency': 'Utah Avalanche Center', 'forecast_url': 'https://utahavalanchecenter.org/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-02', 'name': 'Teton Pass & Grand Teton National Park', 'country': 'USA', 'region': 'Wyoming & Tetons', 'province_state': 'WY', 'location': 'WY, USA', 'lat': 43.512, 'lon': -110.957, 'upper_reference': 'Mount Glory upper mountain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Bridger-Teton Avalanche Center', 'forecast_url': 'https://bridgertetonavalanchecenter.org/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-03', 'name': 'San Juan Mountains (Red Mountain Pass & Silverton)', 'country': 'USA', 'region': 'Colorado', 'province_state': 'CO', 'location': 'CO, USA', 'lat': 37.898, 'lon': -107.679, 'upper_reference': 'Red Mountain upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Colorado Avalanche Information Center', 'forecast_url': 'https://avalanche.state.co.us/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-04', 'name': 'Thompson Pass (Chugach Mountains)', 'country': 'USA', 'region': 'Alaska', 'province_state': 'AK', 'location': 'AK, USA', 'lat': 61.14, 'lon': -145.72, 'upper_reference': 'Thompson Pass upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Alaska avalanche forecast directory', 'forecast_url': 'https://avalanche.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-05', 'name': 'Turnagain Pass (Kenai Peninsula)', 'country': 'USA', 'region': 'Alaska', 'province_state': 'AK', 'location': 'AK, USA', 'lat': 60.79, 'lon': -149.14, 'upper_reference': 'Tincan upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Chugach National Forest Avalanche Information Center', 'forecast_url': 'https://www.cnfaic.org/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-06', 'name': 'Mount Baker Backcountry', 'country': 'USA', 'region': 'Washington', 'province_state': 'WA', 'location': 'WA, USA', 'lat': 48.847, 'lon': -121.7, 'upper_reference': 'Table Mountain upper alpine', 'sample_kind': 'representative-alpine-v3', 'agency': 'Northwest Avalanche Center', 'forecast_url': 'https://nwac.us/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-07', 'name': 'Mount Rainier (Muir Snowfield & Tatoosh Range)', 'country': 'USA', 'region': 'Washington', 'province_state': 'WA', 'location': 'WA, USA', 'lat': 46.835, 'lon': -121.733, 'upper_reference': 'Camp Muir vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Northwest Avalanche Center', 'forecast_url': 'https://nwac.us/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-08', 'name': 'Mount Shasta', 'country': 'USA', 'region': 'California & Nevada', 'province_state': 'CA', 'location': 'CA, USA', 'lat': 41.409, 'lon': -122.195, 'upper_reference': 'Avalanche Gulch upper mountain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Mount Shasta Avalanche Center', 'forecast_url': 'https://www.shastaavalanche.org/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-09', 'name': 'Eastern Sierra (Mammoth Lakes, Tioga Pass & Bishop)', 'country': 'USA', 'region': 'California & Nevada', 'province_state': 'CA', 'location': 'CA, USA', 'lat': 37.63, 'lon': -119.032, 'upper_reference': 'Mammoth Mountain upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Eastern Sierra Avalanche Center', 'forecast_url': 'https://www.esavalanche.org/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-10', 'name': 'Lake Tahoe Backcountry (Desolation Wilderness & Donner Summit)', 'country': 'USA', 'region': 'California & Nevada', 'province_state': 'CA/NV', 'location': 'CA/NV, USA', 'lat': 39.32, 'lon': -120.35, 'upper_reference': 'Donner Summit upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Sierra Avalanche Center', 'forecast_url': 'https://www.sierraavalanchecenter.org/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-11', 'name': 'Berthoud Pass', 'country': 'USA', 'region': 'Colorado', 'province_state': 'CO', 'location': 'CO, USA', 'lat': 39.796, 'lon': -105.762, 'upper_reference': 'Colorado Mines Peak upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Colorado Avalanche Information Center', 'forecast_url': 'https://avalanche.state.co.us/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-12', 'name': 'Loveland Pass', 'country': 'USA', 'region': 'Colorado', 'province_state': 'CO', 'location': 'CO, USA', 'lat': 39.678, 'lon': -105.855, 'upper_reference': 'Mount Sniktau upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Colorado Avalanche Information Center', 'forecast_url': 'https://avalanche.state.co.us/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-13', 'name': 'Cameron Pass', 'country': 'USA', 'region': 'Colorado', 'province_state': 'CO', 'location': 'CO, USA', 'lat': 40.51, 'lon': -105.89, 'upper_reference': 'Diamond Peaks upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Colorado Avalanche Information Center', 'forecast_url': 'https://avalanche.state.co.us/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-14', 'name': 'Elk Mountains (Aspen, Ashcroft & Maroon Bells)', 'country': 'USA', 'region': 'Colorado', 'province_state': 'CO', 'location': 'CO, USA', 'lat': 39.08, 'lon': -106.93, 'upper_reference': 'Elk Mountains alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Colorado Avalanche Information Center', 'forecast_url': 'https://avalanche.state.co.us/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-15', 'name': 'Tenth Mountain Division Huts (Vail/Leadville/Aspen)', 'country': 'USA', 'region': 'Colorado', 'province_state': 'CO', 'location': 'CO, USA', 'lat': 39.38, 'lon': -106.47, 'upper_reference': 'Central 10th Mountain hut terrain proxy', 'sample_kind': 'representative-alpine-v3', 'agency': 'Colorado Avalanche Information Center', 'forecast_url': 'https://avalanche.state.co.us/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-16', 'name': 'Crested Butte Backcountry (Irwin & Washington Gulch)', 'country': 'USA', 'region': 'Colorado', 'province_state': 'CO', 'location': 'CO, USA', 'lat': 38.88, 'lon': -107.12, 'upper_reference': 'Irwin upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Crested Butte Avalanche Center', 'forecast_url': 'https://cbavalanchecenter.org/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-17', 'name': 'Wolf Creek Pass', 'country': 'USA', 'region': 'Colorado', 'province_state': 'CO', 'location': 'CO, USA', 'lat': 37.48, 'lon': -106.79, 'upper_reference': 'Wolf Creek upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Colorado Avalanche Information Center', 'forecast_url': 'https://avalanche.state.co.us/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-18', 'name': 'Rocky Mountain National Park (Hidden Valley & Bear Lake)', 'country': 'USA', 'region': 'Colorado', 'province_state': 'CO', 'location': 'CO, USA', 'lat': 40.34, 'lon': -105.68, 'upper_reference': 'Hidden Valley upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Colorado Avalanche Information Center', 'forecast_url': 'https://avalanche.state.co.us/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-19', 'name': 'Mount Washington (Tuckerman & Huntington Ravines)', 'country': 'USA', 'region': 'Northeast', 'province_state': 'NH', 'location': 'NH, USA', 'lat': 44.27, 'lon': -71.303, 'upper_reference': 'Mount Washington upper ravine terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Mount Washington Avalanche Center', 'forecast_url': 'https://www.mountwashingtonavalanchecenter.org/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-20', 'name': 'Katahdin / Baxter State Park', 'country': 'USA', 'region': 'Northeast', 'province_state': 'ME', 'location': 'ME, USA', 'lat': 45.904, 'lon': -68.921, 'upper_reference': 'Katahdin upper mountain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Baxter State Park', 'forecast_url': 'https://baxterstatepark.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-21', 'name': 'Mount Mansfield & Bolton Valley Backcountry', 'country': 'USA', 'region': 'Northeast', 'province_state': 'VT', 'location': 'VT, USA', 'lat': 44.543, 'lon': -72.814, 'upper_reference': 'Mount Mansfield upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche safety directory', 'forecast_url': 'https://avalanche.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-22', 'name': 'Brandon Gap & Rochester Backcountry (Green Mountains)', 'country': 'USA', 'region': 'Northeast', 'province_state': 'VT', 'location': 'VT, USA', 'lat': 43.83, 'lon': -72.94, 'upper_reference': 'Brandon Gap upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche safety directory', 'forecast_url': 'https://avalanche.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-23', 'name': 'Adirondack High Peaks (Mount Marcy & Avalanche Pass)', 'country': 'USA', 'region': 'Northeast', 'province_state': 'NY', 'location': 'NY, USA', 'lat': 44.1127, 'lon': -73.9237, 'upper_reference': 'Mount Marcy upper mountain', 'sample_kind': 'representative-alpine-v3', 'agency': 'NY DEC', 'forecast_url': 'https://dec.ny.gov/things-to-do/hiking/adirondack-backcountry/backcountry-information-for-adirondack-park', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-24', 'name': 'Bridger Range', 'country': 'USA', 'region': 'Montana', 'province_state': 'MT', 'location': 'MT, USA', 'lat': 45.818, 'lon': -110.931, 'upper_reference': 'Bridger upper ridge', 'sample_kind': 'representative-alpine-v3', 'agency': 'Gallatin National Forest Avalanche Center', 'forecast_url': 'https://www.mtavalanche.com/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-25', 'name': 'Cooke City & Beartooth Pass', 'country': 'USA', 'region': 'Montana', 'province_state': 'MT/WY', 'location': 'MT/WY, USA', 'lat': 45.003, 'lon': -109.924, 'upper_reference': 'Republic Mountain upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Gallatin National Forest Avalanche Center', 'forecast_url': 'https://www.mtavalanche.com/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-26', 'name': 'Gallatin Range (Hyalite Canyon)', 'country': 'USA', 'region': 'Montana', 'province_state': 'MT', 'location': 'MT, USA', 'lat': 45.43, 'lon': -110.95, 'upper_reference': 'Hyalite upper alpine', 'sample_kind': 'representative-alpine-v3', 'agency': 'Gallatin National Forest Avalanche Center', 'forecast_url': 'https://www.mtavalanche.com/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-27', 'name': 'Glacier National Park (Going-to-the-Sun Road / Marias Pass)', 'country': 'USA', 'region': 'Montana', 'province_state': 'MT', 'location': 'MT, USA', 'lat': 48.7, 'lon': -113.72, 'upper_reference': 'Logan Pass alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche forecast directory', 'forecast_url': 'https://avalanche.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-28', 'name': 'Whitefish Range (Flathead National Forest)', 'country': 'USA', 'region': 'Montana', 'province_state': 'MT', 'location': 'MT, USA', 'lat': 48.5, 'lon': -114.35, 'upper_reference': 'Whitefish upper mountain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche forecast directory', 'forecast_url': 'https://avalanche.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-29', 'name': 'Sawtooth Mountains (Banner Summit & Galena Summit)', 'country': 'USA', 'region': 'Idaho', 'province_state': 'ID', 'location': 'ID, USA', 'lat': 43.89, 'lon': -114.717, 'upper_reference': 'Galena Peak upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Sawtooth Avalanche Center', 'forecast_url': 'https://www.sawtoothavalanche.com/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-30', 'name': 'Teton Canyon & Jedediah Smith Wilderness', 'country': 'USA', 'region': 'Idaho', 'province_state': 'ID/WY', 'location': 'ID/WY, USA', 'lat': 43.76, 'lon': -110.91, 'upper_reference': 'West Teton alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Bridger-Teton Avalanche Center', 'forecast_url': 'https://bridgertetonavalanchecenter.org/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-31', 'name': 'Lost River Range (Mount Borah)', 'country': 'USA', 'region': 'Idaho', 'province_state': 'ID', 'location': 'ID, USA', 'lat': 44.138, 'lon': -113.781, 'upper_reference': 'Borah upper mountain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche forecast directory', 'forecast_url': 'https://avalanche.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-32', 'name': 'Schweitzer Backcountry (Selkirk Mountains)', 'country': 'USA', 'region': 'Idaho', 'province_state': 'ID', 'location': 'ID, USA', 'lat': 48.37, 'lon': -116.66, 'upper_reference': 'Schweitzer upper mountain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche forecast directory', 'forecast_url': 'https://avalanche.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-33', 'name': 'Wallowa Mountains (Anthony Lakes & Wing Ridge)', 'country': 'USA', 'region': 'Oregon', 'province_state': 'OR', 'location': 'OR, USA', 'lat': 44.96, 'lon': -118.23, 'upper_reference': 'Anthony Lakes upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche forecast directory', 'forecast_url': 'https://avalanche.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-34', 'name': 'Mount Hood', 'country': 'USA', 'region': 'Oregon', 'province_state': 'OR', 'location': 'OR, USA', 'lat': 45.36, 'lon': -121.711, 'upper_reference': 'Palmer upper snowfield', 'sample_kind': 'representative-alpine-v3', 'agency': 'Northwest Avalanche Center', 'forecast_url': 'https://nwac.us/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-35', 'name': 'Three Sisters & Bachelor Backcountry (Central Cascades)', 'country': 'USA', 'region': 'Oregon', 'province_state': 'OR', 'location': 'OR, USA', 'lat': 44.1, 'lon': -121.77, 'upper_reference': 'South Sister upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche forecast directory', 'forecast_url': 'https://avalanche.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-36', 'name': 'Crater Lake National Park', 'country': 'USA', 'region': 'Oregon', 'province_state': 'OR', 'location': 'OR, USA', 'lat': 42.92, 'lon': -122.17, 'upper_reference': 'Garfield Peak upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche forecast directory', 'forecast_url': 'https://avalanche.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-37', 'name': 'Stevens Pass (Skyline Lake & Lichtenberg)', 'country': 'USA', 'region': 'Washington', 'province_state': 'WA', 'location': 'WA, USA', 'lat': 47.758, 'lon': -121.1, 'upper_reference': 'Skyline Ridge upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Northwest Avalanche Center', 'forecast_url': 'https://nwac.us/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-38', 'name': 'Snoqualmie Pass (Kendall Peak & Alpental Sidecountry)', 'country': 'USA', 'region': 'Washington', 'province_state': 'WA', 'location': 'WA, USA', 'lat': 47.435, 'lon': -121.385, 'upper_reference': 'Kendall Peak upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Northwest Avalanche Center', 'forecast_url': 'https://nwac.us/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-39', 'name': 'Washington Pass (North Cascades)', 'country': 'USA', 'region': 'Washington', 'province_state': 'WA', 'location': 'WA, USA', 'lat': 48.52, 'lon': -120.66, 'upper_reference': 'Liberty Bell alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Northwest Avalanche Center', 'forecast_url': 'https://nwac.us/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-40', 'name': 'Hurricane Ridge (Olympic National Park)', 'country': 'USA', 'region': 'Washington', 'province_state': 'WA', 'location': 'WA, USA', 'lat': 47.97, 'lon': -123.5, 'upper_reference': 'Hurricane Ridge upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Northwest Avalanche Center', 'forecast_url': 'https://nwac.us/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-41', 'name': 'Hatcher Pass (Talkeetna Mountains)', 'country': 'USA', 'region': 'Alaska', 'province_state': 'AK', 'location': 'AK, USA', 'lat': 61.79, 'lon': -149.27, 'upper_reference': 'Hatcher Pass upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Alaska avalanche forecast directory', 'forecast_url': 'https://avalanche.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-42', 'name': 'Valdez & Worthington Glacier', 'country': 'USA', 'region': 'Alaska', 'province_state': 'AK', 'location': 'AK, USA', 'lat': 61.17, 'lon': -145.8, 'upper_reference': 'Worthington Glacier upper vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Alaska avalanche forecast directory', 'forecast_url': 'https://avalanche.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-43', 'name': 'Juneau Icefield & Douglas Island', 'country': 'USA', 'region': 'Alaska', 'province_state': 'AK', 'location': 'AK, USA', 'lat': 58.42, 'lon': -134.39, 'upper_reference': 'Juneau Icefield alpine vicinity', 'sample_kind': 'representative-alpine-v3', 'agency': 'Alaska avalanche forecast directory', 'forecast_url': 'https://avalanche.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-44', 'name': 'Ruby Mountains (Lamoille Canyon)', 'country': 'USA', 'region': 'California & Nevada', 'province_state': 'NV', 'location': 'NV, USA', 'lat': 40.6, 'lon': -115.37, 'upper_reference': 'Lamoille Canyon upper alpine', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche forecast directory', 'forecast_url': 'https://avalanche.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-45', 'name': 'La Sal Mountains (Moab)', 'country': 'USA', 'region': 'Utah', 'province_state': 'UT', 'location': 'UT, USA', 'lat': 38.45, 'lon': -109.23, 'upper_reference': 'La Sal upper alpine', 'sample_kind': 'representative-alpine-v3', 'agency': 'Utah Avalanche Center', 'forecast_url': 'https://utahavalanchecenter.org/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-46', 'name': 'Uinta Mountains (Mirror Lake Highway)', 'country': 'USA', 'region': 'Utah', 'province_state': 'UT', 'location': 'UT, USA', 'lat': 40.72, 'lon': -110.89, 'upper_reference': 'Bald Mountain upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Utah Avalanche Center', 'forecast_url': 'https://utahavalanchecenter.org/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-47', 'name': 'Logan Canyon (Bear River Range)', 'country': 'USA', 'region': 'Utah', 'province_state': 'UT', 'location': 'UT, USA', 'lat': 41.95, 'lon': -111.53, 'upper_reference': 'Bear River Range upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Utah Avalanche Center', 'forecast_url': 'https://utahavalanchecenter.org/', 'forecast_kind': 'bulletin', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-48', 'name': 'Taos & Wheeler Peak Backcountry (Sangre de Cristo Mountains)', 'country': 'USA', 'region': 'Southwest', 'province_state': 'NM', 'location': 'NM, USA', 'lat': 36.556, 'lon': -105.416, 'upper_reference': 'Wheeler Peak upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche forecast directory', 'forecast_url': 'https://avalanche.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-49', 'name': 'San Francisco Peaks (Humphreys Peak, Flagstaff)', 'country': 'USA', 'region': 'Southwest', 'province_state': 'AZ', 'location': 'AZ, USA', 'lat': 35.346, 'lon': -111.678, 'upper_reference': 'Humphreys Peak upper terrain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche forecast directory', 'forecast_url': 'https://avalanche.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
    {'id': 'us-50', 'name': 'Mount Lassen (Lassen Volcanic National Park)', 'country': 'USA', 'region': 'California & Nevada', 'province_state': 'CA', 'location': 'CA, USA', 'lat': 40.488, 'lon': -121.505, 'upper_reference': 'Lassen Peak upper mountain', 'sample_kind': 'representative-alpine-v3', 'agency': 'Avalanche forecast directory', 'forecast_url': 'https://avalanche.org/', 'forecast_kind': 'resource', 'forecast_note': 'Check current bulletin coverage, access restrictions and conditions for the actual route. Approximate weather sample; not a navigation waypoint.', 'coordinate_status': 'Provisional area reference', 'coordinate_source': ''},
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


BATCH_SIZE = 10
BATCH_PAUSE_SECONDS = 5


def retry_delay(exc, attempt):
    """Respect Retry-After; do not hammer a rate-limited service."""
    fallback = 60 * (2 ** attempt)
    header = exc.headers.get("Retry-After") if exc.headers else None
    if header:
        try:
            return max(fallback, int(header))
        except ValueError:
            try:
                moment = parsedate_to_datetime(header)
                return max(fallback, math.ceil((moment - datetime.now(timezone.utc)).total_seconds()))
            except (ValueError, TypeError, OverflowError):
                pass
    return fallback


def load_forecast_batch(zones):
    """One HTTP request for up to ten locations; response order matches request."""
    params = {
        "latitude": ",".join(str(z["lat"]) for z in zones),
        "longitude": ",".join(str(z["lon"]) for z in zones),
        "hourly": ",".join(HOURLY), "timezone": "UTC",
        "temperature_unit": "celsius", "wind_speed_unit": "kmh",
        "past_days": 8, "forecast_days": 16,
    }
    req = Request(
        API + "?" + urlencode(params),
        headers={"User-Agent": "AlpineDashboard/3.1 (personal noncommercial snow tracker)", "Accept": "application/json"},
    )
    for attempt in range(3):
        try:
            with urlopen(req, timeout=45) as response:
                payload = json.load(response)
            if isinstance(payload, dict) and payload.get("error"):
                raise ValueError(payload.get("reason", "Open-Meteo API error"))
            if isinstance(payload, dict) and len(zones) == 1:
                payload = [payload]
            if not isinstance(payload, list) or len(payload) != len(zones):
                raise ValueError("Unexpected multi-location API response length")
            return payload
        except (HTTPError, URLError, TimeoutError) as exc:
            if isinstance(exc, HTTPError):
                if 400 <= exc.code < 500 and exc.code != 429:
                    raise
                if exc.code == 429:
                    if attempt == 2:
                        raise
                    delay = retry_delay(exc, attempt)
                    if delay > 180:
                        print(f"API requests a {delay}s cooldown; stopping this run.", file=sys.stderr, flush=True)
                        raise
                    print(f"API rate limit (429); cooling down {delay}s before retry.", file=sys.stderr, flush=True)
                    time.sleep(delay)
                    continue
            if attempt == 2:
                raise
            time.sleep(5 * (2 ** attempt))
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
    # Start at the UTC hour after the current (partial) hour, not at midnight.
    # end_hour is the prior completed hour. The first snowfall interval starts
    # two hours after it and ends one hour later. Never mix past and forecast.
    forecast_start = end_hour + timedelta(hours=2)
    future = []
    for day in range(14):
        start = forecast_start + timedelta(days=day)
        amounts = []
        for hour in range(1, 25):
            i = lookup.get(start + timedelta(hours=hour))
            val = numeric(hourly["snowfall"][i]) if i is not None else None
            amounts.append(val if val is not None and val >= 0 else None)
        total = sum(amounts) if all(val is not None for val in amounts) else None
        future.append({"date": start.date().isoformat(), "start_utc": iso_utc(start),
                       "snowfall_cm": rounded(total)})
    forecast_total = rounded(sum(d["snowfall_cm"] for d in future)) if all(d["snowfall_cm"] is not None for d in future) else None
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
        "snowfall_14d": future, "snow_14d_cm": forecast_total, "forecast_start_utc": iso_utc(forecast_start),
        "sample_kind": zone.get("sample_kind", "original-zone-reference"), "sample_lat": zone["lat"], "sample_lon": zone["lon"],
        "error": None,
    }


def fallback_zone(zone, message):
    return {
        **zone,
        "grid_elevation_m": None, "sample_time_utc": None,
        "snow_24h_cm": None, "snow_7d_cm": None, "snow_depth_cm": None,
        "temperature_c": None, "wind_speed_kmh": None,
        "wind_direction_deg": None, "wind_gust_kmh": None,
        "snowfall_7d": [], "snowfall_14d": [], "snow_14d_cm": None, "forecast_start_utc": None, "error": message,
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

    for offset in range(0, len(ZONES), BATCH_SIZE):
        batch = ZONES[offset:offset + BATCH_SIZE]
        print(f"Fetching locations {offset + 1}-{offset + len(batch)} of {len(ZONES)}", flush=True)
        try:
            payloads = load_forecast_batch(batch)
        except (ValueError, KeyError, IndexError, TypeError, HTTPError, URLError, TimeoutError) as exc:
            if isinstance(exc, HTTPError) and exc.code == 429:
                print("Open-Meteo is still rate limiting requests. Stopping to preserve the last good dataset. Retry later, not repeatedly.", file=sys.stderr, flush=True)
                return 1
            print(f"Batch failed: {exc}", file=sys.stderr, flush=True)
            for zone in batch:
                by_id[zone["id"]] = fallback_zone(zone, str(exc))
        else:
            for zone, payload in zip(batch, payloads):
                try:
                    by_id[zone["id"]] = extract_zone(zone, payload, end_hour)
                    print(f"OK   {zone['name']}", flush=True)
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    print(f"FAIL {zone['name']}: {exc}", file=sys.stderr, flush=True)
                    by_id[zone["id"]] = fallback_zone(zone, str(exc))
        if offset + len(batch) < len(ZONES):
            time.sleep(BATCH_PAUSE_SECONDS)

    result = [by_id[zone["id"]] for zone in ZONES]
    successful = sum(zone["error"] is None for zone in result)
    if successful == 0:
        print("No zones succeeded; keeping the last good files and failing this run.", file=sys.stderr)
        return 1

    document = {
        "schema_version": 3,
        "generated_at": iso_utc(now),
        "reference_time_utc": iso_utc(end_hour),
        "source": "Open-Meteo Forecast API (modeled / interpolated data, not station observations)",
        "period_note": "Seven consecutive past 24-hour periods; last period is the past 24 hours.",
        "forecast_note": "Fourteen complete future 24-hour periods starting at the next whole UTC hour. Representative alpine or lodge reference coordinates are approximate and provisional; modeled depth is not a summit measurement.",
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
