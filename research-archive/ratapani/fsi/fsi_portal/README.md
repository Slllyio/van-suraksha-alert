# FSI fire portal exports (pulled 14 Oct 2026)

These come from FSI's open portal at fsiforestfire.gov.in. No login is needed. The pull commands are in `../scouting/ground_truth_sources.md`.

## Fire points with beat and compartment (season from 1 Nov 2025)

Source: Fire Point Search. Each row is one alert.

**Columns:** Fire_Date, Fire_Time, Source_Type (VIIRS/MODIS), Lat, Lon, State, District, Circle, Division, Range, Block, Beat, Compartment_No.

| File | Area covered | Rows |
|---|---|---|
| fsi_pts_obedullaganj.csv | Obedullahganj division | 1,722 (1,114 unique) |
| obd_2026.csv | Obedullahganj | 1,651 (a second export) |
| fsi_pts_raisen.csv | Raisen | 1,195 |
| fsi_pts_sehore.csv | Sehore | 1,644 |
| fsi_pts_bhopal.csv | Bhopal | 309 |

**Use:**
- Join to the 500 m grid to get FSI's own beat and compartment for each cell.
- Check `../../beats/cell_beat.csv` against it.
- Points that fall in more than one beat show where alerts are sent to several beats.

## Large forest fire events, MP 2019-2025

`lff_mp.csv` has 7,535 events.

**Columns:**
- F_T_D / L_T_D: first and last detection, as yyyymmdd_hhmm.
- Location: district, division, range.
- Fire name.
- Inside point: INSIDE_X / INSIDE_Y.
- Bounding box: EXT_MIN/MAX_X/Y.

About 685 events fall in a box around Ratapani.

**Use:** check our scar dates and extents, and measure growth rates for the spread model.

## FSI VIIRS satellite and position accuracy (added 14 Oct 2026, from the field alerts thread)
FSI's VIIRS alerts came from S-NPP from Nov 2025 to 26 Apr 2026, and from NOAA-21 from about May 2026 (matched against FIRMS pass times). In the S-NPP months, FSI pixel positions are a median 0.25 km off NASA's FIRMS positions (only 13% within 0.1 km). In the NOAA-21 months, 98% are within 0.1 km. For any Nov-Apr FSI-to-FIRMS point join, use a radius of about 0.4 km.
