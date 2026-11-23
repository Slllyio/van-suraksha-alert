"""Weekly flag shares after 15 Feb, implied precision of the flag, and cost of dropping; per-division summaries."""
import pandas as pd, numpy as np
W='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r15_firms_nd/'
c=pd.read_parquet(W+'clusters3.parquet')
c['m']=c.date.dt.month; c['dd']=c.date.dt.day
doy=c.date.dt.dayofyear; c['wk15']=np.where((doy>=46)&(c.m<=6),(doy-46)//7,-1)  # week index from 15 Feb (doy 46)
season_pts=c[(doy>=46)&(c.date<=pd.to_datetime(c.season.astype(str)+'-06-15'))].n.sum()
bg=(c.n*c.flag)[c.win=='3 16Mar-May'].sum()/c.n[c.win=='3 16Mar-May'].sum()
jan=(c.n*c.flag)[c.win=='1 Jan-14Feb'].sum()/c.n[c.win=='1 Jan-14Feb'].sum()
rows=[]
for k in range(0,8):
    q=c[c.wk15==k]; fp=(q.n*q.flag).sum()/q.n.sum()
    rows.append(dict(week=f'{k}: {pd.Timestamp(2025,2,15)+pd.Timedelta(days=7*k):%d %b}+',pts=q.n.sum(),flag_pts_share=round(fp,3),excess=round(fp-bg,3),
       flag_precision_est=round(max(fp-bg,0)/fp,2),janlike_share_upper=round(max(fp-bg,0)/(jan-bg),2),flagged_pts=int((q.n*q.flag).sum())))
R=pd.DataFrame(rows); print('background (16Mar-May) flag share',round(bg,3),'Jan share',round(jan,3)); print(R.to_string()); R.to_csv('weekly_after_15feb.csv',index=False)
print('season (15Feb-15Jun) pts',season_pts)
drop=c[(c.wk15.between(0,2))&c.flag]; print('drop rule (flag, 15 Feb-7 Mar): clusters',len(drop),'pts',drop.n.sum(),'share of season pts',round(drop.n.sum()/season_pts,4))
est_ctrl=sum(max(r.flag_pts_share-bg,0)*r.pts for r in R.itertuples() if r.Index<=2); print('est control pts removed',round(est_ctrl),'est wildfire pts lost',round(drop.n.sum()-est_ctrl))
# upper-bound contamination: Jan-like share x pts, weeks 0-3
ub=sum(r.janlike_share_upper*r.pts for r in R.itertuples() if r.Index<=3); print('upper-bound control pts 15Feb-14Mar',round(ub),'share of season',round(ub/season_pts,4))
# per-division Jan flag share summary
D=pd.read_csv('division_flag_shares.csv',index_col=0)
q=D[D.jan_pts>=100]; print('divisions with >=100 Jan pts',len(q),'median Jan flag share',q.jan_flag_pts.median(),'IQR',q.jan_flag_pts.quantile([.25,.75]).values)
# implied later burns avoided
e=c[c.win.isin(['0 Oct-Dec','1 Jan-14Feb'])].groupby(['cell','season']).size(); print('early cell-seasons',len(e),'implied later cell-burns avoided at -0.041',round(len(e)*0.041))
l=c[c.win.isin(['2 15Feb-15Mar','3 16Mar-May','4 Jun'])].groupby(['cell','season']).size(); print('later cell-seasons',len(l))
