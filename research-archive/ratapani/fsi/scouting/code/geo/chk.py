import sys,os,numpy as np,pandas as pd
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from geos import ll2lc
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/geo_r8/'
z=np.load(D+'gk2a_2024/gk2a_202403250800.npz'); L0,C0=int(z['L0']),int(z['C0'])
dT=z['sw038']-z['ir112']
from numpy.lib.stride_tricks import sliding_window_view as sw
pad=7; P=np.pad(dT,pad,mode='edge'); med=np.median(sw(P,(15,15)),axis=(-1,-2)); an=dT-med
v=pd.concat([pd.read_csv(D+f'firms/{f}_2024_India.csv') for f in ['viirs-snpp','viirs-jpss1']])
v=v[(v.acq_date=='2024-03-25')&(v.daynight=='D')&v.latitude.between(21,25)&v.longitude.between(75,81)]
l,c=ll2lc(v.latitude.values,v.longitude.values); v['li']=np.round(l).astype(int)-L0; v['ci']=np.round(c).astype(int)-C0
for sh in [(0,0),(-1,0),(1,0),(0,-1),(0,1)]:
    li=(v.li+sh[0]).clip(0,an.shape[0]-1); ci=(v.ci+sh[1]).clip(0,an.shape[1]-1)
    print('shift',sh,'mean anomaly at VIIRS pixels %.2f K; median %.2f'%(np.nanmean(an[li,ci]),np.nanmedian(an[li,ci])))
print('all pixels mean %.2f sd %.2f'%(np.nanmean(an),np.nanstd(an)), 'n VIIRS',len(v))
g=v.groupby(['li','ci']).frp.sum().sort_values(ascending=False).head(10)
for (li,ci),f in g.items(): print(li,ci,'VIIRS sumFRP %.0f'%f,'GK2A anomaly %.1f'%an[li,ci], 'local max in 3x3 %.1f'%np.nanmax(an[max(li-1,0):li+2,max(ci-1,0):ci+2]))
