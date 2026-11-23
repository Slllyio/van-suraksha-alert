import sys, json, logging, numpy as np, pandas as pd
sys.path.insert(0,'/home/user/vanagni')
from pathlib import Path
from src.analysis import fire_occurrence as FO
from src.analysis.fwi_observed import roll_fwi
logging.basicConfig(level=logging.WARNING)
W=pd.read_parquet('weather_power.parquet')
def ap(score,label):
    o=np.argsort(-np.asarray(score)); y=np.asarray(label)[o].astype(float)
    tp=np.cumsum(y); prec=tp/np.arange(1,len(y)+1); return float((prec*y).sum()/max(y.sum(),1))
res={}
for k in W.reserve.unique():
    w=W[W.reserve==k].copy(); w['date']=w.date.dt.date
    w=roll_fwi(w,unit_col='reserve')
    det=pd.read_parquet(f'det_{k.replace(" ","_")}.parquet')
    cnt=det.groupby(det.date.dt.date).size().rename('n_forest')
    d=w[[c for c in w.columns if c not in ('n_points',)]].copy()
    d=d[(pd.to_datetime(d.date)>=pd.Timestamp('2013-01-01'))]
    d['n_forest']=d.date.map(cnt).fillna(0).astype(int); d['fire_day']=d.n_forest>0
    d=FO.build_features(d); d=d[[x.month in FO.FIRE_SEASON_MONTHS for x in d.date]].reset_index(drop=True)
    d['year']=[x.year for x in d.date]
    r={'days':len(d),'fire_days':int(d.fire_day.sum()),'base_rate':float(d.fire_day.mean())}
    md=Path(f'models/{k}'); md.mkdir(parents=True,exist_ok=True)
    for v in ('weather','memory','weekly'):
        t=FO.train_and_verify(variant=v,daily=d,model_path=md/f'{v}.json',leads=[0,1,2,3,7])
        cv=FO.cross_validate(FO.weekly_labels(d,7) if v=='weekly' else d,t['features'],1.0,t['label_col'])
        p=cv['predictions']
        r[v]={'features':t['features'],'auc':t['cv']['auc_model'],'auc_fwi':t['cv']['auc_fwi'],'brier':t['cv']['brier_model'],
              'brier_clim':t['cv']['brier_climatology'],'pr_auc':ap(p.score,p.label),'pr_auc_fwi':ap(p.fwi,p.label),
              'seasons_beat_fwi':sum(y['auc_model']>y['auc_fwi'] for y in t['cv']['by_year']),'n_seasons':len(t['cv']['by_year']),
              'by_year':[(y['test_year'],round(y['auc_model'],3),round(y['auc_fwi'],3),y['fire_days']) for y in t['cv']['by_year']],
              'lead':[(int(x['lead']),round(x.get('auc',x.get('auc_model',np.nan)),3)) for x in t['lead_table']],
              'best_cut':t['best_cut'],'best_fwi_cut':t['best_fwi_cut']}
    res[k]=r
    print(k, r['fire_days'], {v:(round(r[v]['auc'],3),round(r[v]['pr_auc'],3)) for v in ('weather','memory','weekly')}, 'fwi',round(r['weather']['auc_fwi'],3), flush=True)
json.dump(res,open('results.json','w'),indent=1,default=str)
