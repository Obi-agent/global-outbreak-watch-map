# ObiCRM Atlas

Static GitHub Pages analyst workspace for monitoring official public-health outbreak signals.

The interface groups related authority signals into explainable incidents, with severity, directional trend, confidence, geographic precision, evidence, watchlists, source health, shareable filters, and CSV export. The raw linked notices always remain available for professional verification.

## Daily refresh

The scheduled GitHub Actions workflow runs `scripts/update_outbreak_data.py` every morning at 05:18 UTC and commits refreshed `gow_data.geojson` plus `gow_sources.json` when anything changes.

Active sources include:

- WHO Disease Outbreak News API
- CDC Travel Health Notices
- CDC U.S. and international outbreak lists
- ECDC Communicable Disease Threats Report RSS
- PAHO Epidemiological Alerts
- UKHSA/GOV.UK news and outbreaks-under-monitoring pages

The dependency-free updater now:

- screens noisy or suspicious labels before publication
- normalizes countries and resolves common aliases
- groups related signals into stable incident records
- records explainable severity, evidence-language trend, confidence, geography, and quality assessments
- retains recent last-known-good signals when an individual source fails
- publishes daily source health, a 0-100 quality score, and a 14-day quality history

The atlas uses Esri World Imagery satellite tiles with a separate English boundaries-and-places reference layer. Both maps are constrained to one world.

Report dates come from the authority, not the daily scan. A dated weekly reporting period may be used when no publication metadata is available. Unknown dates stay blank. Directional trends use only the newest dated, non-retained evidence, no more than seven calendar days old. Older evidence is historical. Missing dates and reports that do not establish a direction are marked not assessed. Severity describes the report and is not a forecast.

Evidence counts are distinct reports per feed and URL, not the number of country markers. Feed counts do not establish independent corroboration. Saved links to regrouped single bulletins open that bulletin while it remains in the dataset.

Every published signal retains its direct authority URL. The resulting classifications support triage; linked authority notices remain the operational source of truth.

## Local refresh

```powershell
python scripts/update_outbreak_data.py
python -m http.server 8000
```

Run the quality checks with:

```powershell
python -m unittest discover -s tests -v
```
