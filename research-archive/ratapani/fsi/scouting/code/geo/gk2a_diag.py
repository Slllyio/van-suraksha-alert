import sys,os,glob,numpy as np,pandas as pd
D=sys.argv[1]; fs=sorted(glob.glob(D+'/gk2a_*.npz'))
ts=pd.to_datetime([os.path.basename(f)[5:17] for f in fs],format='%Y%m%d%H%M')
T38=np.stack([np.load(f)['sw038'] for f in fs]); T11=np.stack([np.load(f)['ir112'] for f in fs]); dT=T38-T11
slot=(ts.hour*60+ts.minute).values
A=np.full_like(dT,np.nan); S=np.full_like(dT,np.nan)
for s in np.unique(slot):
    m=slot==s; md=np.nanmedian(dT[m],0); A[m]=dT[m]-md; S[m]=1.4826*np.nanmedian(np.abs(dT[m]-md),0)
A-=np.nanmedian(A,axis=(1,2),keepdims=True)
v=pd.read_csv(D+'/../firms_box_2024.csv',parse_dates=['t']); v=v[v.src!='MODIS']
v['pass']=v.t.dt.floor('30min'); g=v.groupby(['pass','li','ci']).agg(frp=('frp','sum'),t=('t','median'),dn=('daynight','first')).reset_index()
tarr=ts.values; rows=[]
for r in g.itertuples():
    j=np.argmin(np.abs(tarr-np.datetime64(r.t)))
    if abs(tarr[j]-np.datetime64(r.t))>np.timedelta64(20,'m'): continue
    for sh in [(0,0),(-1,0),(1,0),(0,-1),(0,1)]:
        li,ci=r.li+sh[0],r.ci+sh[1]
        if 0<=li<A.shape[1] and 0<=ci<A.shape[2]: rows.append((r.dn,r.frp,sh,A[j,li,ci],S[j,li,ci],np.nanmax(A[j,max(li-1,0):li+2,max(ci-1,0):ci+2])))
d=pd.DataFrame(rows,columns=['dn','frp','sh','A','S','Amax3'])
for dn in 'DN':
  for lo,hi in [(0,10),(10,30),(30,100),(100,1e9)]:
    s=d[(d.dn==dn)&(d.frp>=lo)&(d.frp<hi)]
    print(dn,lo,hi,'n',len(s)//5, ' | '.join('%s A=%.2f'%(str(sh),s[s.sh==sh].A.median()) for sh in [(0,0),(-1,0),(1,0),(0,-1),(0,1)]), '| median S %.2f'%s.S.median(), 'Amax3 med %.2f'%s[s.sh==(0,0)].Amax3.median())
hr=ts.hour+5.5
for h in [2,8,11,13,14,16,18,20,22]:
    m=((ts+pd.Timedelta('5.5h')).hour==h); print('IST hour',h,'median per-pixel MAD S %.2f K; spatial sd of A %.2f'%(np.nanmedian(S[m]),np.nanmedian(np.nanstd(A[m],axis=(1,2)))))
