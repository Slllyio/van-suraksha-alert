"""Physics bound on spotting from Ratapani litter fires.
(1) Albini 1983 / Chase 1981 maximum spotting distance from wind-driven surface fires, ported line by line
    from CFS fbp97spot.c (tall-grass coefficients A=129, B=-1.238, the only open-surface class in that code).
(2) ELMFIRE/Pyretechnics example spotting config: E[dX]=10*I^0.3*U^0.55 m, Var=425*E, survival exp(-d/200),
    1e-6 firebrands per kJ, Schroeder 1969 ignition probability. Expected spot fires 1-5 km per fire."""
import numpy as np
from scipy.stats import lognorm
def albini83(HFI, WS_kmh, A=129., B=-1.238):
    U = WS_kmh / 3.6; fU = A * U ** B; E = HFI * fU; H = 0.173 * np.sqrt(E); h_c = H ** 0.337 - 1.22
    h = max(h_c, 6.); Uh = U * (h / 10.) ** (1 / 7); U_H = U * (H / 10.) ** (1 / 7); h = h_c
    F = 1.3 * 3.6 * Uh * np.sqrt(max(h, 1e-3)) * (0.362 + np.sqrt(H / max(h, 1e-3)) * 0.5 * np.log(H / max(h, 1e-3)))
    X = 2.78 * U_H * np.sqrt(H) if h < 10 else Uh * np.sqrt(H) * (2.13 + np.log(H / h))
    return X + F, H
print('Albini 1983 (fbp97spot.c port): HFI kW/m, wind 10 m km/h -> value returned by SpotCalc, lofting height H m')
for hfi in (50, 125, 250, 500, 1000, 3000):
    print(hfi, [tuple(float(v) for v in np.round(albini83(hfi, w), 1)) for w in (10, 20, 30)])
def schroeder(T, M):
    Q = 144.512 - 0.266 * T - 0.00058 * T * T - T * M + 18.54 * (1 - np.exp(-15.1 * M)) + 640 * M
    X = max(0., 400 - Q) * 0.1; return min(0.000048 * X ** 4.3 * 0.02, 1.)
print('\nELMFIRE-style example config')
for I, U, area_ha in [(125, 2.0, 25), (125, 4.0, 25), (250, 4.0, 60), (500, 6.0, 60), (2000, 8.0, 200)]:
    E = 10 * I ** 0.3 * U ** 0.55; V = 425 * E
    s2 = np.log(1 + V / E ** 2); mu = np.log(E) - s2 / 2; d = lognorm(s=np.sqrt(s2), scale=np.exp(mu))
    heat = 18000 * 0.25 * area_ha * 1e4                     # kJ: 18 MJ/kg x 0.25 kg/m2 consumed
    n = 1e-6 * heat
    xs = np.linspace(1000, 5000, 4001); dens = d.pdf(xs) * np.exp(-xs / 200); p_land_surv = np.trapezoid(dens, xs)
    for T, M in [(35, 0.05), (35, 0.08)]:
        pI = schroeder(T, M)
        print(dict(I=I, U=U, area_ha=area_ha, mean_m=round(E), P_beyond_1km=f'{d.sf(1000):.3g}', P_beyond_2km=f'{d.sf(2000):.3g}',
                   firebrands=round(n), T=T, M=M, P_ign=round(pI, 2), expected_spots_1_5km=f'{n * p_land_surv * pI:.2g}',
                   expected_spots_1_5km_no_decay=f'{n * (d.sf(1000) - d.sf(5000)) * pI:.2g}'))
