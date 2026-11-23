"""Rothermel (1972) surface fire spread with Albini (1976) multi-class weighting and the
BehavePlus wind/slope vector, as used by WRF-SFIRE, FARSITE and FlamMap.
Fuel models: Scott & Burgan (2005). All internal maths in the US units of the original papers."""
import numpy as np

T_AC = 0.0459137  # tons/acre -> lb/ft2
# name: (1h, 10h, 100h, live herb, live woody loads t/ac), (SAV 1h, herb, woody 1/ft), depth ft, dead Mx %, dynamic
FUELS = {
    'NB':  ((0, 0, 0, 0, 0), (2000, 1800, 1500), 0.0, 15, False),
    'GR1': ((0.10, 0, 0, 0.30, 0), (2200, 2000, 1500), 0.4, 15, True),
    'GR2': ((0.10, 0, 0, 1.00, 0), (2000, 1800, 1500), 1.0, 15, True),
    'GS2': ((0.50, 0.50, 0, 0.60, 1.00), (2000, 1800, 1800), 1.5, 15, True),
    'TU1': ((0.20, 0.90, 1.50, 0.20, 0.90), (2000, 1800, 1600), 0.6, 20, True),
    # Anderson (1982) static models, WRF-SFIRE default set (FBFM13)
    'FM1': ((0.74, 0, 0, 0, 0), (3500, 1500, 1500), 1.0, 12, False),
    'FM2': ((2.00, 1.00, 0.50, 0.50, 0), (3000, 1500, 1500), 1.0, 15, False),
    'FM3': ((3.01, 0, 0, 0, 0), (1500, 1500, 1500), 2.5, 25, False),
    'FM8': ((1.50, 1.00, 2.50, 0, 0), (2000, 1500, 1500), 0.2, 30, False),
    'FM9': ((2.92, 0.41, 0.15, 0, 0), (2500, 1500, 1500), 0.2, 25, False),
    'TL2': ((1.40, 2.30, 2.20, 0, 0), (2000, 1800, 1500), 0.2, 25, False),
    'TL6': ((2.40, 1.20, 1.20, 0, 0), (2000, 1800, 1500), 0.3, 25, False),
    'TL9': ((6.65, 3.30, 4.15, 0, 0), (1800, 1800, 1500), 0.6, 35, False),
}
H, RHO_P, S_T, S_E = 8000.0, 32.0, 0.0555, 0.010


def fuel_classes(name, m1, m10, m100, mherb, mwood, load_scale=1.0):
    """Return dead and live class arrays (load lb/ft2, SAV, moisture) after dynamic herb curing."""
    loads, (s1, sh, sw), depth, mx, dyn = FUELS[name]
    w1, w10, w100, wh, ww = [l * T_AC * load_scale for l in loads]
    dead = [[w1, s1, m1], [w10, 109.0, m10], [w100, 30.0, m100]]
    live = [[0.0, sh, mherb], [ww, sw, mwood]]
    if dyn and wh > 0:
        cured = np.clip((1.20 - mherb) / 0.90, 0, 1)
        dead.append([wh * cured, sh, m1])
        live[0][0] = wh * (1 - cured)
    return np.array(dead, float), np.array(live, float), depth, mx / 100.0


def rothermel(name, m1, m10, m100, mherb=0.6, mwood=0.9, load_scale=1.0):
    """No-wind no-slope spread R0 (ft/min), reaction intensity, and the coefficients needed for
    wind (C, B, E, beta/beta_op) and slope (beta) factors. Returns dict or None for non-burnable."""
    dead, live, depth, mx = fuel_classes(name, m1, m10, m100, mherb, mwood, load_scale)
    if depth <= 0 or dead[:, 0].sum() + live[:, 0].sum() <= 0:
        return None
    cats = [c[c[:, 0] > 0] for c in (dead, live)]
    A_ij = [c[:, 1] * c[:, 0] / RHO_P for c in cats]
    A_i = np.array([a.sum() for a in A_ij]); A_T = A_i.sum()
    f_i = A_i / A_T
    f_ij = [a / a.sum() if a.sum() > 0 else a for a in A_ij]
    sig_i = np.array([(f * c[:, 1]).sum() for f, c in zip(f_ij, cats)])
    sigma = (f_i * sig_i).sum()
    w0 = dead[:, 0].sum() + live[:, 0].sum()
    rho_b = w0 / depth; beta = rho_b / RHO_P
    beta_op = 3.348 * sigma ** -0.8189; rel = beta / beta_op
    gmax = sigma ** 1.5 / (495 + 0.0594 * sigma ** 1.5)
    A = 133.0 * sigma ** -0.7913
    gamma = gmax * rel ** A * np.exp(A * (1 - rel))
    # moisture of extinction for live fuels (Albini 1976)
    d, l = dead[dead[:, 0] > 0], live[live[:, 0] > 0]
    mx_live = mx
    if len(l):
        wd = (d[:, 0] * np.exp(-138.0 / d[:, 1])).sum(); wl = (l[:, 0] * np.exp(-500.0 / l[:, 1])).sum()
        mfd = (d[:, 0] * np.exp(-138.0 / d[:, 1]) * d[:, 2]).sum() / wd
        mx_live = max(2.9 * (wd / wl) * (1 - mfd / mx) - 0.226, mx)
    IR = 0.0; heat_sink = 0.0
    for k, (c, f) in enumerate(zip(cats, f_ij)):
        if len(c) == 0:
            continue
        Mf = (f * c[:, 2]).sum(); Mxk = mx if k == 0 else mx_live
        r = min(Mf / Mxk, 1.0)
        eta_m = 1 - 2.59 * r + 5.11 * r ** 2 - 3.52 * r ** 3
        eta_s = min(0.174 * S_E ** -0.19, 1.0)
        wn = (f * c[:, 0]).sum() * (1 - S_T)
        IR += gamma * wn * H * eta_m * eta_s
        heat_sink += f_i[k] * (f * np.exp(-138.0 / c[:, 1]) * (250 + 1116 * c[:, 2])).sum()
    xi = np.exp((0.792 + 0.681 * sigma ** 0.5) * (beta + 0.1)) / (192 + 0.2595 * sigma)
    R0 = IR * xi / (rho_b * heat_sink) if IR > 0 else 0.0
    C = 7.47 * np.exp(-0.133 * sigma ** 0.55); B = 0.02526 * sigma ** 0.54; E = 0.715 * np.exp(-3.59e-4 * sigma)
    return dict(R0=R0, IR=IR, C=C, B=B, E=E, rel=rel, beta=beta)


def emc(T_c, rh):
    """Simard (1968) equilibrium moisture content (fraction); T in C, RH in %."""
    T = T_c * 9 / 5 + 32; h = np.clip(rh, 0, 100)
    e = np.where(h < 10, 0.03229 + 0.281073 * h - 0.000578 * h * T,
        np.where(h < 50, 2.22749 + 0.160107 * h - 0.01478 * T,
                 21.0606 + 0.005565 * h ** 2 - 0.00035 * h * T - 0.483199 * h))
    return np.clip(e, 0.5, 40) / 100.0


def dead_moisture(T_c, rh, precip_mm, solar_wm2):
    """Hourly 1/10/100-h dead fuel moisture by exponential time-lag toward EMC.
    Surface fuel in sun runs hotter and drier than 2 m air (NFDRS fuel-atmosphere correction:
    up to +14 C and lower RH at full sun)."""
    n = len(T_c); out = np.zeros((n, 3))
    dT = 14.0 * np.clip(solar_wm2 / 900.0, 0, 1)
    es = lambda t: 6.112 * np.exp(17.67 * t / (t + 243.5))
    rh_s = np.clip(rh * es(T_c) / es(T_c + dT), 1, 100)
    eq = emc(T_c + dT, rh_s)
    m = np.array([eq[0], eq[0] + 0.02, eq[0] + 0.04])
    for t in range(n):
        for k, tau in enumerate((1.0, 10.0, 100.0)):
            m[k] = eq[t] + (m[k] - eq[t]) * np.exp(-1.0 / tau)
            if precip_mm[t] > 0.5:
                m[k] = max(m[k], (0.35, 0.25, 0.20)[k] if precip_mm[t] > 2 else (0.25, 0.15, 0.12)[k])
        out[t] = m
    return out


def phi_wind(p, U_ftmin):
    return p['C'] * U_ftmin ** p['B'] * p['rel'] ** -p['E'] if U_ftmin > 0 else 0.0


def phi_slope(p, tan_slope):
    return 5.275 * p['beta'] ** -0.3 * tan_slope ** 2


def rothermel_px(w1, w10, depth_m, mx, sav1_ft=2000.0):
    """Per-pixel moisture-independent terms for a dead-only bed (1 h litter/cured grass + 10 h twigs).
    Inputs SI (kg/m2, m). Returns dict of arrays; moisture enters in r0_px."""
    lb = 0.204816  # kg/m2 -> lb/ft2
    w = np.stack([w1 * lb, w10 * lb]); sav = np.stack([np.broadcast_to(np.asarray(sav1_ft, float), w1.shape), np.full(w1.shape, 109.0)])
    depth = depth_m / 0.3048
    A = sav * w / RHO_P; At = A.sum(0); f = np.where(At > 0, A / np.where(At > 0, At, 1), 0)
    sigma = (f * sav).sum(0)
    rho_b = np.where(depth > 0, w.sum(0) / np.where(depth > 0, depth, 1), 0); beta = rho_b / RHO_P
    sig = np.where(sigma > 0, sigma, 2000.0)
    beta_op = 3.348 * sig ** -0.8189; rel = np.where(beta > 0, beta / beta_op, 1.0)
    gmax = sig ** 1.5 / (495 + 0.0594 * sig ** 1.5); Ac = 133.0 * sig ** -0.7913
    gamma = gmax * rel ** Ac * np.exp(Ac * (1 - rel))
    xi = np.exp((0.792 + 0.681 * sig ** 0.5) * (beta + 0.1)) / (192 + 0.2595 * sig)
    wn = (f * w).sum(0) * (1 - S_T)
    eta_s = min(0.174 * S_E ** -0.19, 1.0)
    C = 7.47 * np.exp(-0.133 * sig ** 0.55); B = 0.02526 * sig ** 0.54; E = 0.715 * np.exp(-3.59e-4 * sig)
    ok = (w.sum(0) > 0) & (depth > 0) & np.isfinite(depth)
    return dict(f=f, sav=sav, gamma=gamma, wn=wn, eta_s=eta_s, xi=xi, rho_b=rho_b, mx=mx, C=C, B=B, E=E,
                rel=rel, beta=beta, ok=ok)


def r0_px(p, m1, m10):
    """No-wind no-slope ROS (ft/min) per pixel for scalar dead moistures."""
    M = np.array([m1, m10])[:, None]
    Mf = (p['f'] * M).sum(0); r = np.clip(Mf / np.where(p['mx'] > 0, p['mx'], 1), 0, 1)
    eta_m = 1 - 2.59 * r + 5.11 * r ** 2 - 3.52 * r ** 3
    IR = p['gamma'] * p['wn'] * H * eta_m * p['eta_s']
    hs = (p['f'] * np.exp(-138.0 / p['sav']) * (250 + 1116 * M)).sum(0)
    R0 = np.where(p['ok'] & (r < 1), IR * p['xi'] / np.where(p['rho_b'] > 0, p['rho_b'] * hs, 1), 0.0)
    return R0
