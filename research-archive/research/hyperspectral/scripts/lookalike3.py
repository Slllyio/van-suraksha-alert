import pandas as pd, numpy as np, lightgbm as lgb
from sklearn.metrics import roc_auc_score
L=pd.read_parquet('lookalike_cells.parquet'); L['division']=L.division.fillna('none'); c=L[L.group.isin(['chronic','lookalike'])].copy(); y=(c.group=='chronic').astype(int)
# spectrum: EMIT pre-season cells, only seasons where the cell did NOT burn the season before (no fresh scar)
PEOPLE=['d_village','villages_5k','d_road','road_km_5k','d_major','farm_2k5','farm_5k','settle_5k','d_edge_in','forest_5k']
E=pd.read_parquet('cells_scored.parquet'); E=E[E.burnt_last<0.05]
E=E.merge(L[['cell','group','look','division','nbr_years']],on='cell',suffixes=('_x','')); E=E[E.group.isin(['chronic','lookalike'])].copy(); ye=(E.group=='chronic').astype(int)
print('EMIT cells chronic/lookalike',ye.sum(),(1-ye).sum())
exec(open('scripts/sets.py').read().replace('d.','E.').replace(' in d ',' in E '))
E['div_rate']=0.0
for f in range(5):
    tr=E.fold!=f; r=E[tr].groupby('division').apply(lambda g:(g.group=='chronic').mean()); E.loc[~tr,'div_rate']=E.loc[~tr,'division'].map(r).fillna(ye.mean()).values
E['div_rate']=E.div_rate.fillna(ye.mean())
for nm,cols in [('S2-like',S2c),('Pixxel-like VNIR',VN),('full EMIT',S2c+VN+HY),('division+look',['div_rate','look']),('division+look+S2',['div_rate','look']+S2c),('division+look+VNIR',['div_rate','look']+VN),('division+look+full',['div_rate','look']+S2c+VN+HY),('division+look+people',['div_rate','look']+PEOPLE),('division+look+people+full',['div_rate','look']+PEOPLE+S2c+VN+HY)]:
    p=np.zeros(len(E))
    for f in range(5):
        tr=(E.fold!=f).values
        p[~tr]=lgb.LGBMClassifier(n_estimators=300,learning_rate=0.03,min_child_samples=50,verbose=-1).fit(E.loc[tr,cols],ye[tr]).predict_proba(E.loc[~tr,cols])[:,1]
    print(f'spectrum only, chronic vs lookalike AUC {nm:18s} {roc_auc_score(ye,p):.3f}')
# plain spectral differences, within same look-score bin and division
E['lbin']=pd.qcut(E.look,10,labels=False,duplicates='drop')
for v in ['s2_ndvi','s2_ndmi','s2_ndti','s2_nbr','v_rep','v_pri','v_cri','h_cai','h_lca','h_w970','h_w1200','s2_B4','s2_B11']:
    g=E.groupby(['division','lbin','group'])[v].median().unstack().dropna()
    w=E[E.group=='lookalike'].groupby(['division','lbin']).size().reindex(g.index).fillna(0)
    sd=E[v].std()
    print(f'{v:8s} chronic {E[E.group=="chronic"][v].median():.4f} lookalike {E[E.group=="lookalike"][v].median():.4f}  within-div diff {np.average(g.chronic-g.lookalike,weights=w)/sd:+.2f} SD')
