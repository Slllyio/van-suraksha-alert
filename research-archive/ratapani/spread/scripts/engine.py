"""Fire-front propagation on the 20 m grid: time-dependent minimum-travel-time (Dijkstra) with a
16-neighbour stencil and elliptical Rothermel spread (fire at the rear focus). For a front that
moves with spatially varying speed this solves the same eikonal problem as WRF-SFIRE's level set
(dpsi/dt + S|grad psi| = 0); hourly weather enters through FIFO travel times."""
import numpy as np, numba as nb, heapq

OFFS = np.array([(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1),
                 (-1, -2), (-1, 2), (1, -2), (1, 2), (-2, -1), (-2, 1), (2, -1), (2, 1)], np.int64)


@nb.njit(cache=True)
def ros_fields(fuel_idx, tan_slope, upslope_az, R0, phiw, wind_az, C, B, E, rel, beta, lb_cap):
    """Per hour and pixel: head ROS (m/min), heading (rad, clockwise from north), eccentricity."""
    nh = R0.shape[1]; ny, nx = fuel_idx.shape
    Rh = np.zeros((nh, ny, nx), np.float32); Dh = np.zeros((nh, ny, nx), np.float32); Eh = np.zeros((nh, ny, nx), np.float32)
    for h in range(nh):
        wa = wind_az[h] * np.pi / 180
        for i in range(ny):
            for j in range(nx):
                k = fuel_idx[i, j]
                if k < 0 or R0[k, h] <= 0:
                    continue
                ps = 5.275 * beta[k] ** -0.3 * tan_slope[i, j] ** 2
                sa = upslope_az[i, j] * np.pi / 180
                vx = phiw[k, h] * np.sin(wa) + ps * np.sin(sa)
                vy = phiw[k, h] * np.cos(wa) + ps * np.cos(sa)
                pe = np.sqrt(vx * vx + vy * vy)
                Rh[h, i, j] = R0[k, h] * (1 + pe) * 0.3048
                Dh[h, i, j] = np.arctan2(vx, vy)
                ue = (pe * rel[k] ** E[k] / C[k]) ** (1.0 / B[k]) / 88.0 if pe > 0 else 0.0  # mph
                lb = 0.936 * np.exp(0.2566 * ue) + 0.461 * np.exp(-0.1548 * ue) - 0.397
                lb = min(max(lb, 1.0), lb_cap)
                Eh[h, i, j] = np.sqrt(lb * lb - 1) / lb
    return Rh, Dh, Eh


@nb.njit(cache=True)
def _dir_ros(R, D, e, th):
    if R <= 0:
        return 0.0
    return R * (1 - e) / (1 - e * np.cos(th - D))


@nb.njit(cache=True)
def arrival(Rh, Dh, Eh, burnable, ign_i, ign_j, ign_t, res, tmax, offs, strict):
    """Arrival time (min) from ignition pixels. Rh/Dh/Eh hourly fields."""
    nh, ny, nx = Rh.shape
    T = np.full((ny, nx), np.inf)
    heap = [(0.0, 0, 0)]; heap.pop()
    for n in range(len(ign_i)):
        T[ign_i[n], ign_j[n]] = ign_t[n]
        heap.append((ign_t[n], ign_i[n], ign_j[n]))
    heapq.heapify(heap)
    while len(heap):
        t, i, j = heapq.heappop(heap)
        if t > T[i, j] or t > tmax:
            continue
        for o in range(offs.shape[0]):
            di, dj = offs[o, 0], offs[o, 1]
            a, b = i + di, j + dj
            if a < 0 or b < 0 or a >= ny or b >= nx or not burnable[a, b]:
                continue
            if strict and abs(di) + abs(dj) > 1:
                # no jumping over a one-pixel non-burnable line (road, stream, fire line)
                if abs(di) == 1 and abs(dj) == 1:
                    if not (burnable[i + di, j] or burnable[i, j + dj]):
                        continue
                elif abs(dj) == 2:
                    sj = dj // 2
                    if not (burnable[i, j + sj] or burnable[i + di, j + sj]):
                        continue
                else:
                    si = di // 2
                    if not (burnable[i + si, j] or burnable[i + si, j + dj]):
                        continue
            th = np.arctan2(dj, -di)   # east = +j, north = -i
            dist = res * np.sqrt(di * di + dj * dj)
            # FIFO integration through hourly weather
            tt = t; rem = dist; ok = False
            while True:
                h = int(tt // 60.0)
                if h >= nh or tt > tmax:
                    break
                v = 0.5 * (_dir_ros(Rh[h, i, j], Dh[h, i, j], Eh[h, i, j], th) + _dir_ros(Rh[h, a, b], Dh[h, a, b], Eh[h, a, b], th))
                tn = (h + 1) * 60.0
                if v > 0 and v * (tn - tt) >= rem:
                    tt += rem / v; ok = True; break
                if v > 0:
                    rem -= v * (tn - tt)
                tt = tn
            if ok and tt < T[a, b]:
                T[a, b] = tt
                heapq.heappush(heap, (tt, a, b))
    return T


@nb.njit(cache=True)
def ros_fields_px(R0h, tan_slope, upslope_az, U, wind_az, C, B, E, rel, beta, lb_cap):
    """Per-pixel fuel version: R0h[h,i,j] ft/min; C,B,E,rel,beta per pixel; U[h] midflame ft/min."""
    nh, ny, nx = R0h.shape
    Rh = np.zeros((nh, ny, nx), np.float32); Dh = np.zeros((nh, ny, nx), np.float32); Eh = np.zeros((nh, ny, nx), np.float32)
    for h in range(nh):
        wa = wind_az[h] * np.pi / 180
        for i in range(ny):
            for j in range(nx):
                if R0h[h, i, j] <= 0:
                    continue
                pw = C[i, j] * U[h] ** B[i, j] * rel[i, j] ** -E[i, j] if U[h] > 0 else 0.0
                ps = 5.275 * beta[i, j] ** -0.3 * tan_slope[i, j] ** 2
                sa = upslope_az[i, j] * np.pi / 180
                vx = pw * np.sin(wa) + ps * np.sin(sa); vy = pw * np.cos(wa) + ps * np.cos(sa)
                pe = np.sqrt(vx * vx + vy * vy)
                Rh[h, i, j] = R0h[h, i, j] * (1 + pe) * 0.3048
                Dh[h, i, j] = np.arctan2(vx, vy)
                ue = (pe * rel[i, j] ** E[i, j] / C[i, j]) ** (1.0 / B[i, j]) / 88.0 if pe > 0 else 0.0
                lb = 0.936 * np.exp(0.2566 * ue) + 0.461 * np.exp(-0.1548 * ue) - 0.397
                lb = min(max(lb, 1.0), lb_cap)
                Eh[h, i, j] = np.sqrt(lb * lb - 1) / lb
    return Rh, Dh, Eh
