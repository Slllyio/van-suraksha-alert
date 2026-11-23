s=open('s2leafon.py').read()
old="""    with ThreadPoolExecutor(6) as ex: stack = [x for x in ex.map(one, items) if x is not None]
    stack = np.stack(stack); out[name] = np.nanmedian(stack, 0).astype('float32'); out[name + '_n'] = np.isfinite(stack).sum(0).astype('uint8')
    del stack"""
assert old in s
s=s.replace(old,"""    from collections import defaultdict
    byd = defaultdict(list)
    for it in items: byd[it.datetime.date()].append(it)
    def day(its):
        m = None
        for it in its:
            x = one(it)
            if x is None: continue
            if m is None: m = x
            else: k = np.isnan(m) & ~np.isnan(x); m[k] = x[k]
        return None if m is None else m.astype('float16')
    with ThreadPoolExecutor(3) as ex: stack = [x for x in ex.map(day, byd.values()) if x is not None]
    stack = np.stack(stack); print(name, 'dates', len(stack), flush=True)
    med = np.empty((H, W), 'float32')
    for r in range(0, H, 256): med[r:r+256] = np.nanmedian(stack[:, r:r+256].astype('float32'), 0)
    out[name] = med; out[name + '_n'] = np.isfinite(stack).sum(0).astype('uint8')
    del stack""")
open('s2leafon.py','w').write(s)
