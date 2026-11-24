# Alpine Dashboard — automated backcountry snow tracker

A responsive, no-build dashboard for nine ski-touring areas in Canada and the US. It pulls modeled weather estimates using the free Open-Meteo Forecast API, stores daily snapshots in `snow_history.csv`, and publishes `index.html` plus `data.json` via GitHub Pages.

## What's included

- `fetch_snow.py` — standard-library-only Python 3.11+ collector; no API key, dependencies or secrets required.
- `index.html` — responsive dark UI, Tailwind CSS v4 and Chart.js from public CDNs; region and unit controls, 24h ranking, 7-day chart, official safety links.
- `data.json` — valid **unpopulated** initial dataset (never fake snow observations). The collector replaces this after its first successful run.
- `snow_history.csv` — CSV header initially; new daily rows are accumulated after each successful run.
- `.github/workflows/daily_update.yml` — scheduled/manual fetch, Git commit and explicit GitHub Pages deployment.

## Publish to GitHub Pages (first time)

1. Sign in at https://github.com and create a **public** repository named `alpine-dashboard`. On GitHub Free, public repositories are eligible for GitHub Pages. Do **not** add an additional GitHub Pages template workflow.
2. Unzip the downloaded project. Upload the files and folders **inside** `alpine-dashboard/` to the repository root. Keep the nested file path exactly `.github/workflows/daily_update.yml` (hidden `.github` folder included). Make sure `index.html`, `data.json`, `fetch_snow.py`, and `snow_history.csv` are at repository root. Commit the files to the default branch (`main` is typical).
3. Under **Settings → Actions → General → Workflow permissions**, select **Read and write permissions** if GitHub offers the option, then save. The workflow also declares `contents: write`. If your repository has branch protection, allow the GitHub Actions bot to push changes or use an unprotected default branch for this personal project.
4. Under **Settings → Pages → Build and deployment → Source**, choose **GitHub Actions**. This is essential: a commit made by the default `GITHUB_TOKEN` does not trigger a branch-source Pages rebuild. The included workflow deploys the site itself instead.
5. Go to **Actions → Refresh and publish Alpine Dashboard → Run workflow → Run workflow** on the default branch. It makes nine Open-Meteo requests, generates the first real dataset, commits the files, and deploys the website. Check that the run finishes successfully.
6. Go back to **Settings → Pages**. GitHub will show the site's actual URL. For a normal project repository it has the form `https://YOUR-ACCOUNT.github.io/alpine-dashboard/` (replace the account name with your GitHub username). Bookmark it on your phone; the same link works on your computer.
7. Daily runs are scheduled for **11:00 UTC**, which is **06:00 EST (UTC−5)** all year. During North American daylight saving time this is **07:00 EDT**. GitHub Actions schedules are best-effort and can start late. To keep **06:00 local Eastern time** year-round instead, you would need a DST-aware scheduler/gate rather than a fixed UTC cron.

If **Actions** are disabled, enable them in repository settings. Some repositories require approving the initial workflow. Under **Settings → Actions → General**, confirm GitHub-hosted actions are permitted. Deployment can fail if Pages is not configured with **GitHub Actions** as the source.

## Run locally

```bash
python fetch_snow.py
python -m http.server 8000
```

Then visit http://localhost:8000/ . Do not double-click `index.html` from your file manager; its `fetch('./data.json')` is intended to run on an HTTP server, not a `file://` URL. Internet access is required for the collector and the Tailwind/Chart.js CDNs. No `pip install` step is needed.

If an individual zone's fetch fails, its card shows unavailable data and its failed reading is not added to the history. A total failure exits nonzero and preserves the previous dataset. The workflow will not deploy a false update. Rerunning on the **same UTC date** replaces that day's row for a zone, rather than duplicating it. Successive daily runs append new dates.

## How the data is calculated

Open-Meteo returns **hourly snowfall in centimeters for the preceding hour**, **snow depth in meters**, **2 m air temperature in °C**, and **10 m wind and gusts in km/h**, plus **wind direction in degrees**. The collector uses the latest fully completed hour *before* the current UTC hour, avoiding future forecast hours. It sums the latest 24 hourly snowfall values and builds seven adjacent 24-hour periods aligned to the same UTC hour. Each chart label is the **UTC date on which that period ends**. If hourly data are missing, the associated snowfall total is `null`, not a fabricated zero. Depth is converted from meters to centimeters.

The dashboard shows a “Powder Alert” at **15 cm or more** of modeled 24-hour snowfall. A “High Wind Warning” appears if the latest hourly modeled wind gust is **over 40 km/h**. These are dashboard *weather thresholds*, **not official danger ratings**. Reports older than 36 hours are marked stale and excluded from the top-powder ranking. Metric/Imperial switching does not alter stored values; conversions happen in JavaScript.

## Important avalanche limitations

**Modeled data cannot establish safe backcountry conditions.** Point estimates do not measure true skiable powder, snowpack instability, wind loading, aspect-dependent accumulation, or avalanche danger. Check official bulletins, current field observations, local access rules, terrain and weather before traveling. Avalanche Québec's bulletin covers defined Chic-Chocs mountains; **it does not issue a St-Donat/Montagne Noire forecast**. The Laurentians therefore link to general Avalanche Québec resources and the Adirondacks link to NY DEC backcountry advisories; these buttons are labeled accordingly. Rogers Pass users also need to check **Parks Canada's winter permit/access system** at https://parks.canada.ca/pn-np/bc/glacier/visit/hiver-winter/ski . Agency forecast coverage and operating season vary; verify the area shown on each official site.

## Data source and references

- Weather API: https://open-meteo.com/en/docs
- Avalanche Québec (Chic-Chocs): https://avalanchequebec.ca/bulletin-davalanche/
- Mount Washington Avalanche Center: https://www.mountwashingtonavalanchecenter.org/
- NY DEC: https://dec.ny.gov/things-to-do/hiking/adirondack-backcountry/backcountry-information-for-adirondack-park
- Glacier National Park / Parks Canada: https://parks.canada.ca/pn-np/bc/glacier/visit/hiver-winter/ski
- Avalanche Canada: https://avalanche.ca/en/forecasts
- CAIC: https://www.avalanche.state.co.us/forecasts
- UAC: https://utahavalanchecenter.org/forecast/salt-lake
- BTAC: https://bridgertetonavalanchecenter.org/
- NWAC: https://nwac.us/

This project is for personal, noncommercial use. Open-Meteo's free tier is subject to its terms and usage policies.
