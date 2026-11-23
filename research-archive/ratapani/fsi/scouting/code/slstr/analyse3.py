import pandas as pd, numpy as np, json
from scipy.spatial import cKDTree
S='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/slstr_out/'
G=json.load(open('/mnt/project-files/ratapani/grid_500m.geojson'))['features']
cc=np.array([np.array(g['geometry']['coordinates'][0][:4]).mean(0) for g in G]); cid=np.array([g['properties']['cell_id'] for g in G])
def xy(lon,lat): return np.c_[(lon-77.85)*102.5,(lat-23.0)*111.0]
ct=cKDTree(xy(cc[:,0],cc[:,1]))
def incell(lon,lat,r=0.4): d,i=ct.query(xy(lon,lat)); return np.where(d<=r,cid[i],-1)
f=pd.read_csv(S+'slstr_frp_fires.csv'); f['t']=pd.to_datetime('2000-01-01')+pd.to_timedelta(f.time,unit='us'); f['ist']=f.t+pd.Timedelta('5.5h')
f['cell']=incell(f.longitude.values,f.latitude.values); f=f[f.cell>=0].copy(); f['slot']=np.where(f.ist.dt.hour.between(8,13),'morning','night'); f['yr']=f.ist.dt.year
a=pd.read_csv('/mnt/project-files/fire-alert-scars/alert_scar_lookup.csv'); a['t']=pd.to_datetime(a.acq_date)+pd.to_timedelta(a.acq_time.fillna(0).astype(int)//100,unit='h')+pd.to_timedelta(a.acq_time.fillna(0).astype(int)%100,unit='m'); a['ist']=a.t+pd.Timedelta('5.5h')
a=a[a.t>='2020-12-01']
print('SLSTR in-grid',len(f),'FIRMS alerts ref',len(a), a.t.max())
tv=cKDTree(xy(a.longitude.values,a.latitude.values)); vt=a.ist.values
def frac(X,T,h0,h1,r=1.0):
    o=[]
    for i in range(len(X)):
        idx=tv.query_ball_point(X[i],r); dt=(vt[idx]-T[i])/np.timedelta64(1,'h') if idx else np.array([]); o.append(bool(((dt>=h0)&(dt<=h1)).any()))
    return np.array(o)
X=xy(f.longitude.values,f.latitude.values); T=f.ist.values
f['firms12']=frac(X,T,-12,12); f['prev15']=frac(X,T,-15,0); f['next16']=frac(X,T,0,16)
rng=np.random.default_rng(0); k=rng.integers(0,len(cc),len(f)); f['ctrl12']=frac(xy(cc[k,0],cc[k,1]),T,-12,12)
bw=pd.read_csv('/mnt/project-files/research/ratapani-burn-labels/burn_windows.csv',parse_dates=['window_start','window_end']); b=bw[bw.burned==1][['cell_id','window_start','window_end']]
f['d']=f.ist.dt.normalize(); f['rc']=cid[k]
def inscar(col):
    m=f[[col,'d']].reset_index().merge(b,left_on=col,right_on='cell_id'); m=m[(m.d>=m.window_start-pd.Timedelta('1D'))&(m.d<=m.window_end)]; return f.index.isin(m['index'])
f['scar']=inscar('cell'); f['ctrlscar']=inscar('rc')
print('burn windows max season', bw.season.max())
f['strong']=(f.FRP_MWIR>20)
agg=dict(n=('cell','size'),firms12=('firms12','mean'),ctrl12=('ctrl12','mean'),scar=('scar','mean'),ctrlscar=('ctrlscar','mean'))
print(f.groupby('slot').agg(**agg).round(3)); print(f.groupby(['slot','yr']).agg(**agg).round(2))
print(f.groupby(['slot','firms12']).agg(n=('cell','size'),scar=('scar','mean')).round(3))
print('morning strong >20MW',f[f.slot=='morning'].groupby('strong').agg(**agg).round(2))
# night: new fires vs carry-on
n=f[f.slot=='night']; print('night: FIRMS in prev 15h',n.prev15.mean().round(3),'| no FIRMS before but FIRMS in next 16h (first sighting at 22:00)',(~n.prev15&n.next16).mean().round(3))
# per fire-day value: FIRMS fire cell-days that SLSTR sees first
f.to_csv(S+'slstr_ingrid_matched_all.csv',index=False)
