# Prithvi tokens, 10 regions, compact (19 Oct 2026)
{region}_{season}.npz for 10 boxes of 40 x 40 km, seasons 2022-25, on the 500 m mp_grid (cell = row*1829+col).
- cell: grid cell id (6,400 per box)
- tok64: frozen Prithvi-EO-2.0 300M tokens (pre-season frames Apr/Nov/Jan/Feb, up to 14 Feb) cut from 3072 to 64 dims by PCA
- raw: 36 raw HLS band values that went into Prithvi
- clear: share of clear looks
pca64.npz holds the PCA (mean, comp). It was fit on all 10 regions together, so refit within training regions for a held-out-region test. Full 3072-dim tokens (1.6 GB) are kept in the Prithvi thread's scratch area only.
