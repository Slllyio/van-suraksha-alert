import pandas as pd, numpy as np, lightgbm as lgb
from sklearn.metrics import roc_auc_score
d=pd.read_parquet('cells_scored.parquet'); exec(open('scripts/sets.py').read())
d=d[(d.lc_teak>0.6)|(d.lc_sal>0.6)].copy(); d['t']=(d.lc_teak>0.6).astype(int)
print('teak',d.t.sum(),'sal',(1-d.t).sum())
for name,cols in [('S2-like',S2c),('Pixxel-like VNIR',VN),('full EMIT',S2c+VN+HY),('terrain only',['elev','slope','rugged','tpi5','south'])]:
    p=np.zeros(len(d))
    for k in range(5):
        tr=(d.fold!=k).values
        p[~tr]=lgb.LGBMClassifier(n_estimators=300,learning_rate=0.05,min_child_samples=50,verbose=-1).fit(d.loc[tr,cols],d.t[tr]).predict_proba(d.loc[~tr,cols])[:,1]
    print(f'{name:18s} teak-vs-sal AUC {roc_auc_score(d.t,p):.3f}')
