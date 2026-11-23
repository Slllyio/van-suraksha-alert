"""Canopy cover from Sentinel-2 (FSI derives canopy density from Sentinel-2), trained on the 1 m canopy-height cover where that
product is sound. The Meta height map has a strip (~cols 2250-3750) where cover collapses while WorldCover/NDVI show forest."""
import numpy as np, lightgbm as lgb
from scipy.ndimage import uniform_filter
S=np.load('static10.npz'); C=np.load('chm10.npz'); N=np.load('s2ndvi10.npz'); ins=S['inside']; wc=S['wc'].astype('float32')
on=np.nan_to_num(N['leafon'],nan=0.3); dry=np.nan_to_num(N['dry_unmasked'],nan=0.15)  # canopy only: unmasked composite is fine, burn scars sit under the canopy signal; y=np.nan_to_num(C['cover3'])
F=[on,dry,on-dry,uniform_filter(on,5),uniform_filter(dry,5),uniform_filter(on,15),uniform_filter(on-dry,15),S['slope'],S['elev'],wc==10,wc==20,wc==30]
X=np.stack([f.astype('float32') for f in F],-1)
cols=np.arange(S['W'])[None,:].repeat(S['H'],0)
bad=(cols>=1300)&(cols<3800)
rng=np.random.default_rng(0)
idx=np.flatnonzero(ins&~bad); idx=rng.choice(idx,600000,replace=False)
# spatial holdout: train on columns <5000 (outside bad), test on >=5000
tr=idx[cols.ravel()[idx]<5000]; te=idx[cols.ravel()[idx]>=5000]
Xf=X.reshape(-1,X.shape[-1]); yf=y.ravel()
m=lgb.LGBMRegressor(n_estimators=400,learning_rate=0.05,num_leaves=63,min_child_samples=200,verbose=-1).fit(Xf[tr],yf[tr])
p=m.predict(Xf[te]); r2=1-((p-yf[te])**2).sum()/((yf[te]-yf[te].mean())**2).sum()
p1=uniform_filter(np.zeros(1),1)
print('pixel R2 spatial holdout', round(r2,3))
m=lgb.LGBMRegressor(n_estimators=400,learning_rate=0.05,num_leaves=63,min_child_samples=200,verbose=-1).fit(Xf[idx],yf[idx])
pred=np.clip(m.predict(Xf).reshape(y.shape),0,1).astype('float32')
# 1 ha check on holdout region
ha_p=uniform_filter(pred,10); ha_y=uniform_filter(y,10); h=ins&(cols>=5000)
print('1 ha R2 (all-data model, east part)', round(1-((ha_p[h]-ha_y[h])**2).sum()/((ha_y[h]-ha_y[h].mean())**2).sum(),3))
for c0 in range(0,7544,750):
    k=ins&(cols>=c0)&(cols<c0+750)
    if k.sum()>1000: print(c0,'chm',round(float(y[k].mean()),2),'s2',round(float(pred[k].mean()),2))
fused=np.where(bad,pred,y).astype('float32')
np.savez_compressed('canopy_s2.npz',s2=pred,fused=fused)
