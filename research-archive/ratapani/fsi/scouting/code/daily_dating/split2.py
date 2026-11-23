"""Windows split by real per-cell-clear extra scenes (L7 path 145; S2 scene cloud>=60), threshold clear>=0.5."""
import pandas as pd, numpy as np
P=pd.read_parquet('../r9data/extra_clear.parquet'); P['d']=pd.to_datetime(P.date)
w=pd.read_csv('/mnt/project-files/research/ratapani-burn-labels/burn_windows.csv'); w=w[w.burned==1].copy()
w['ws']=pd.to_datetime(w.window_start); w['we']=pd.to_datetime(w.window_end); w['L']=(w.we-w.ws).dt.days
for thr in [0.5,0.8]:
    E=P[P.clear>=thr]
    by={k:v for k,v in E.groupby('cell_id')}
    out=[]
    for r in w.itertuples():
        v=by.get(r.cell_id); ds=[]
        if v is not None:
            x=v[(v.d>r.ws)&(v.d<r.we)]
            ds=sorted(set(x.d)); sens=set(x.sensor)
        else: sens=set()
        cuts=[r.ws]+list(ds)+[r.we]; seg=np.diff([c.toordinal() for c in cuts])
        out.append(dict(season=r.season,L=r.L,split=len(ds)>0,ls=('ls' in sens),s2=('s2' in sens),EL=(seg**2).sum()/r.L))
    R=pd.DataFrame(out)
    print(f'--- clear>={thr}: windows {len(R)}, split {R.split.mean():.3f} (L7 {R.ls.mean():.3f}, S2 hi-cloud {R.s2.mean():.3f}); mean L {R.L.mean():.2f} -> expected {R.EL.mean():.2f}; median {R.L.median()} -> {R.EL.median():.1f}')
    print(R.groupby('season').agg(n=('L','size'),split=('split','mean'),L=('L','mean'),EL=('EL','mean')).round(3).to_string())
    print('share windows <=3 d before/after', (R.L<=3).mean().round(3),(R.EL<=3).mean().round(3))
