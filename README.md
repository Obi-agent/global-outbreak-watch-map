# Global Outbreak Watch

Static GitHub Pages dashboard for monitoring official and trusted public health outbreak signals.

## Daily refresh

The scheduled GitHub Actions workflow runs `scripts/update_outbreak_data.py` every morning at 05:18 UTC and commits refreshed `gow_data.geojson` plus `gow_sources.json` when anything changes.

Active sources include:

- WHO Disease Outbreak News API
- CDC Travel Health Notices
- CDC U.S. and international outbreak lists
- ECDC Communicable Disease Threats Report RSS
- PAHO Epidemiological Alerts
- UKHSA/GOV.UK news and outbreaks-under-monitoring pages

The updater uses dependency-free Python and best-effort extraction. Every generated map point retains a direct source URL and source status is embedded in the GeoJSON metadata.

## Local refresh

```powershell
python scripts/update_outbreak_data.py
python -m http.server 8000
```
