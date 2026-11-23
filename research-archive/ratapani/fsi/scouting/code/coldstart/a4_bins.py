import pandas as pd, numpy as np
D=pd.read_csv('/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r7code_coldstart/nohist_profile.csv')
def tab(c,bins):
    g=D.groupby(pd.cut(D[c],bins)).y.agg(['size','sum','mean']); print(c); print(g.round(3).to_string())
tab('elig_ha',[-1,2,5,10,15,20,26]); tab('fr_thisseason1',[-0.01,0,0.25,0.5,0.75,1]); tab('wc_crop',[-0.01,0.05,0.2,0.5,1]); tab('d_ob',[0,250,500,1000,2000,6000]); tab('slope_deg',[0,2,4,6,10,25])
# which never-burned cells (all 10 seasons) vs ones that burn at least once 2020+
nev=D.groupby('cell_id').agg(y=('y','max'),elig=('elig_ha','first'),crop=('wc_crop','first'),ff=('forest_frac','first'),dob=('d_ob','first'))
print(nev.groupby('y').median().round(3).to_string()); print(nev.y.value_counts().to_dict())
print('nohist cells by elig_ha<5:', (nev.elig<5).mean().round(3))
