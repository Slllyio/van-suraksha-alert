import struct, zlib, numpy as np
TYPES = {7: 'B', 6: 'b', 8: 'h', 9: 'i', 1: 'B', 2: 's', 3: 'H', 4: 'I', 5: 'II', 12: 'd', 16: 'Q', 11: 'f'}
SZ = {7: 1, 6: 1, 8: 2, 9: 4, 1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 12: 8, 16: 8, 11: 4}
def tags(path):
    b = open(path, 'rb').read(); e = '<' if b[:2] == b'II' else '>'
    ver = struct.unpack(e + 'H', b[2:4])[0]; assert ver == 42, ver
    off = struct.unpack(e + 'I', b[4:8])[0]; n = struct.unpack(e + 'H', b[off:off + 2])[0]; T = {}
    for i in range(n):
        t, ty, cnt, vo = struct.unpack(e + 'HHII', b[off + 2 + 12 * i: off + 14 + 12 * i])
        size = SZ[ty] * cnt; data = b[off + 10 + 12 * i: off + 14 + 12 * i] if size <= 4 else b[vo: vo + size]
        if ty == 2: T[t] = data.decode(errors='ignore')
        elif ty == 5: T[t] = struct.unpack(e + 'I' * (2 * cnt), data)
        else: T[t] = struct.unpack(e + TYPES[ty] * cnt, data[:SZ[ty] * cnt])
    return b, e, T
def read(path):
    b, e, T = tags(path)
    W, H = T[256][0], T[257][0]; comp = T[259][0]; spp = T.get(277, (1,))[0]; planar = T.get(284, (1,))[0]; pred = T.get(317, (1,))[0]
    tw, th = (T[322][0], T[323][0]) if 322 in T else (W, T[278][0]); offs, cnts = (T[324], T[325]) if 324 in T else (T[273], T[279])
    out = np.zeros((spp, H, W), np.int16); ntx = (W + tw - 1) // tw; nty = (H + th - 1) // th
    for k, (o, c) in enumerate(zip(offs, cnts)):
        raw = b[o:o + c]
        if comp == 8 or comp == 32946: raw = zlib.decompress(raw)
        elif comp != 1: raise ValueError('compression %d' % comp)
        if planar == 1:
            a = np.frombuffer(raw, e + 'i2').reshape(th, tw, spp)
            if pred == 2: a = np.cumsum(a, axis=1, dtype=np.int16)
            ti = k; band = None
        else:
            a = np.frombuffer(raw, e + 'i2').reshape(th, tw, 1)
            if pred == 2: a = np.cumsum(a, axis=1, dtype=np.int16)
            band = k // (ntx * nty); ti = k % (ntx * nty)
        ty_, tx_ = divmod(ti, ntx); y0, x0 = ty_ * th, tx_ * tw; hh, ww = min(th, H - y0), min(tw, W - x0)
        if band is None: out[:, y0:y0 + hh, x0:x0 + ww] = np.moveaxis(a[:hh, :ww], 2, 0)
        else: out[band, y0:y0 + hh, x0:x0 + ww] = a[:hh, :ww, 0]
    return out, T
if __name__ == '__main__':
    import sys; b, e, T = tags(sys.argv[1]); print({k: (v if len(str(v)) < 100 else str(v)[:100]) for k, v in T.items()})
