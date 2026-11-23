"""Does a 500 m cell (0.005 deg) burned before 15 Feb burn less later in the same season (15 Feb-15 Jun)?
Within-cell comparison across seasons, outcome residualised on division x season rate. Also beat level."""
import pandas as pd, numpy as np
W='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r15_firms_nd/'
c=pd.read_parquet(W+'clusters3.parquet')
c=c[c.season.between(2014,2026)]
c['early']=c.win.isin(['0 Oct-Dec','1 Jan-14Feb'])
c['later']=c.win.isin(['2 15Feb-15Mar','3 16Mar-May','4 Jun'])
c['mid']=c.win.isin(['3 16Mar-May'])
cs=c.groupby(['cell','season']).agg(Division=('Division','first'),beat=('beat','first'),early=('early','any'),early_flag=('flag',lambda s: (s&c.loc[s.index,'early']).any()),
   later=('later','any'),mid=('mid','any')).reset_index()
cells=cs.groupby('cell').agg(Division=('Division','first'),beat=('beat','first'))
seasons=range(2014,2027)
full=pd.MultiIndex.from_product([cells.index,seasons],names=['cell','season']).to_frame(index=False)
full=full.merge(cells,left_on='cell',right_index=True).merge(cs.drop(columns=['Division','beat']),on=['cell','season'],how='left')
for k in ['early','early_flag','later','mid']: full[k]=full[k].fillna(False).astype(bool)
print('cell-seasons',len(full),'cells',full.cell.nunique())
out=[]
for treat in ['early','early_flag']:
  for y in ['later','mid']:
    f=full.copy()
    f['res']=f[y]-f.groupby(['Division','season'])[y].transform('mean')
    g=f.groupby('cell')
    nt=g[treat].transform('sum'); f=f[(nt>0)&(nt<13)]
    a=f.groupby(['cell',treat]).agg(res=('res','mean'),raw=(y,'mean')).unstack()
    a=a.dropna()
    d_res=(a['res'][True]-a['res'][False]); d_raw=(a['raw'][True]-a['raw'][False])
    base=a['raw'][False].mean()
    # bootstrap by cell
    rng=np.random.default_rng(0); bs=[d_res.sample(frac=1,replace=True,random_state=rng.integers(1e9)).mean() for _ in range(300)]
    # naive cross-section
    naive=full.groupby(treat)[y].mean()
    out.append(dict(treat=treat,outcome=y,cells=len(a),p_untreated_seasons_same_cells=round(base,3),raw_diff=round(d_raw.mean(),4),adj_diff=round(d_res.mean(),4),ci_lo=round(np.percentile(bs,2.5),4),ci_hi=round(np.percentile(bs,97.5),4),
                    rel_change=round(d_res.mean()/base,3),naive_treated=round(naive[True],3),naive_untreated=round(naive[False],3)))
R=pd.DataFrame(out); print(R.to_string()); R.to_csv('later_odds_cell.csv',index=False)
# same with neighbour ring outcome? beat level: share of beat cells burning later vs n early cells
b=full.groupby(['beat','Division','season']).agg(early_cells=('early','sum'),later_cells=('later','sum')).reset_index()
b['lr']=np.log1p(b.later_cells); b['le']=np.log1p(b.early_cells)
for k in ['lr','le']:
    b[k+'_w']=b[k]-b.groupby('beat')[k].transform('mean')-b.groupby(['Division','season'])[k].transform('mean')+b.groupby('Division')[k].transform('mean')
slope=np.polyfit(b.le_w,b.lr_w,1)[0]
rng=np.random.default_rng(1); beats=b.beat.unique(); bsl=[]
for _ in range(200):
    s=rng.choice(beats,len(beats)); q=b.set_index('beat').loc[s]; bsl.append(np.polyfit(q.le_w,q.lr_w,1)[0])
print('beat-season two-way demeaned elasticity of later cells on early cells',round(slope,3),'CI',np.round(np.percentile(bsl,[2.5,97.5]),3))
# per region: tiger reserves vs other
TR=['Kanha Tiger Reserve','Satpura_TR','Kuno_Palpur','PTR MP','BTR','Panna_TR','SANJAY_DUBRI','Noradehi','Madhav_National_Park','Obedullahganj']
for nm,sel in [('reserves',full.Division.isin(TR)),('other',~full.Division.isin(TR))]:
    f=full[sel].copy(); f['res']=f['later']-f.groupby(['Division','season'])['later'].transform('mean')
    nt=f.groupby('cell').early.transform('sum'); f=f[(nt>0)&(nt<13)]
    a=f.groupby(['cell','early']).res.mean().unstack().dropna(); print(nm,'cells',len(a),'adj diff',round((a[True]-a[False]).mean(),4),'base',round(f[~f.early].later.mean(),3))
