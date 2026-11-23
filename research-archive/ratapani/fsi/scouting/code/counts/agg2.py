import pandas as pd, numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score, brier_score_loss
D='/mnt/project-files/ratapani/'
p=pd.read_parquet(D+'scoring/pipeline_lean_pred_loso_2017_24.parquet')
e=pd.read_parquet(D+'fsi/scouting/data/exp_preds.parquet',columns=['season','date','cell_id','pos'])
x=p.merge(e,on=['season','date','cell_id'])
cb=pd.read_csv(D+'beats/cell_beat.csv'); x=x.merge(cb,on='cell_id',how='left')
x['range']=x.beat_uid.str[:7]; print('ranges',x.range.nunique())
x['doy']=(x.date-pd.to_datetime(x.season.astype(str)+'-02-01')).dt.days
x['week']=x.doy//7
def clim(g,keys,unit):
    # LOSO climatology of rate: mean over other seasons of rate for same unit-key (and same week)
    out=np.zeros(len(g))
    for s in g.season.unique():
        tr=g[g.season!=s]; te=g.season==s
        if unit:
            # multiplicative: unit factor * week shape
            wk=tr.groupby('wk').apply(lambda d: d.obs.sum()/d.n.sum())
            uf=tr.groupby(unit).apply(lambda d: d.obs.sum()/d.n.sum())/ (tr.obs.sum()/tr.n.sum())
            out[te.values]=g.loc[te,'wk'].map(wk).fillna(tr.obs.sum()/tr.n.sum()).values*g.loc[te,unit].map(uf).fillna(1).values
        else:
            wk=tr.groupby('wk').apply(lambda d: d.obs.sum()/d.n.sum())
            out[te.values]=g.loc[te,'wk'].map(wk).fillna(tr.obs.sum()/tr.n.sum()).values
    return out
def run(keys,name,unit):
    g=x.groupby(keys).agg(pred=('pipeline_lean','sum'),obs=('pos','sum'),n=('pos','size'),wk=('week','first')).reset_index()
    g=g[g.n>=5].reset_index(drop=True)
    g['rate']=g.obs/g.n; g['pr']=g.pred/g.n
    g['clim']=clim(g,keys,unit)
    g['busy']=g.groupby('season').rate.transform(lambda v: v>=v.quantile(0.9))&(g.obs>0)
    r=lambda a: spearmanr(g[a],g.rate).correlation
    a=lambda c: roc_auc_score(g.busy,g[c])
    # Brier skill score for busy using isotonic-free logistic on pr? simple: BSS of climatological freq
    print(f"{name:15s} n={len(g):6d} rho(model)={r('pr'):.2f} rho(clim)={r('clim'):.2f} AUCbusy model={a('pr'):.3f} clim={a('clim'):.3f}")
    return g
run(['season','date','beat_uid'],'beat-day','beat_uid')
run(['season','week','beat_uid'],'beat-week','beat_uid')
run(['season','date','range'],'range-day','range')
run(['season','week','range'],'range-week','range')
run(['season','date'],'sanctuary-day',None)
run(['season','week'],'sanctuary-week',None)
# VIIRS sanctuary-day
v=pd.read_parquet(D+'fsi/scouting/data/viirs_cells.parquet',columns=['date','cell_id','reserve','ev'])
v=v[v.reserve=='Ratapani']
vd=v.groupby('date').size()
sd=x.groupby(['season','date']).agg(pred=('pipeline_lean','mean')).reset_index()
sd['v12']=[vd.reindex(pd.date_range(d+pd.Timedelta(days=1),d+pd.Timedelta(days=2))).fillna(0).sum() for d in sd.date]
sd['v0']=[vd.get(d,0) for d in sd.date]
print('VIIRS sanctuary: rho(pred_mean, VIIRS dets t+1..t+2)=%.2f ; rho(persistence VIIRS t, t+1..t+2)=%.2f'%(spearmanr(sd.pred,sd.v12).correlation, spearmanr(sd.v0,sd.v12).correlation))
sd['busy']=sd.groupby('season').v12.transform(lambda s: s>=s.quantile(0.9))
print('busy(top10%% VIIRS 2-day) AUC model=%.3f persistence=%.3f'%(roc_auc_score(sd.busy,sd.pred),roc_auc_score(sd.busy,sd.v0)))
# events-based new ignitions
ev=pd.read_parquet(D+'fsi/scouting/data/events.parquet')
ed=ev.groupby(ev.start.dt.normalize()).size()
sd['e12']=[ed.reindex(pd.date_range(d+pd.Timedelta(days=1),d+pd.Timedelta(days=2))).fillna(0).sum() for d in sd.date]
print('rho(pred, new VIIRS events t+1..t+2)=%.2f'%spearmanr(sd.pred,sd.e12).correlation)
print('mean VIIRS dets per 2-day', sd.v12.mean(), 'share of 2-day windows with 0', (sd.v12==0).mean())
from scipy.stats import rankdata
sd['v_last3']=[vd.reindex(pd.date_range(d-pd.Timedelta(days=2),d)).fillna(0).sum() for d in sd.date]
for name,score in [('persist3',sd.v_last3),('rank(pred)+rank(persist3)',rankdata(sd.pred)+rankdata(sd.v_last3))]:
    print(name,'AUCbusy=%.3f rho=%.2f'%(roc_auc_score(sd.busy,score),spearmanr(score,sd.v12).correlation))
# NB GLM of 2-day count: log(mu)=a+b*logit(pred)+c*log1p(v_last3), LOSO, coverage of 90% PI

from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import nbinom
def nbfit(X,y):
    def nll(t):
        b=t[:-1]; a=np.exp(t[-1]); mu=np.exp(X@b); n=1/a
        return -np.sum(gammaln(y+n)-gammaln(n)-gammaln(y+1)+n*np.log(n/(n+mu))+y*np.log(mu/(n+mu)))
    t0=np.zeros(X.shape[1]+1); t0[0]=np.log(y.mean()+.1)
    r=minimize(nll,t0,method='L-BFGS-B'); return r.x
sd['lp']=np.log(sd.pred/(1-sd.pred)); sd['lv']=np.log1p(sd.v_last3)
for cols in (['lp'],['lv'],['lp','lv']):
    cov=[];mae=[];maec=[]
    for s_ in sd.season.unique():
        tr=sd[sd.season!=s_]; te=sd[sd.season==s_]
        X=np.c_[np.ones(len(tr)),tr[cols].values]; t=nbfit(X,tr.v12.values)
        mu=np.exp(np.c_[np.ones(len(te)),te[cols].values]@t[:-1]); n=1/np.exp(t[-1]); pp=n/(n+mu)
        lo=nbinom.ppf(0.05,n,pp); hi=nbinom.ppf(0.95,n,pp)
        cov+=list((te.v12>=lo)&(te.v12<=hi)); mae+=list(abs(te.v12-mu)); maec+=list(abs(te.v12-tr.v12.mean()))
    print(cols,'NB LOSO 90%% PI coverage=%.2f MAE=%.2f (constant-mean MAE=%.2f) alpha=%.2f coefs=%s'%(np.mean(cov),np.mean(mae),np.mean(maec),np.exp(t[-1]),np.round(t[:-1],2)))
