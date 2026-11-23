import sys, json, numpy as np, pandas as pd
sys.path.insert(0,'/home/user/vanagni')
from src.analysis import fire_occurrence as FO
from src.analysis.fwi_observed import roll_fwi
W=pd.read_parquet('weather_power.parquet'); frames=[]
for k in W.reserve.unique():
    w=W[W.reserve==k].copy(); w['date']=w.date.dt.date; w=roll_fwi(w,unit_col='reserve')
    det=pd.read_parquet(f'det_{k.replace(" ","_")}.parquet'); cnt=det.groupby(det.date.dt.date).size()
    d=w[pd.to_datetime(w.date)>=pd.Timestamp('2013-01-01')].copy()
    d['n_forest']=d.date.map(cnt).fillna(0).astype(int); d['fire_day']=d.n_forest>0
    d=FO.build_features(d); d=d[[x.month in FO.FIRE_SEASON_MONTHS for x in d.date]].reset_index(drop=True)
    d['year']=[x.year for x in d.date]; frames.append(d)
A=pd.concat(frames,ignore_index=True)
# Guna's chosen feature sets, fixed (no reselection): weather and memory
SETS={'weather (Guna features)':['ffmc','rh_pct','doy_sin','doy_cos'],'memory (Guna features)':['ffmc','rh_pct','log_nf_prev14','temp_c','dmc']}
out={}
for name,f in SETS.items():
    rows=[]
    for k in A.reserve.unique():
        for y in sorted(A.year.unique()):
            tr=A[(A.reserve!=k)&(A.year!=y)].dropna(subset=f+['fire_day']); te=A[(A.reserve==k)&(A.year==y)].dropna(subset=f+['fire_day','fwi'])
            m=FO.fit(tr,f,1.0,'fire_day'); rows.append(pd.DataFrame({'reserve':k,'year':y,'p':m.predict(te),'y':te.fire_day.values,'fwi':te.fwi.values}))
    P=pd.concat(rows)
    out[name]={k:(round(FO.auc(g.p,g.y.astype(bool)),3),round(FO.auc(g.fwi,g.y.astype(bool)),3)) for k,g in P.groupby('reserve')}
    out[name]['_pooled']=(round(FO.auc(P.p,P.y.astype(bool)),3),round(FO.auc(P.fwi,P.y.astype(bool)),3))
print(json.dumps(out,indent=1)); json.dump(out,open('pooled.json','w'))
r=json.load(open('results.json'))
for k in r:
    m=json.load(open(f'models/{k}/memory.json'))['metadata']['lead_table']; w=json.load(open(f'models/{k}/weather.json'))['metadata']['lead_table']
    print(k,'memory lagged',[round(x['auc_lagged'],3) for x in m],'perfect',[round(x['auc_perfect'],3) for x in m],'| weather lagged',[round(x['auc_lagged'],3) for x in w],'fwi lag',[round(x['auc_fwi_lagged'],3) for x in m])
