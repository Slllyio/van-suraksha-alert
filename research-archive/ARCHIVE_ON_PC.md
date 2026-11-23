# Files moved from the shared folder to Akkshay's PC

Moved 2026-10-18 to free space in /mnt/project-files. Each file was copied to the PC at
`E:\FIRE\cloud_archive\<same relative path>`, and the copy's size and SHA-256 were checked
against the original before the original was removed. A copy of this list is at
`E:\FIRE\cloud_archive\MANIFEST.md`.

To get a file back, ask a thread with access to the PC folder E:\FIRE to copy it from
`E:\FIRE\cloud_archive\...` into the same path here.

| Shared folder path (removed) | PC path | Bytes | SHA-256 | Why it was cold |
|---|---|---|---|---|
| fuel-map/ratapani/rothermel/rothermel_peak_10m.tif | E:\FIRE\cloud_archive\fuel-map\ratapani\rothermel\rothermel_peak_10m.tif | 269,449,521 | 2fd0d4c0679f6a9f872d8964e27a47ffe8bad50ee976098fb6840c2731e28942 | spread reads only the 20 m Rothermel maps |
| fuel-map/ratapani/work/phenoclass.npz | E:\FIRE\cloud_archive\fuel-map\ratapani\work\phenoclass.npz | 142,470,110 | 3fcd02d4889ee43ae52ddc43a56a2fbed70020538ac932b90858e615fb0b5473 | old fuel map working array; cover_phenology_10m.tif stays |
| fuel-map/ratapani/work/chm10.npz | E:\FIRE\cloud_archive\fuel-map\ratapani\work\chm10.npz | 102,320,711 | a7a3b86cc3a82b062965f074efb89c2d9e7fbec8fbbd32917b251f30b01cb118 | old fuel map working array |
| fuel-map/ratapani/work/teakprob2.npy | E:\FIRE\cloud_archive\fuel-map\ratapani\work\teakprob2.npy | 101,029,376 | 4f1309d1329679fdd4f1bb65414a384b2ce6edb437cb4377b5bbee6eea12c639 | teak_probability_10m.tif stays |
| fuel-map/ratapani/work/maps_v2.npz | E:\FIRE\cloud_archive\fuel-map\ratapani\work\maps_v2.npz | 89,659,182 | 314f8ff16a67f6c83f065ee26070ed3329067998134e28aa9d4c946b0ee47dbf | fuel map v2, replaced by v3 |
| fuel-map/ratapani/work/fsi_fireprone10.npy | E:\FIRE\cloud_archive\fuel-map\ratapani\work\fsi_fireprone10.npy | 25,257,440 | 3f08b2da5600a089f07d209db5d4114cbfb17836d060c0ac3c35fcbdf58c4d6a | fsi_fire_prone_2021_10m.tif stays |
| fuel-map/ratapani/work/fsi_fcm_ftm10.npz | E:\FIRE\cloud_archive\fuel-map\ratapani\work\fsi_fcm_ftm10.npz | 1,110,238 | eb1397008ed05473845e75b8484296edb6abd73ef1ae7a86e6f746ac42958e3c | FSI tifs stay |
| ratapani/ee/modis_ndvi_ndmi.csv | E:\FIRE\cloud_archive\ratapani\ee\modis_ndvi_ndmi.csv | 95,843,558 | fe6ed9dad37117247495944b571edd18865364ff4d2b9b1b3ffb80ba303cb7f4 | EE NDVI layer, a dead end; only research/ratapani-ignition/scripts/round3.py read it |
| ratapani/ee/modis_lst.csv | E:\FIRE\cloud_archive\ratapani\ee\modis_lst.csv | 57,376,215 | a5b36f285eff58f317f5776a01f9e055bffbfc40b26439661b5f9e4594c87d64 | EE LST layer, a dead end; no script reads it |
| **Total** | | **884,516,351 (844 MB)** | | |

## Checked and kept here (still read by active threads)
- fuel-map/ratapani/work/static10.npz, leaffall.npz, s2ndvi10.npz, canopy_s2.npz: read by ratapani/scoring/v2/fuel_cells.py and fuel-map/ratapani/v3.
- fuel-map/ratapani/rothermel/*_20m.tif and rothermel/loosebed/: spread fuel inputs (ratapani/spread/scripts/prep_rfuel.py).
- research/fire-continuity, research/fuel-from-heat, research/big-fires, research/prediction-review: imported or read by spread, Prithvi, field-system and scoring scripts.
- ratapani/ee/era5, terrain, worldcover, proximity, alphaearth: read by spread, Prithvi and ratapani/fsi scripts.
