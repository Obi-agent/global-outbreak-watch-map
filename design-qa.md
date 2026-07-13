# Design QA

Date: 13 July 2026

Reference: supplied professional atlas concept, desktop 1440 x 1024

Implementation: ObiCRM Atlas, desktop 1440 x 1024 and mobile 390 x 844

## Visual Comparison

- Branding and hierarchy match the reference: ObiCRM Atlas wordmark, Global Outbreak Watch descriptor, date and source health, then compact workspace actions.
- The desktop structure matches the concept: five-row incident ledger, bounded world atlas, expandable evidence drawer, and source-health footer.
- Ledger columns reproduce Incident, Severity, Trend, Confidence, and Updated. Disease-specific icon orbs, directional arrows, confidence dots, semantic badges, pagination, and the selected-row outline are present.
- The map includes the Map/List segmented control, geographic-precision legend, clusters, labelled active-page incidents, selected-incident emphasis, zoom, reset, scale, and minimap.
- Esri World Imagery provides the real satellite surface; the separate World Boundaries and Places overlay keeps country, city, region, and water names in English at both world and operational zoom levels.
- The evidence drawer reproduces the criticality rationale, confidence and corroborating authorities, and a latest-first official-update timeline.
- White and cool-gray surfaces carry the operational hierarchy; red, orange, yellow, green, blue, and purple remain semantic accents rather than a monotone theme.

## Map Boundary

- Horizontal drag was exercised repeatedly in both directions at 1440 x 1024.
- `maxBounds`, full bounds viscosity, `noWrap`, and tile bounds keep the viewport inside one world.
- Loaded zoom-2 tile columns remained in the valid 0-3 range after both boundary tests. No repeated Earth or marker-free duplicate tiles appeared.
- The satellite imagery and English-label layers both retained valid non-wrapping tile coordinates after the basemap change.

## Responsive Comparison

- Desktop 1440 x 1024: no overlap, clipping, horizontal overflow, blank map, missing tiles, or uncontrolled layout shift observed.
- Mobile 390 x 844: zero horizontal overflow; Map and List remain available from the first screen.
- Mobile ledger rows form a continuous 90px three-column list with compact pagination.
- Mobile evidence stays closed on initial load, opens from incident selection, scrolls internally, and closes without changing the selected incident.

## Interaction Checks

- Directional trend filter: 11 Worsening incidents; every visible row reported Worsening and the URL encoded the filter.
- Pagination: page 2 changed the visible incident set and reported `Showing 6-10 of 62 incidents`.
- Map/List switching, watch follow/unfollow, source filters, selected evidence, map reset, and ledger collapse/expand were exercised successfully.
- Updated incident set: 62 incidents from 146 published signals across 8 current sources.
- The current source state is accurately shown as 8 of 8 online with quality 95/100 rather than copying the reference's illustrative warning state.

## Accessibility

- Controls have semantic labels, focus-visible outlines, reduced-motion handling, and practical targets.
- Ledger rows are keyboard-selectable; dialogs use native modal semantics; the map has an explicit bounded-world accessible label.
- Severity, trend, confidence, precision, and source status are reinforced with text and do not rely on color alone.

final result: passed
