# All-MP VIIRS fire points, Jan 1 to Jun 30 of each season (Oct 15)

Source: NASA FIRMS area API, standard-processing archive (SP), bounding box 74.0-82.9 E, 21.0-26.9 N (all of MP plus edges). The area is not clipped to forest or beats, so farm fires are included. Script: `firms_mp.py`. It reads the key from the FIRMS_MAP_KEY environment variable; the key is never written to files.

| Satellite | File prefix | Seasons | Points per season |
|---|---|---|---|
| S-NPP | viirs-snpp | 2014-2026 | 47k-132k |
| NOAA-20 | viirs-jpss1 | 2018-2026 (archive starts Apr 1, 2018) | 45k-133k |
| NOAA-21 | viirs-noaa21 | 2023-2026 (archive starts Mar 1, 2023) | 57k-124k |

Columns are standard FIRMS VIIRS: acq_date is UTC and acq_time is HHMM UTC.

Check against the Ratapani files in `../alerts/`, inside the Ratapani box:
- S-NPP 2020 and NOAA-20 2022: identical, 100% of points found.
- NOAA-21 2025: same count (1,959 vs 1,963), but only 34% match exactly on position and time. The Ratapani file came from the near-real-time feed, and the archive version has reprocessed positions.

Five 5-day chunks failed at first with transient HTTP 400 errors (S-NPP Jan 6-20, 2022; NOAA-20 Jan 31-Feb 9, 2025). They were refetched and merged.

## MODIS (added 17 Oct by the FSI/research thread)

`modis_{2014..2026}.csv`: Terra + Aqua MODIS fire points (FIRMS MODIS_SP, collection 6.1) for the same bbox, Jan 1-Jun 30. That is 5.7k-18.9k points per season, 155k in all. Script: `firms_mp_modis.py`, which also reads the key from FIRMS_MAP_KEY. Terra passes about 10:30 and 22:30 IST, which are times of day VIIRS never covers. Aqua passes about 13:30 and 01:30, the same as VIIRS.
