"""70 m hot pixels (anomaly > 10 K above the 1-2 km ring, inside scar + 100 m) for every refetched clip; same rules as big-fires b16b."""
import glob, os, pickle, numpy as np, pandas as pd
from rasterio.features import rasterize
from rasterio.transform import Affine
S = pickle.load(open('/tmp/claude-0/fronts/fire_scars.pkl', 'rb')); out = []
for fp in sorted(glob.glob('/tmp/claude-0/eco_cache/*.npz')):
    fid = int(os.path.basename(fp).split('_')[0]); gid = os.path.basename(fp)[len(str(fid)) + 1:-4]
    z = np.load(fp); lst, cloud = z['LST'].astype(float), z['cloud']; tr = Affine(*z['transform']); t0 = pd.Timestamp(gid.split('_')[6][:15])
    poly = S[fid]; H, W = lst.shape
    near = rasterize([(poly.buffer(100), 1)], out_shape=(H, W), transform=tr, fill=0).astype(bool)
    ring = rasterize([(poly.buffer(2000).difference(poly.buffer(1000)), 1)], out_shape=(H, W), transform=tr, fill=0).astype(bool)
    clear = np.isfinite(lst) & (lst > 250) & (cloud == 0)
    if clear[ring].sum() < 50: continue
    an = lst - np.median(lst[ring & clear]); hot = (an > 10) & near & clear
    rr, cc = np.where(hot)
    for r_, c_ in zip(rr, cc):
        out.append(dict(fire=fid, granule=gid, t0=t0, x=tr.c + (c_ + .5) * tr.a, y=tr.f + (r_ + .5) * tr.e, an=an[r_, c_]))
H = pd.DataFrame(out); H.to_csv('/tmp/claude-0/eco_cache/hot_pixels.csv', index=False)
print(len(H), H.groupby(['fire', 't0']).size().describe())
