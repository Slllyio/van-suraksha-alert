import sys, numpy as np, collections
from PIL import Image
for f in sys.argv[1:]:
    a=np.array(Image.open(f).convert('RGBA')); m=a[...,3]>0
    c=collections.Counter(map(tuple,a[m][:,:3].tolist()))
    print(f, a.shape, int(m.sum()), c.most_common(4))
