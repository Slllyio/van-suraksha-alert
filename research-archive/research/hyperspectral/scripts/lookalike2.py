import pandas as pd, numpy as np, lightgbm as lgb
from sklearn.metrics import roc_auc_score
L=pd.read_parquet('lookalike_cells.parquet'); L['division']=L.division.fillna('none'); c=L[L.group.isin(['chronic','lookalike'])].copy(); y=(c.group=='chronic').astype(int)
print('reserve share: chronic %.3f lookalike %.3f'%(c[c.group=="chronic"].reserve.mean(),c[c.group=="lookalike"].reserve.mean()))
r=c.groupby('division').apply(lambda g:(g.group=='chronic').mean()); print('division alone AUC',round(roc_auc_score(y,c.division.map(r)),3))
# depth inside forest bands: share chronic among (chronic+lookalike)
c['depth']=pd.cut(c.d_edge_in,[-.1,0.5,1,2,3,20]); c['vil']=pd.cut(c.villages_5k,[-1,0,2,5,40])
print(c.groupby('depth').apply(lambda g:pd.Series({'n':len(g),'chronic_share':(g.group=='chronic').mean()})).round(3))
print(c.groupby('vil').apply(lambda g:pd.Series({'n':len(g),'chronic_share':(g.group=='chronic').mean()})).round(3))
# within the same division: does depth/villages still separate?
for v in ['d_edge_in','villages_5k','d_road','forest_5k','farm_5k','nbr_years']:
    rho=c.groupby('division').apply(lambda g: g[v].rank().corr((g.group=='chronic').astype(int)) if g.group.nunique()==2 and len(g)>50 else np.nan)
    print(f'{v:12s} within-division corr with chronic: median {rho.median():+.2f}, same sign in {(np.sign(rho)==np.sign(rho.median())).mean():.0%} of {rho.notna().sum()} divisions')
# spectrum: EMIT pre-season cells, only seasons where the cell did NOT burn the season before (no fresh scar)
E=pd.read_parquet('cells_scored.parquet'); E=E[E.burnt_last<0.05]
E=E.merge(L[['cell','group','look']],on='cell'); E=E[E.group.isin(['chronic','lookalike'])].copy(); ye=(E.group=='chronic').astype(int)
print('EMIT cells chronic/lookalike',ye.sum(),(1-ye).sum())
exec(open('scripts/sets.py').read().replace('d.','E.').replace(' in d ',' in E '))
for nm,cols in [('S2-like',S2c),('Pixxel-like VNIR',VN),('full EMIT',S2c+VN+HY)]:
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
