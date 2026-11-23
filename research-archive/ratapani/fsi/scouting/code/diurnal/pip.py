import numpy as np
class Path:
    def __init__(self,v): self.v=np.asarray(v)[:,:2]
    def contains_points(self,pts):
        x=pts[:,0][:,None]; y=pts[:,1][:,None]
        xi=self.v[:,0][None,:]; yi=self.v[:,1][None,:]
        xj=np.roll(self.v[:,0],1)[None,:]; yj=np.roll(self.v[:,1],1)[None,:]
        out=np.zeros(len(pts),bool)
        for s in range(0,len(pts),2000):
            xs=x[s:s+2000]; ys=y[s:s+2000]
            c=((yi>ys)!=(yj>ys)) & (xs < (xj-xi)*(ys-yi)/(yj-yi+1e-15)+xi)
            out[s:s+2000]=c.sum(1)%2==1
        return out
