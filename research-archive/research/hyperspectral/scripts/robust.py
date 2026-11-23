# robustness: (1) hold out whole flight lines/dates instead of 10 km blocks; (2) feature importance
import pandas as pd, numpy as np, lightgbm as lgb
from sklearn.metrics import roc_auc_score
d=pd.read_parquet('cells_scored.parquet')
exec(open('scripts/sets.py').read())
d['gday']=d.granule.str[17:25]
d['yr']=d.year
gs=d.gday.unique(); print('dates',gs)
for name in ['history+GIS','+S2-like','+S2+Pixxel-like VNIR','+S2+full EMIT']:
    cols=sets[name]; p=np.zeros(len(d))
    for g in gs:
        te=(d.gday==g).values
        m=lgb.LGBMClassifier(n_estimators=400,learning_rate=0.03,min_child_samples=50,subsample=0.8,subsample_freq=1,colsample_bytree=0.7,verbose=-1).fit(d.loc[~te,cols],d.y[~te])
        p[te]=m.predict_proba(d.loc[te,cols])[:,1]
    per=[roc_auc_score(d.y[d.gday==g],p[d.gday==g]) for g in gs]
    print(f'{name:24s} date-held-out AUC {roc_auc_score(d.y,p):.3f}  per date',np.round(per,3))
cols=sets['+S2+full EMIT']
m=lgb.LGBMClassifier(n_estimators=400,learning_rate=0.03,min_child_samples=50,verbose=-1,importance_type='gain').fit(d[cols],d.y)
imp=pd.Series(m.feature_importances_,cols).sort_values(ascending=False); print((imp/imp.sum()).head(20).round(3))
print('cross-season: train one season, test the other')
for name in ['history+GIS','+S2-like','+S2+Pixxel-like VNIR','+S2+full EMIT']:
    cols=sets[name]; r=[]
    for a,b in [(2023,2025),(2025,2023)]:
        m=lgb.LGBMClassifier(n_estimators=400,learning_rate=0.03,min_child_samples=50,subsample=0.8,subsample_freq=1,colsample_bytree=0.7,verbose=-1).fit(d.loc[d.yr==a,cols],d.y[d.yr==a])
        r.append(roc_auc_score(d.y[d.yr==b],m.predict_proba(d.loc[d.yr==b,cols])[:,1]))
    print(f'{name:24s} 2023->2025 {r[0]:.3f}  2025->2023 {r[1]:.3f}')
