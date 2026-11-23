"""Rothermel (1972, Albini 1976 form) single-class dead fuel, used to compare
predicted ROS against measured field litter fires found in the r9 behaviour scouting.
Inputs SI: w0 kg/m2 (oven-dry load), delta m (depth), M fraction, U midflame m/s,
slope tan, sigma 1/m, h J/kg, Mx fraction, rho_p kg/m3."""
import math
def ros(w0, delta, M, U=0.0, tanphi=0.0, sigma_m=6000., h=18.6e6, Mx=0.30, rho_p=512., St=0.0555, Se=0.010):
    # convert to English units
    w0e = w0*0.204816          # lb/ft2
    de = delta*3.28084         # ft
    sig = sigma_m/3.28084      # 1/ft
    he = h/2326.               # Btu/lb
    rpe = rho_p*0.062428       # lb/ft3
    Ue = U*196.85              # ft/min
    rho_b = w0e/de
    beta = rho_b/rpe
    beta_op = 3.348*sig**-0.8189
    A = 133.0*sig**-0.7913
    Gmax = sig**1.5/(495+0.0594*sig**1.5)
    G = Gmax*(beta/beta_op)**A*math.exp(A*(1-beta/beta_op))
    wn = w0e*(1-St)
    r = min(M/Mx,1.0)
    etaM = 1-2.59*r+5.11*r**2-3.52*r**3
    etas = min(0.174*Se**-0.19,1.0)
    IR = G*wn*he*etaM*etas           # Btu/ft2/min
    xi = math.exp((0.792+0.681*sig**0.5)*(beta+0.1))/(192+0.2595*sig)
    eps = math.exp(-138./sig)
    Qig = 250+1116*M
    C = 7.47*math.exp(-0.133*sig**0.55); B = 0.02526*sig**0.54; E = 0.715*math.exp(-3.59e-4*sig)
    phiw = C*Ue**B*(beta/beta_op)**-E if Ue>0 else 0.
    phis = 5.275*beta**-0.3*tanphi**2
    R = IR*xi*(1+phiw+phis)/(rho_b*eps*Qig)   # ft/min
    return R*0.3048, dict(rho_b_SI=w0/delta, beta=beta, beta_ratio=beta/beta_op, IR_kWm2=IR*0.18920, phis=phis, phiw=phiw)

cases = [
 # name, w0, depth, M, midflame U, observed ROS m/min
 ("Teak Ecuador 2019 (10 head fires)", 0.58, 0.1423, 0.112, 0.72*0.6, 0.61),   # wind 0.72 m/s at 0.5 m; take 0.6 to midflame-ish
 ("Teak Ecuador 2026 (15 plots)",      1.10, 0.1357, 0.124, 0.06, 0.48),
 ("HKK DDF Wiriya 2009 (21, head)",    0.464,0.1257, 0.124, 3.55/3.6*0.4, 1.89),  # 3.55 km/h open; WAF 0.4
 ("Thai MDF/DDF Junpen 2013 head",     0.236+0.152*0.5, 0.10, 0.065, 0.5, 1.37), # depth not reported: assume 10 cm
 ("Gadchiroli Saha 2002 (calm)",       0.40*0.6, 0.06, 0.08, 0.0, 0.3),          # 4 t/ha fresh wt, ~60% dry; depth assumed
]
print("Rothermel check, sigma=6000 1/m (teak leaf ~0.3 mm thick), Mx=0.30, h=18.6 MJ/kg")
for name,w,d,M,U,obs in cases:
    R,info = ros(w,d,M,U)
    print(f"{name:38s} pred {R:5.2f} m/min  obs {obs:4.2f}  obs/pred {obs/R:4.1f}  rho_b {info['rho_b_SI']:.1f} kg/m3  beta/bop {info['beta_ratio']:.2f}")
print()
print("Our beds, no wind, flat:")
for name,w,d in [("v2 mean 1.46 t/ha loose 2.5 kg/m3",0.146,0.146/2.5),("2.5 t/ha loose 2.5 kg/m3",0.25,0.25/2.5),
                 ("2.5 t/ha at teak-field 4.1 kg/m3",0.25,0.25/4.1),("2.5 t/ha at 8 kg/m3",0.25,0.25/8),("2.5 t/ha compact 30 kg/m3",0.25,0.25/30)]:
    for M in (0.04,0.06,0.10):
        R,info = ros(w,d,M,0.0)
        R1,_ = ros(w,d,M,0.5)
        print(f"{name:36s} M={M:.2f} depth {d*100:4.1f} cm  ROS calm {R*60:5.1f} m/h  U=0.5 m/s {R1*60:6.1f} m/h")
print()
print("Slope multipliers (1+phi_s) vs measured litter-bed slope burns (Ortiz-Mendoza 2024: 0->10deg x1.43, 0->20deg x3.0)")
for w,d in [(0.5,0.5/4.0),(0.25,0.25/2.5)]:
    for deg in (5,10,20):
        t=math.tan(math.radians(deg)); R0,_=ros(w,d,0.08); R,_=ros(w,d,0.08,0,t)
        jun=math.exp(0.018*100*t)
        print(f" rho_b {w/d:.1f}  {deg:2d} deg: Rothermel x{R/R0:.2f}   Junpen exp(0.018*S%) x{jun:.2f}")
print()
print("Junpen 2013 models (m/min -> m/h):")
for M in (4,5,6,8,12):
    for S in (0,10,20):
        r=1.657*math.exp(0.018*S)*math.exp(-0.080*M); print(f"  M={M:2d}% S={S:2d}%  {r:4.2f} m/min = {r*60:5.1f} m/h")
for F in (1.0,1.46,2.0,2.5,3.0,4.0):
    r=0.251*math.exp(0.439*F); print(f"  F_LG={F:.2f} t/ha S=0  {r:4.2f} m/min = {r*60:5.1f} m/h")
print("Wiriya 2009 models:")
for W in (1,2,3.55,5,8):
    r=0.3565*math.exp(0.4261*W); print(f"  wind {W} km/h  {r:4.2f} m/min = {r*60:5.1f} m/h")
for D in (3,5,8,12.57):
    r=0.2382*D**0.8078; print(f"  depth {D} cm  {r:4.2f} m/min = {r*60:5.1f} m/h")
print()
print("Byram intensity / flame length for Ratapani-like fronts (H=18 MJ/kg, consumption 0.8):")
for load in (1.46,2.0,3.0):
    for Rmh in (24,70,98):
        I=18000*load*0.1*0.8*Rmh/3600.; L=0.0775*I**0.46
        print(f"  load {load} t/ha  R {Rmh} m/h  I={I:5.1f} kW/m  L={L:4.2f} m")
print()
print("12-h mean front speed if day spread lasts Hd hours at Rd and night at Rn (m/min):")
for Rd,Hd,Rn in [(1.4,8,0.3),(1.0,8,0.2),(1.9,6,0.0),(0.6,10,0.2)]:
    print(f"  day {Rd} m/min x {Hd} h + night {Rn} m/min x {12-Hd} h -> {(Rd*Hd+Rn*(12-Hd))*60/12:5.1f} m/h")
