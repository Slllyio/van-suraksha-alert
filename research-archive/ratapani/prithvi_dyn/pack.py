"""Reduce the dynamic Prithvi embeddings to 16 principal components (fit on a random sample of cell-steps across all seasons;
unsupervised, no labels) and pack them for the shared folder: prithvi_dyn_pca16.npz with steps (YYYY-MM-DD of each step d,
the composite covers the 15 days before d) and X (n_steps, 3614, 16) float16, plus the explained variance."""
import glob, os, numpy as np
from sklearn.decomposition import PCA
H = r'E:\FIRE\ratapani\prithvi_dyn'
fs = sorted(glob.glob(H + r'\emb\*.npy')); steps = [os.path.basename(f)[:4] + '-' + os.path.basename(f)[5:7] + '-' + os.path.basename(f)[7:9] for f in fs]
rs = np.random.default_rng(0); sample = np.concatenate([np.load(f)[rs.choice(3614, 300, replace=False)].astype(np.float32) for f in fs])
p = PCA(16, random_state=0).fit(sample); print('explained', p.explained_variance_ratio_.round(3), 'total', p.explained_variance_ratio_.sum().round(3))
X = np.stack([p.transform(np.load(f).astype(np.float32)) for f in fs]).astype(np.float16)
os.makedirs(H + r'\push', exist_ok=True)
np.savez_compressed(H + r'\push\prithvi_dyn_pca16.npz', steps=np.array(steps), X=X, explained=p.explained_variance_ratio_)
print('steps', len(steps), steps[0], steps[-1], 'X', X.shape, os.path.getsize(H + r'\push\prithvi_dyn_pca16.npz') // 1e6, 'MB')
