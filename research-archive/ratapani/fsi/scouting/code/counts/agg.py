import pandas as pd, numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
D='/mnt/project-files/ratapani/'
p=pd.read_parquet(D+'scoring/pipeline_lean_pred_loso_2017_24.parquet')
e=pd.read_parquet(D+'fsi/scouting/data/exp_preds.parquet',columns=['season','date','cell_id','pos'])
x=p.merge(e,on=['season','date','cell_id'])
cb=pd.read_csv(D+'beats/cell_beat.csv'); x=x.merge(cb,on='cell_id',how='left')
print('rows',len(x),'pos rate',x.pos.mean(),'beats',x.beat_uid.nunique(),'missing beat',x.beat_uid.isna().mean())
print('cell-day AUC', roc_auc_score(x.pos,x.pipeline_lean))
x['week']=((x.date-pd.to_datetime(x.season.astype(str)+'-02-01')).dt.days//7)
# baseline: no-weather, beat x season-week climatology from other seasons is complex; use cell mean prediction per season (removes day variation)
x['cellmean']=x.groupby(['season','cell_id']).pipeline_lean.transform('mean')
x['daymean']=x.groupby(['season','date']).pipeline_lean.transform('mean')
def agg(keys,name):
    g=x.groupby(keys).agg(pred=('pipeline_lean','sum'),obs=('pos','sum'),n=('pos','size'),cm=('cellmean','sum')).reset_index()
    g=g[g.n>=5]
    r_all=spearmanr(g.pred,g.obs).correlation
    # within-season
    rs=[spearmanr(gg.pred,gg.obs).correlation for s,gg in g.groupby('season') if gg.obs.nunique()>1]
    rate_r=spearmanr(g.pred/g.n,g.obs/g.n).correlation
    any_auc=roc_auc_score(g.obs>0,g.pred/g.n) if 0<(g.obs>0).mean()<1 else np.nan
    # busy = top 10% of units by observed rate within season
    g['rate']=g.obs/g.n
    g['busy']=g.groupby('season').rate.transform(lambda v: v>=v.quantile(0.9)) & (g.obs>0)
    busy_auc=roc_auc_score(g.busy,g.pred/g.n)
    busy_auc_cm=roc_auc_score(g.busy,g.cm/g.n)
    # hit rate: flag top10% predicted per season
    g['flag']=g.groupby('season').pred.transform(lambda v: v>=v.quantile(0.9))
    g['pr']=g.pred/g.n
    g['flagr']=g.groupby('season').pr.transform(lambda v: v>=v.quantile(0.9))
    hit=(g.flagr&g.busy).sum()/g.busy.sum(); far=(g.flagr&~g.busy).sum()/g.flagr.sum()
    print(f"{name:22s} units={len(g):7d} P(obs>0)={(g.obs>0).mean():.2f} rho_count={r_all:.2f} rho_rate={rate_r:.2f} rho_within_season={np.nanmean(rs):.2f} AUC_any={any_auc:.3f} AUC_busy10={busy_auc:.3f} (no-weather {busy_auc_cm:.3f}) POD10={hit:.2f} FAR10={far:.2f}")
agg(['season','date','cell_id'],'cell-day')  if False else None
agg(['season','date','beat_uid'],'beat-day')
agg(['season','week','beat_uid'],'beat-week')
x['range']=x.beat_uid.str[:7]
agg(['season','date','range'],'range-day')
agg(['season','week','range'],'range-week')
agg(['season','date'],'sanctuary-day')
agg(['season','week'],'sanctuary-week')
