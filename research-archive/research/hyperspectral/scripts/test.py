# Does a pre-season EMIT spectrum (Jan-early Feb) tell which 500 m forest squares burn that season,
# beyond burn history + GIS + Sentinel-2-like bands? Pixxel-like (472-890 nm) vs full SWIR.
import glob, numpy as np, pandas as pd, lightgbm as lgb
from sklearn.metrics import roc_auc_score
from sklearn.decomposition import PCA
P='/mnt/project-files/'
fs=sorted(glob.glob('emit/*.parquet')); ref=[c for c in pd.read_parquet(fs[0]).columns if c.startswith('w')]
def ld(f):
    x=pd.read_parquet(f); w=[c for c in x.columns if c.startswith('w')]; assert len(w)==len(ref); return x.rename(columns=dict(zip(w,ref)))
sp=pd.concat([ld(f) for f in fs])
sp['year']=sp.granule.str[17:21].astype(int)
sp=sp[np.isfinite(sp[[c for c in sp.columns if c.startswith('w')]]).all(1)]
sp=sp.sort_values('npix').drop_duplicates(['cell','year'],keep='last')
wc=[c for c in sp.columns if c.startswith('w')]; wl=np.array([float(c[1:]) for c in wc])
cy=pd.read_parquet(P+'fire-alert-scars/mp/burn_history/cell_year.parquet')
st=pd.read_parquet(P+'ratapani/mp_grid/static_gis_v1.parquet')
d=sp.merge(st,on='cell')
d=d[(d.lc_forest+d.lc_scrub>0.5)&(d.beat_frac>0.5)]
# season label + history from earlier seasons only
lab=cy[['cell','year','burned_forest']]
d=d.merge(lab,on=['cell','year'],how='left').fillna({'burned_forest':0})
d['y']=(d.burned_forest>=0.3).astype(int)
hist=[]
for yr in sorted(d.year.unique()):
    h=cy[cy.year<yr]; g=h.assign(b=h.burned_forest>=0.1).groupby('cell')
    t=pd.DataFrame({'yrs_burnt':g.b.sum(),'mean_burnt':g.burned_forest.mean(),
       'last_gap':yr-h[h.burned_forest>=0.1].groupby('cell').year.max(),
       'burnt_last':h[h.year==yr-1].set_index('cell').burned_forest}).reset_index(); t['year']=yr; hist.append(t)
d=d.merge(pd.concat(hist),on=['cell','year'],how='left')
d[['yrs_burnt','mean_burnt','burnt_last']]=d[['yrs_burnt','mean_burnt','burnt_last']].fillna(0); d['last_gap']=d.last_gap.fillna(20)
def band(lo,hi): return d[[c for c,w in zip(wc,wl) if lo<=w<=hi]].mean(1)
S2={'B2':(458,523),'B3':(543,578),'B4':(650,680),'B5':(698,713),'B6':(733,748),'B7':(773,793),'B8':(785,900),'B8A':(855,875),'B11':(1565,1655),'B12':(2100,2280)}
for k,(a,b) in S2.items(): d['s2_'+k]=band(a,b)
d['s2_ndvi']=(d.s2_B8-d.s2_B4)/(d.s2_B8+d.s2_B4); d['s2_nbr']=(d.s2_B8-d.s2_B12)/(d.s2_B8+d.s2_B12)
d['s2_ndmi']=(d.s2_B8-d.s2_B11)/(d.s2_B8+d.s2_B11); d['s2_ndti']=(d.s2_B11-d.s2_B12)/(d.s2_B11+d.s2_B12)
R=lambda x: band(x-6,x+6)
# hyperspectral-only physics indices (SWIR): dry litter (cellulose/lignin), canopy/leaf water
d['h_cai']=0.5*(R(2031)+R(2211))-R(2101)
d['h_lca']=100*((R(2205)-R(2165))+(R(2205)-R(2330)))
d['h_sindri']=(R(2210)-R(2260))/(R(2210)+R(2260))
d['h_ndli']=(np.log(1/R(1754))-np.log(1/R(1680)))/(np.log(1/R(1754))+np.log(1/R(1680)))
d['h_w970']=0.5*(R(900)+R(1060))-R(970); d['h_w1200']=0.5*(R(1090)+R(1265))-R(1200)
# Pixxel-like VNIR indices (red edge, pigments)
d['v_rep']=700+40*((R(670)+R(780))/2-R(700))/(R(740)-R(700))
d['v_pri']=(R(531)-R(570))/(R(531)+R(570)); d['v_cri']=1/R(510)-1/R(550); d['v_ari']=1/R(550)-1/R(700)
vn=[c for c,w in zip(wc,wl) if 472<=w<=890]; full=[c for c,w in zip(wc,wl) if not (1330<w<1450 or 1780<w<1960)]
def pcs(cols,n,pre):
    X=d[cols].values; X=X/np.clip(np.linalg.norm(X,axis=1,keepdims=True),1e-6,None)  # shape of spectrum
    Z=PCA(n,random_state=0).fit_transform(np.c_[X,np.log(d[cols].mean(1).clip(1e-4)).values[:,None]])
    for i in range(n): d[f'{pre}{i}']=Z[:,i]
    return [f'{pre}{i}' for i in range(n)]
pv=pcs(vn,15,'pv'); pf=pcs(full,20,'pf')
d['blk']=(d.row//20)*1000+(d.col//20)   # 10 km blocks
blocks=d.blk.unique(); rng=np.random.default_rng(0); fold=dict(zip(blocks,rng.integers(0,5,len(blocks)))); d['fold']=d.blk.map(fold)
GIS=['elev','slope','rugged','tpi5','south','lc_forest','lc_scrub','lc_grass','lc_sal','lc_teak','lc_drymix','lc_moistmix','lc_bamboo','lc_degraded','forest_5k','farm_5k','d_edge_in','d_road','d_village','villages_5k','road_km_5k']
HIST=['yrs_burnt','mean_burnt','last_gap','burnt_last']
S2c=[c for c in d if c.startswith('s2_')]; VN=pv+[c for c in d if c.startswith('v_')]; HY=pf+[c for c in d if c.startswith('h_')]
sets={'history+GIS':HIST+GIS,'+S2-like':HIST+GIS+S2c,'+S2+Pixxel-like VNIR':HIST+GIS+S2c+VN,'+S2+full EMIT':HIST+GIS+S2c+VN+HY,
      'S2-like only':S2c,'Pixxel-like only':VN,'full EMIT only':S2c+VN+HY,'SWIR litter/water indices only':[c for c in d if c.startswith('h_')]}
def cv(cols,sub):
    p=np.zeros(len(sub))
    for k in range(5):
        tr=sub.fold!=k; m=lgb.LGBMClassifier(n_estimators=400,learning_rate=0.03,num_leaves=31,min_child_samples=50,subsample=0.8,subsample_freq=1,colsample_bytree=0.7,verbose=-1)
        m.fit(sub.loc[tr,cols],sub.y[tr]); p[~tr.values]=m.predict_proba(sub.loc[~tr,cols])[:,1]
    return p
def top10(y,p): k=int(len(p)*0.1); return y[np.argsort(-p)[:k]].sum()/y.sum()
out=[]
for yr in [None]+sorted(d.year.unique()):
    sub=(d if yr is None else d[d.year==yr]).reset_index(drop=True)
    for name,cols in sets.items():
        p=cv(cols,sub); auc=roc_auc_score(sub.y,p)
        # block bootstrap CI of gain vs '+S2-like' filled later
        out.append(dict(season='all' if yr is None else yr,set=name,cells=len(sub),burn_rate=sub.y.mean(),auc=auc,top10=top10(sub.y.values,p)))
        sub['p_'+name]=p
    if yr is None:
        base=sub['p_+S2-like'].values
        for nm in ['+S2+Pixxel-like VNIR','+S2+full EMIT']:
            g=[]; bl=sub.blk.values; ub=np.unique(bl)
            for b in range(200):
                s=rng.choice(ub,len(ub)); idx=np.concatenate([np.where(bl==x)[0] for x in s])
                g.append(roc_auc_score(sub.y.values[idx],sub['p_'+nm].values[idx])-roc_auc_score(sub.y.values[idx],base[idx]))
            print(nm,'AUC gain over +S2-like, 95% CI',np.percentile(g,[2.5,50,97.5]).round(4))
        # what the SWIR litter index tracks
        print(sub[['h_cai','h_lca','h_ndli','s2_ndti','s2_ndvi','lc_teak','lc_sal','lc_forest','yrs_burnt','y']].corr(method='spearman')[['h_cai','h_lca','s2_ndti','y']].round(2))
        sub.to_parquet('cells_scored.parquet')
r=pd.DataFrame(out); print(r.round(3).to_string()); r.to_csv('results.csv',index=False)
