import math
# Rothermel 1972 surface spread, dead fuels only, f_i weighting (BehavePlus-like, no live).
T2LB=0.0459137  # t/ac -> lb/ft2
def ros(loads_tac, sav, depth_ft, mx, M, U_kmh=0.0, slope_pct=0.0, h=8000., load_scale=1.0):
    rp,St,Se=32.,0.0555,0.01
    w=[l*T2LB*load_scale for l in loads_tac]
    s=[x for x in sav]
    A=[si*wi/rp for si,wi in zip(s,w)]; At=sum(A)
    f=[a/At for a in A]
    sig=sum(fi*si for fi,si in zip(f,s))
    wn=sum(fi*wi*(1-St) for fi,wi in zip(f,w))
    Mf=sum(fi*mi for fi,mi in zip(f,M))
    rhob=sum(w)/depth_ft; beta=rhob/rp
    bop=3.348*sig**-0.8189
    gmax=sig**1.5/(495+0.0594*sig**1.5); Aa=133*sig**-0.7913
    g=gmax*(beta/bop)**Aa*math.exp(Aa*(1-beta/bop))
    rm=min(Mf/mx,1.0); etaM=max(0.0,1-2.59*rm+5.11*rm**2-3.52*rm**3)
    etas=0.174*Se**-0.19
    IR=g*wn*h*etaM*etas
    xi=math.exp((0.792+0.681*sig**0.5)*(beta+0.1))/(192+0.2595*sig)
    den=rhob*sum(fi*math.exp(-138/si)*(250+1116*mi) for fi,si,mi in zip(f,s,M))
    R0=IR*xi/den
    U=U_kmh*1000/0.3048/60  # ft/min midflame
    C=7.47*math.exp(-0.133*sig**0.55); B=0.02526*sig**0.54; E=0.715*math.exp(-3.59e-4*sig)
    phiw=C*U**B*(beta/bop)**-E if U>0 else 0
    phis=5.275*beta**-0.3*(slope_pct/100)**2
    R=R0*(1+phiw+phis)
    tr=384/sig; I=IR*tr*R/60  # Btu/ft/s
    L=0.45*I**0.46 if I>0 else 0
    return dict(sig=round(sig), beta=round(beta,4), bop=round(bop,4), R0_mmin=round(R0*0.3048,3), R_mmin=round(R*0.3048,3), I_kWm=round(I*3.4613,1), L_m=round(L*0.3048,2))
models={
 'FBFM8':([1.5,1.0,2.5],[2000,109,30],0.2,0.30),
 'FBFM9':([2.92,0.41,0.15],[2500,109,30],0.2,0.25),
 'TL2':([1.40,2.30,2.20],[2000,109,30],0.2,0.25),
 'TL3':([0.50,2.20,2.80],[2000,109,30],0.3,0.20),
 'TL6':([2.40,1.20,1.20],[2000,109,30],0.3,0.25),
 'TL8':([5.80,1.40,1.10],[1800,109,30],0.3,0.35),
 'TL9':([6.65,3.30,4.15],[1800,109,30],0.6,0.35),
 'CDAC_Forest(0.27kg/m2 all 1h,SAV1224,0.2ft,Mx30)':([0.270*4.4609],[1224],0.2,0.30),
}
for M1 in (0.04,0.06,0.08,0.10,0.12):
  for U in (0.0,2.0,5.0):
    for k,(l,s,d,mx) in models.items():
        M=[M1,M1+0.01,M1+0.02][:len(l)]
        r=ros(l,s,d,mx,M,U_kmh=U,slope_pct=10)
        print(f"M1h={M1:.2f} U={U:>3} {k:<50} {r}")
