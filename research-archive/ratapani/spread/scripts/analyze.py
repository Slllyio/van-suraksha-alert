import pandas as pd, numpy as np, sys
for name in sys.argv[1:]:
    d = pd.read_parquet(f'/tmp/claude-0/spread/data/res_{name}.parquet')
    s = d.dropna(subset=['sor_model'])
    win = (s.sor_model > s.sor_iso).mean(); tie = (s.sor_model == s.sor_iso).mean()
    big = s[s.scar_px >= 250]
    t = d.dropna(subset=['n_later'])
    print(f"[{name}] events {len(d)}, with scar>=1ha {len(s)} | Sorensen at scar area: physics {s.sor_model.mean():.3f} vs distance {s.sor_iso.mean():.3f} "
          f"(physics better in {win:.0%}, tie {tie:.0%}); scars>=10 ha (n={len(big)}): {big.sor_model.mean():.3f} vs {big.sor_iso.mean():.3f}")
    print(f"   absolute: median scar {s.scar_px.median()*0.04:.1f} ha, model 24h {s.area24.median()*0.04:.0f} ha, 48h {s.area48.median()*0.04:.0f} ha; Sorensen 24h {s.sor24.mean():.3f} 48h {s.sor48.mean():.3f}")
    if len(t):
        print(f"   later VIIRS detections (n={t.n_later.sum():.0f} in {len(t)} events): inside physics front {t.hit_model.sum()/t.n_later.sum():.1%} vs equal-area circle {t.hit_iso.sum()/t.n_later.sum():.1%}")
    if 'sor_end' in d:
        for nm, part in [('2017-21', s[s.season <= 2021]), ('2022-24', s[s.season >= 2022])]:
            print(f"   forecast to last detection+12h [{nm}]: median area ratio model/scar {np.median(part.area_end / part.scar_px):.2f}, Sorensen {part.sor_end.mean():.3f}")
