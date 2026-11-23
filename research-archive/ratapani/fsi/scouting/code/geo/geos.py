import numpy as np
def ll2lc(lat,lon,sub=128.2,cfac=20425338.903339352,lfac=-20425338.903339352,coff=2750.5,loff=2750.5,h=42164000.0,req=6378137.0,rp=6356752.3):
    lat=np.radians(lat); dl=np.radians(lon-sub)
    cl=np.arctan((rp/req)**2*np.tan(lat)); e2=1-(rp/req)**2
    rl=rp/np.sqrt(1-e2*np.cos(cl)**2)
    r1=h-rl*np.cos(cl)*np.cos(dl); r2=-rl*np.cos(cl)*np.sin(dl); r3=rl*np.sin(cl); rn=np.sqrt(r1**2+r2**2+r3**2)
    x=np.degrees(np.arctan(-r2/r1)); y=np.degrees(np.arcsin(r3/rn))
    return loff+y*2**-16*lfac, coff+x*2**-16*cfac   # line, col (0-based-ish float)
def vza(lat,lon,sub,h=42164000.0,R=6371000.0):
    lat=np.radians(lat); dl=np.radians(lon-sub); g=np.arccos(np.cos(lat)*np.cos(dl))
    return np.degrees(np.arctan2(np.sin(g),np.cos(g)-R/h))
