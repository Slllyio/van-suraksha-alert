"""Two-way fixed-effect linear probability: later_burn ~ early_burn + cell FE + division x season FE (alternating projections).
Also Poisson-style ratio check: observed/expected with multiplicative cell x divseason expectation."""
import pandas as pd, numpy as np
W='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r15_firms_nd/'
c=pd.read_parquet(W+'clusters3.parquet'); c=c[c.season.between(2014,2026)]
c['early']=c.win.isin(['0 Oct-Dec','1 Jan-14Feb']); c['later']=c.win.isin(['2 15Feb-15Mar','3 16Mar-May','4 Jun'])
c['early_flag']=c.early&c.flag; c['early_big']=c.early&~c.flag
cs=c.groupby(['cell','season']).agg(Division=('Division','first'),early=('early','any'),early_flag=('early_flag','any'),early_big=('early_big','any'),later=('later','any')).reset_index()
cells=cs.groupby('cell').Division.first()
full=pd.MultiIndex.from_product([cells.index,range(2014,2027)],names=['cell','season']).to_frame(index=False)
full['Division']=full.cell.map(cells)
full=full.merge(cs.drop(columns='Division'),on=['cell','season'],how='left').fillna(False)
full['ds']=full.Division+'_'+full.season.astype(str)
TR=['Kanha Tiger Reserve','Satpura_TR','Kuno_Palpur','PTR MP','BTR','Panna_TR','SANJAY_DUBRI','Noradehi','Madhav_National_Park','Obedullahganj']
def twfe(f,xs,y='later',it=30):
    Z=f[[y]+xs].astype(float).copy()
    for _ in range(it):
        Z=Z-Z.groupby(f.cell.values).transform('mean'); Z=Z-Z.groupby(f.ds.values).transform('mean')
    X=Z[xs].values; Y=Z[y].values
    b=np.linalg.lstsq(X,Y,rcond=None)[0]
    # cluster-robust SE by cell
    e=Y-X@b; XtX=np.linalg.inv(X.T@X); g=pd.DataFrame(X*e[:,None]).groupby(f.cell.values).sum().values
    V=XtX@(g.T@g)@XtX; return b,np.sqrt(np.diag(V))
res=[]
for nm,sel in [('all MP',slice(None)),('reserves',full.Division.isin(TR)),('other',~full.Division.isin(TR))]:
    f=full[sel] if not isinstance(sel,slice) else full
    f=f.reset_index(drop=True)
    for xs in (['early'],['early_flag','early_big']):
        b,se=twfe(f,xs)
        for k,bb,ss in zip(xs,b,se): res.append(dict(sample=nm,term=k,coef=round(bb,4),se=round(ss,4),base_later=round(f.later.mean(),4),rel=round(bb/f.later.mean(),3)))
R=pd.DataFrame(res); print(R.to_string()); R.to_csv('later_odds_twfe.csv',index=False)
# by later window: does effect fade? outcome 15Feb-15Mar vs 16Mar-May
c['l1']=c.win=='2 15Feb-15Mar'; c['l2']=c.win=='3 16Mar-May'
cs2=c.groupby(['cell','season']).agg(l1=('l1','any'),l2=('l2','any')).reset_index()
f=full.merge(cs2,on=['cell','season'],how='left').fillna(False)
for y in ['l1','l2']:
    b,se=twfe(f,['early'],y=y); print(y,'coef',round(b[0],4),'se',round(se[0],4),'base',round(f[y].mean(),4))
