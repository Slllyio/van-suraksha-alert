"""Is the 70 m vs VIIRS offset a correctable bias? And does it point the way the fire is travelling?
Per visible satellite-pass (b17b clips): offset = hot-pixel centroid - centroid of that satellite's blocks (UTM 43N, m).
(1) Fixed bias: mean offset east/north with fire-bootstrap CI, split by satellite, scan width, ascending/descending (day/night).
(2) Travel direction: earlier fire = any VIIRS/MODIS alert within 2 km of the blocks, 3-48 h before the pass. Spread direction = unit vector
    from earlier-alert centroid to the current blocks' centroid. Projection of the offset on that direction (+ = hot pixels
    AHEAD of the blocks, away from burnt ground) and the angle between the two. Random direction would give projection 0
    and |angle| median 90 deg.
(3) Does a "behind the front" correction of +k m along the spread direction move blocks closer to the hot pixels?
Output: results/mp_offset_direction.json"""
import os, json, numpy as np, pandas as pd
from pyproj import Transformer
R='/mnt/project-files/research/big-fires/results'; M='/mnt/project-files/fire-alert-scars/mp/out'; CL=os.environ.get('MP_ECO_SCRATCH','/tmp/claude-0/mp_eco')+'/clips'
D=pd.read_csv(f'{R}/mp_ecostress_passes.csv',parse_dates=['t0']); V=D[D.visible==True]
A=pd.read_csv(f'{M}/mp_alert_event.csv',usecols=['latitude','longitude','acq_date','acq_time','satellite','instrument','scan','track','event_id'])
A=A.copy()   # all MP alerts: earlier looks of the same fire often carry another event id
A['t']=pd.to_datetime(A.acq_date+' '+A.acq_time.astype(int).astype(str).str.zfill(4),format='%Y-%m-%d %H%M')
to43=Transformer.from_crs('EPSG:4326','EPSG:32643',always_xy=True); A['x'],A['y']=to43.transform(A.longitude.values,A.latitude.values)
from scipy.spatial import cKDTree
TREE=cKDTree(np.c_[A.x.values,A.y.values])
rows=[]
for r in V.itertuples():
    z=np.load(f'{CL}/{r.event_id}_{r.granule}.npz'); lst=z['lst'].astype(float); clear=np.isfinite(lst)&(lst>250)&(z['cloud']==0)
    E=A[A.event_id==r.event_id]; v=E[(E.instrument=='VIIRS')&((E.t-r.t0).abs()<=pd.Timedelta(hours=1))]; g=v[v.satellite==r.sensor]
    if g.empty: continue
    dmin=np.hypot(z['x'][:,None]-v.x.values[None],z['y'][:,None]-v.y.values[None]).min(1)
    near,ring=dmin<=600,(dmin>=1500)&(dmin<=3000); bg=np.median(lst[clear&ring]); hot=(lst-bg>10)&clear&near
    hx,hy=z['x'][hot].astype(float),z['y'][hot].astype(float); bx,by=g.x.mean(),g.y.mean()
    ox,oy=hx.mean()-bx,hy.mean()-by
    nb_=A.iloc[TREE.query_ball_point([bx,by],2000)]
    pr=nb_[(nb_.t<g.t.min()-pd.Timedelta(hours=3))&(nb_.t>=g.t.min()-pd.Timedelta(hours=48))]
    # burnt-ground direction from the SAME 70 m image: fresh black ground is warm (3-10 K over background) behind the hot line
    warm=(lst-bg>=3)&(lst-bg<10)&clear&(dmin<=1500)
    wdir=(hx.mean()-z['x'][warm].mean(),hy.mean()-z['y'][warm].mean()) if warm.sum()>=10 else None
    rec=dict(event_id=r.event_id,sensor=r.sensor,scan=g.scan.mean(),hour=g.t.iloc[0].hour,nb=len(g),ox=ox,oy=oy,
             d_block=np.median(np.hypot(hx-bx,hy-by)))
    if len(pr):
        sx,sy=bx-pr.x.mean(),by-pr.y.mean(); L=np.hypot(sx,sy)
        if L>=150:
            ux,uy=sx/L,sy/L; rec.update(spread_len=L,proj=ox*ux+oy*uy,perp=-ox*uy+oy*ux,
               ang=float(np.degrees(np.arctan2(-ox*uy+oy*ux,ox*ux+oy*uy))))
            nx_=nb_[(nb_.t>g.t.max()+pd.Timedelta(hours=3))&(nb_.t<=g.t.max()+pd.Timedelta(hours=24))]
            if len(nx_):    # does the direction predict where the NEXT dots appear?
                def ang(ax,ay,cx,cy): return float(np.degrees(np.abs(np.arctan2(ax*cy-ay*cx,ax*cx+ay*cy))))
                hxm,hym=hx.mean(),hy.mean()
                rec.update(next_dist=float(np.hypot(nx_.x.mean()-bx,nx_.y.mean()-by)),next_ang_dots=ang(sx,sy,nx_.x.mean()-bx,nx_.y.mean()-by),
                           next_ang_burnt=ang(wdir[0],wdir[1],nx_.x.mean()-hxm,nx_.y.mean()-hym) if wdir is not None else np.nan,
                           next_ang_70m=ang(hxm-pr.x.mean(),hym-pr.y.mean(),nx_.x.mean()-hxm,nx_.y.mean()-hym))
            for k in (60,120,200):   # shift blocks k m along spread direction
                rec[f'd_shift{k}']=np.median(np.hypot(hx-(bx+k*ux),hy-(by+k*uy)))
    rows.append(rec)
X=pd.DataFrame(rows); X.to_csv(f'{R}/mp_offset_direction_rows.csv',index=False); rng=np.random.default_rng(0)
def boot(df,col,stat=np.mean,n=1000):
    ev=df.event_id.unique(); gg={e:df[df.event_id==e][col].values for e in ev}
    b=[stat(np.concatenate([gg[e] for e in rng.choice(ev,len(ev))])) for _ in range(n)]
    return [round(float(stat(df[col].values)),1),round(float(np.percentile(b,2.5)),1),round(float(np.percentile(b,97.5)),1)]
X['band']=pd.cut(X.scan,[0,.45,.6,9],labels=['nadir','mid','edge']); X['tod']=np.where(X.hour.between(1,13),'day','night')
out=dict(passes=len(X),fires=int(X.event_id.nunique()),note='[estimate, 95% CI by fire]; offsets in m, east/north',
  fixed_bias_all=dict(east=boot(X,'ox'),north=boot(X,'oy'),offset_length_median=round(float(np.hypot(X.ox,X.oy).median()))),
  by_satellite={s:dict(n=len(g),east=boot(g,'ox'),north=boot(g,'oy')) for s,g in X.groupby('sensor')},
  by_scan={str(s):dict(n=len(g),east=boot(g,'ox'),north=boot(g,'oy')) for s,g in X.groupby('band',observed=True)})
S=X.dropna(subset=['proj'])
out['travel_direction']=dict(passes=len(S),fires=int(S.event_id.nunique()),
  offset_along_spread_m=boot(S,'proj'),offset_across_spread_m=boot(S,'perp'),
  share_ahead=boot(S.assign(a=(S.proj>0).astype(float)),'a',np.mean),
  share_within_45deg=round(float((S.ang.abs()<=45).mean()),3),random_within_45deg=0.25,
  median_abs_angle_deg=round(float(S.ang.abs().median()),1))
out['shift_test_median_dist_m']={'no shift':round(float(S.d_block.median())),**{f'+{k} m along spread':round(float(S[f'd_shift{k}'].median())) for k in (60,120,200)}}
N=S.dropna(subset=['next_ang_dots'])
out['predict_next_dots']=dict(passes=len(N),note='angle between the travel direction and the way to the next dots (3-24 h later); random = 90 median, 25% within 45',
  dots_only=dict(median_angle=round(float(N.next_ang_dots.median()),1),within_45=round(float((N.next_ang_dots<=45).mean()),3)),
  burnt_ground_to_hot_line_same_image=dict(n=int(N.next_ang_burnt.notna().sum()),median_angle=round(float(N.next_ang_burnt.median()),1),within_45=round(float((N.next_ang_burnt<=45).mean()),3) if N.next_ang_burnt.notna().any() else None),
  using_70m_hot_pixels=dict(median_angle=round(float(N.next_ang_70m.median()),1),within_45=round(float((N.next_ang_70m<=45).mean()),3)))
F=N[N.next_dist>=700]
out['predict_next_dots']['next_dots_700m_plus']=dict(passes=len(F),dots_only_within_45=round(float((F.next_ang_dots<=45).mean()),3),
  burnt_ground_within_45=round(float((F.next_ang_burnt<=45).mean()),3),hot_70m_within_45=round(float((F.next_ang_70m<=45).mean()),3))
S2=S.assign(lb=pd.cut(S.spread_len,[150,500,1000,1e9],labels=['150-500 m','0.5-1 km','>1 km']))
out['by_spread_length']={str(k):dict(n=len(g),along=boot(g,'proj'),share_ahead=round(float((g.proj>0).mean()),2)) for k,g in S2.groupby('lb',observed=True)}
json.dump(out,open(f'{R}/mp_offset_direction.json','w'),indent=1); print(json.dumps(out,indent=1))
