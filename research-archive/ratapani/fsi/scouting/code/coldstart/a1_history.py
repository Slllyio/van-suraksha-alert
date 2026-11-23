import pandas as pd, numpy as np
b=pd.read_csv('/mnt/project-files/research/ratapani-burn-labels/burn_windows.csv')
cs=b[b.burned==1].groupby(['season','cell_id']).burned_ha.sum().unstack(0).reindex(range(3614)).fillna(0)
B=(cs>0).astype(int)
print('cells burned per season', B.sum().to_dict())
print('cells never burned 2017-2026', int((B.sum(1)==0).sum()))
print('distribution of #seasons burned (of 10):', B.sum(1).value_counts().sort_index().to_dict())
for Y in range(2018,2027):
    prior=B.loc[:,[s for s in B.columns if s<Y]].sum(1)
    nh=prior==0
    print(Y,'no-history cells',int(nh.sum()),'of which burn in Y',int(B.loc[nh,Y].sum()), 'rate %.2f'%(B.loc[nh,Y].mean() if nh.sum() else np.nan), '| history cells rate %.2f'%B.loc[~nh,Y].mean())
