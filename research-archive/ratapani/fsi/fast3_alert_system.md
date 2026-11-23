# FSI Technical Information Series Vol 1 No 2 (2019): FAST 3.0 alert system

**Source:** E:\FIRE\fsi_data\technical-information-series-v1-n2.pdf, copied to `fsi_reports/`. Read in full.

**For:**
- "Live fire alerts and field checks" (main use).
- The prediction threads (pre-warning and KBDI sections).

## How FSI alerts flow (FAST 3.0)

1. MODIS and VIIRS fire points arrive from NRSC's Shadnagar ground station.
2. A custom filter keeps only points inside Recorded Forest Area + forest cover. Industrial, mining and solar sites are masked out, with a 500 m buffer.
3. Each point is tagged with state, district, division, range, **beat** and compartment, using the forest department's boundary layers.
4. Alerts are sent by SMS and email to registered staff at each level, down to beat level (20 states in 2019). The Van Agni portal now does the same.
5. A WMS layer shows the last 3 days of points.

## Large fire tracking

- **Trigger:** at least 3 VIIRS pixels next to each other (about 40 ha or more).
- **Tracking:** the fire is followed while it burns, plus 3 days after its last detection. New points nearby are counted as the same fire.
- **Naming:** each large fire is named by its range and gets daily updates.

## Field feedback (closest to "attended or not")

- Each SMS alert carries a link to a feedback form with these fields:
  - fire yes / no
  - area burnt (ha)
  - land type
  - fire type (ground, surface, crown)
  - cause
- **No photo, no GPS check and no time-to-reach field.** The form records only whether there was a fire. It does not record whether staff reached it, or when. Our field system's photo plus GPS plus timestamp design adds exactly this.
- Feedback is stored behind FSI's login. MP sent 14 this season (see the fuel deck).

## Stated limits

- About 6 satellite passes a day. Alerts lag the overpass by 1–1.5 h.
- Fires under cloud or under thick canopy, and small fires, are missed.
- The alert location is the pixel centre, which can be up to about 190 m (VIIRS) or 500 m (MODIS) from the fire.
- An alert near a beat junction is sent to **all** adjacent beats.

## Fire pre-warning (for the prediction threads)

- **Started 2016.** From 2017 it runs on a 5 km grid.
- **Inputs:**
  - forest density and forest type
  - relative humidity and Tmax (MOSDAC)
  - 7-day rainfall (IMD CRIS), plus the IITM forecast
  - FSI's alert database, 2004–2016
- **Output:** a weekly KML of danger by grid cell. No skill score is reported.
- **KBDI pilot near Dehradun:** fires occurred when the Keetch-Byram Drought Index was above 600. KBDI bottoms out in mid-March, which gave a 10–12 week lead to the main season. That is a season-timing signal, not a where signal.

## Other facts

- **NFI:** 9.89% of forest is heavily fire-affected and 54.40% mildly.
- **World Bank study cited:** 20 districts hold 44% of detections. Burnt-area hotspots are in Central India.

## For our builds

- **Field system:**
  - Copy FSI's alert attribution chain: point → beat, junction alerts sent to every adjacent beat, 500 m industrial mask, 3-day display window.
  - Copy the large-fire rule (3 or more adjacent VIIRS pixels, tracked until out plus 3 days).
  - Add what FSI lacks: photo, GPS, arrival time and the staff member who attended.
- **Prediction:** the 5 km weekly pre-warning is far coarser than our 500 m daily scoring. Our model already beats fire-weather indices (FWI, all 9 MP reserves). KBDI could be tried as a single season-level feature. ERA5 already shows weather decides *when*, not *where*, in Ratapani.
