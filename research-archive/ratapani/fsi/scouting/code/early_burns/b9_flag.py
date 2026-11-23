"""Likely-control-burn flag on burn-day clusters, shares by window and division, + 'Jan-like' classifier mixture for 15Feb-15Mar."""
import pandas as pd, numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
W='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r15_firms_nd/'
c=pd.read_parquet(W+'clusters2.parquet')
# recurrent early-burn site: 0.005 deg cell with Jan-14Feb clusters in >=3 seasons (excluding own season handled by >=3 incl. own)
import pyproj
lon,lat=pyproj.Transformer.from_crs(7755,4326,always_xy=True).transform(c.x.values,c.y.values)
c['cell']=(np.floor(lat/0.005)).astype(int)*100000+(np.floor(lon/0.005)).astype(int)
e=c[c.win=='1 Jan-14Feb'][['cell','season']].drop_duplicates()
tot=e.groupby('cell').size()
own=set(zip(e.cell,e.season))
c['early_site_seasons']=c.cell.map(tot).fillna(0).astype(int)-np.array([(a,b) in own for a,b in zip(c.cell,c.season)]).astype(int)  # OTHER seasons only
# rule
c['flag_core']=c.day_only & c.short & (c.n<=2) & (c.frp_max<=5)
c['flag_site']=c.early_site_seasons>=2
c['flag']=c.flag_core
c['flag_strict']=c.flag_core & c.flag_site
win=c.win
def sh(x,col): return pd.Series({'clusters':len(x),'pts':x.n.sum(),'flag_cl':x[col].mean(),'flag_pts':(x.n*x[col]).sum()/x.n.sum()})
for col in ['flag','flag_strict']:
    print(col); print(c.groupby('win').apply(sh,col=col).round(3).to_string())
# per division table
rows=[]
for dv,g in c.groupby('Division'):
    r={'Division':dv}
    for w,lab in [('1 Jan-14Feb','jan'),('2 15Feb-15Mar','feb15mar15'),('3 16Mar-May','marmay')]:
        q=g[g.win==w]; r[f'{lab}_pts']=q.n.sum(); r[f'{lab}_flag_pts']=(q.n*q.flag).sum()/max(q.n.sum(),1); r[f'{lab}_strict_pts']=(q.n*q.flag_strict).sum()/max(q.n.sum(),1)
    rows.append(r)
D=pd.DataFrame(rows).set_index('Division')
D['feb15mar15_excess']=(D.feb15mar15_flag_pts-D.marmay_flag_pts).clip(lower=0)
D['est_ctrl_pts_feb15mar15']=(D.feb15mar15_excess*D.feb15mar15_pts).round()
# classifier: Jan-14Feb (1) vs 16Mar-May (0), date-free features
F=['day_only','short','n','nsat','frp_max','near_track','near_road','near_edge','lin','early_site_seasons']
X=c[F].astype(float).fillna(0)
tr=c.win.isin(['1 Jan-14Feb','3 16Mar-May'])
y=(c.win=='1 Jan-14Feb').astype(int)
# balance by subsampling MarMay; train on even seasons, score odd seasons, and vice versa
c['p_jan']=np.nan
for par in (0,1):
    m=tr&(c.season%2==par)
    clf=HistGradientBoostingClassifier(max_iter=200,learning_rate=0.05,class_weight='balanced').fit(X[m],y[m])
    o=c.season%2!=par; c.loc[o,'p_jan']=clf.predict_proba(X[o])[:,1]
from sklearn.metrics import roc_auc_score
mm=tr; print('AUC Jan vs MarMay (cross-season)',roc_auc_score(y[mm],c.p_jan[mm]))
# mixture: fraction pi of 15Feb-15Mar that is Jan-like, fit on histogram of p_jan
bins=np.linspace(0,1,21)
hj=np.histogram(c.p_jan[c.win=='1 Jan-14Feb'],bins,density=True)[0]
hm=np.histogram(c.p_jan[c.win=='3 16Mar-May'],bins,density=True)[0]
def mix(sel):
    h=np.histogram(c.p_jan[sel],bins,density=True)[0]
    pis=np.linspace(0,1,101); err=[((h-(p*hj+(1-p)*hm))**2).sum() for p in pis]; return pis[int(np.argmin(err))]
for w in ['0 Oct-Dec','1 Jan-14Feb','2 15Feb-15Mar','3 16Mar-May','4 Jun']: print('mixture pi Jan-like',w,mix(c.win==w))
# weekly within 15Feb-15Mar
c['wk']=((c.date.dt.month-2)*31+c.date.dt.day-15)//7
for k in range(5): print('week from 15Feb',k,mix((c.win=='2 15Feb-15Mar')&(c.wk==k)), 'flag pts', round(((c.n*c.flag)[(c.win=='2 15Feb-15Mar')&(c.wk==k)]).sum()/c.n[(c.win=='2 15Feb-15Mar')&(c.wk==k)].sum(),3))
pis=[]
for dv,g in c.groupby('Division'):
    s=(c.Division==dv)&(c.win=='2 15Feb-15Mar')
    D.loc[dv,'mix_janlike_feb15mar15']=mix(s) if s.sum()>=150 else np.nan
D=D.round(3); D.to_csv('division_flag_shares.csv')
print(D.sort_values('jan_pts',ascending=False).head(30).to_string())
print('MP totals: feb15mar15 pts',D.feb15mar15_pts.sum(),'est ctrl excess pts',D.est_ctrl_pts_feb15mar15.sum())
c.to_parquet(W+'clusters3.parquet')
