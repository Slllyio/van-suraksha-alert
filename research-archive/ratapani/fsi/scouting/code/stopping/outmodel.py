import pandas as pd, numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.isotonic import IsotonicRegression
R=pd.read_csv('steps_1000_48.csv'); F=pd.read_csv('fires_1000_48.csv',index_col=0)
R['yr']=R.fire.map(F.yr)
# expand to (step,k) rows: state = k silent passes after a detection; label = fire seen again later
rows=[]
for r in R.itertuples():
    K = r.missed if r.redet else r.k_avail
    for k in range(0, min(K, 8)+ (0 if r.redet else 0)):
        pass
    for k in range(0, 9):
        if r.redet and k>r.missed: break
        if (not r.redet) and k>r.k_avail: break
        rows.append((r.yr,k,np.log1p(r.frp),np.log1p(r.frp_cum),r.dn=='N',r.hour,min(r.npass_so_far,8),int(r.redet)))
X=pd.DataFrame(rows,columns=['yr','k','lfrp','lfrpc','night','hour','np','y'])
feats=['k','lfrp','lfrpc','night','hour','np']
res=[]
for test in sorted(X.yr.unique()):
    tr,te=X[X.yr!=test],X[X.yr==test]
    m=HistGradientBoostingClassifier(max_iter=200,learning_rate=0.05,max_leaf_nodes=15).fit(tr[feats],tr.y)
    p=m.predict_proba(te[feats])[:,1]
    base=tr.groupby('k').y.mean(); pb=te.k.map(base).fillna(tr.y.mean())
    res.append(te.assign(p=p,pb=pb))
Z=pd.concat(res)
print('rows',len(Z),'base rate',Z.y.mean().round(3))
print('AUC gbm %.3f  k-only %.3f'%(roc_auc_score(Z.y,Z.p),roc_auc_score(Z.y,Z.pb)))
print('Brier gbm %.4f k-only %.4f climatology %.4f'%(brier_score_loss(Z.y,Z.p),brier_score_loss(Z.y,Z.pb),brier_score_loss(Z.y,np.full(len(Z),Z.y.mean()))))
Z['bin']=pd.cut(Z.p,[0,.1,.2,.3,.4,.5,.6,.7,.8,.9,1])
print(Z.groupby('bin',observed=True).agg(n=('y','size'),pred=('p','mean'),obs=('y','mean')).round(3))
# rule: declare out when p<0.1
for thr in [0.05,0.1,0.2]:
    s=Z[Z.p<thr]; print(f'declare out at p<{thr}: {len(s)} states, {100*s.y.mean():.1f}% were actually seen again')
