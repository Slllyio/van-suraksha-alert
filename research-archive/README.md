# Research archive

This is a copy of the project's research folder as it stood on 23 Nov 2026: every script, README, write-up and
notebook, plus every result file (tables, figures, small maps) under 1 MB. That is 2,688 files and 193 MB. The live
engine is not in here; it lives in `../field-system/` (see `../HANDOVER.md`).

Folders keep the same layout as the research folder, so the relative paths inside the READMEs still work.

| Folder | What it is | Start with |
|---|---|---|
| `research/` | Studies: daily rule and ceiling, large fires, big fires, spread, fire timing, fuel from heat, Bhoonidhi, hyperspectral (Nov 22) and more | each subfolder's `README.md`; `research/fire-prediction-landscape.md` |
| `ratapani/` | Ratapani pilot: FSI scouting (control burning, fire lines, joint plan, department burns), spread model, scoring, labels, MP 500 m grid, beats | `ratapani/fsi/scouting/` notes, `ratapani/spread/` |
| `fire-alert-scars/` | Burn scars for MP 2017-26 and the alert-to-scar lookups the engine uses | `fire-alert-scars/README.md`, `fire-alert-scars/mp/README.md` |
| `fuel-map/` | Ratapani fuel maps (v1-v3) and the Prithvi work | `fuel-map/prithvi/README.md` |
| `project-report/` | Full project report (Markdown + figures). The PDF and the compendium zip are on the shared Drive folder | `PROJECT_FULL_REPORT.md` |
| `report/` | Older Oct 15 report | |
| `docs-draft/` | System description draft | `SYSTEM.md` |
| `ARCHIVE_ON_PC.md` | Files moved to Akkshay's PC, with checksums | |

## What is not here

`BIG_FILES_NOT_IN_GIT.csv` lists every file that was left out (5,593 files, 9.5 GB: parquets, rasters, npz arrays,
big GeoJSON, zips, files over 1 MB). They are kept in the project's cloud folder and on Akkshay's PC (`E:\FIRE`). Most
scripts need them to re-run; ask Akkshay for the set a script needs. The biggest groups are `ratapani/spread`
(2.1 GB), `fuel-map/ratapani` (1.7 GB), `fire-alert-scars/mp` (0.9 GB) and `ratapani/fsi` (0.7 GB).

## Caveats

- These are research scripts written against the folder layout `/mnt/project-files/...`; paths may need changing.
- No passwords or keys are in these files (checked before commit). Scripts that need NASA Earthdata or Earth Engine read
  credentials from the environment.
- Dead ends are listed in the full report; check there before re-trying an idea.
