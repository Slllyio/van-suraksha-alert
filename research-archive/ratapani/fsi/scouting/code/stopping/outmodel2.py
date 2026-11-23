import pandas as pd, numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, brier_score_loss
R=pd.read_csv('steps_1000_48.csv',parse_dates=['t']); F=pd.read_csv('fires_1000_48.csv',index_col=0)
R['yr']=R.fire.map(F.yr); R['ld']=(R.t+pd.Timedelta(hours=5.5)).dt.normalize()
W=pd.read_parquet('/mnt/project-files/ratapani/weather_power_daily.parquet'); W['date']=pd.to_datetime(W.date); W=W.set_index('date').sort_index()
W['rain2']=(W.precip_mm>=2).astype(int); g=W.rain2.cumsum()
last=W.index.to_series().where(W.rain2==1).ffill(); W['dsr']=(W.index.to_series()-last).dt.days.clip(upper=120)
W['rh_next']=W.rh_pct.shift(-1); W['p_next']=W.precip_mm.shift(-1)
R=R.join(W[['rh_pct','temp_c','wind_kmh','precip_mm','dsr','rh_next','p_next']],on='ld')
R['doy']=R.ld.dt.dayofyear
rows=[]
for r in R.itertuples():
    for k in range(0,9):
        if r.redet and k>r.missed: break
        if (not r.redet) and k>r.k_avail: break
        rows.append((r.yr,k,np.log1p(r.frp),np.log1p(r.frp_cum),r.dn=='N',r.hour,min(r.npass_so_far,8),r.rh_pct,r.temp_c,r.wind_kmh,r.precip_mm,r.dsr,r.rh_next,r.p_next,r.doy,int(r.redet)))
X=pd.DataFrame(rows,columns=['yr','k','lfrp','lfrpc','night','hour','np','rh','temp','wind','pr','dsr','rhn','prn','doy','y'])
base=['k','lfrp','lfrpc','night','hour','np']; wx=base+['rh','temp','wind','pr','dsr','rhn','prn','doy']
for name,feats in [('fire-only',base),('fire+weather',wx)]:
    Z=[]
    for test in sorted(X.yr.unique()):
        tr,te=X[X.yr!=test],X[X.yr==test]
        m=HistGradientBoostingClassifier(max_iter=200,learning_rate=0.05,max_leaf_nodes=15).fit(tr[feats],tr.y)
        Z.append(te.assign(p=m.predict_proba(te[feats])[:,1]))
    Z=pd.concat(Z)
    print(name,'AUC %.3f Brier %.4f'%(roc_auc_score(Z.y,Z.p),brier_score_loss(Z.y,Z.p)))
    if name=='fire-only':
        # survival-ish summary: P(seen again) predicted after 1 silent pass by FRP band and day/night
        s=Z[Z.k==1]; print(s.groupby([pd.cut(np.expm1(s.lfrpc),[0,5,15,50,1e4]),'night'],observed=True).agg(n=('y','size'),obs=('y','mean'),pred=('p','mean')).round(3))
# rain effect
e=X[X.k==0]; print('P(seen again) next-day rain>=2mm: %.3f (n=%d) vs dry: %.3f'%(e[e.prn>=2].y.mean(),(e.prn>=2).sum(),e[e.prn<2].y.mean()))
print('by days since rain:',e.groupby(pd.cut(e.dsr,[-1,3,10,30,60,121]),observed=True).y.agg(['mean','size']).round(3).to_dict())
print('by month:',e.groupby(((e.doy-1)//30.5+1).astype(int)).y.agg(['mean','size']).round(3).to_dict())
