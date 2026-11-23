import pandas as pd, numpy as np, warnings; warnings.filterwarnings('ignore')
W='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r7code_coldstart/'
m=pd.read_parquet(W+'merged.parquet')
cs=pd.read_csv('/mnt/project-files/research/ratapani-ignition/cells_static.csv').set_index('cell_id')
m['elig']=cs.elig_ha.reindex(m.cell_id).values
r=m.pipeline_lean.groupby([m.season,m.date,m.beat]).rank('first',ascending=False); top=r<=5
for lo,hi in ((0,2),(2,5),(5,10),(10,30)):
    S=(m.elig>lo)&(m.elig<=hi)
    print('elig %d-%d ha: share of valid cell-days %.3f, of main positives %.3f, of top-5 picks %.3f, pos rate in picks %.3f'%(lo,hi,S.mean(),m.pos_main[S].sum()/m.pos_main.sum(),(top&S).sum()/top.sum(),m.pos_main[top&S].mean() if (top&S).sum() else np.nan))
# how often does a top-5 pick go to a cell with no past-only history?
print('top-5 picks in past-cold cells (2020+): %.4f'%((top&(m.np==0)&(m.season>=2020)).sum()/top[m.season>=2020].sum()))
# first-ever burns per season (past-only, since 2017)
