"""List timing (round 23): train the kept recipe (B0 + static GIS, = system_rebuild variant L2_static) for two
information states and predict every test issue day.

  MD (after the day pass): features use detections through the ~13:30 IST pass of local day t (the current system;
      available by ~18:30-20:00 with NASA NRT, by ~15:15 with FSI). Label = any target fire on the next 4 passes
      (night t+1, day t+1, night t+2, day t+2) = local days t+1, t+2, exactly as before.
  MN (after the night pass): features also use the ~01:30 IST night pass of day t+1 (available by ~03:30 with FSI,
      ~07:00-09:30 with NASA NRT). Label = the next 4 passes (day t+1, night t+2, day t+2, night t+3).
MN is built by moving every night detection back one local day ('pseudo day'), so the unchanged feature code sees
it in day t. Fire history (prior seasons) is always taken from the unshifted table.
Usage: python3 lt_train.py MD|MN held|fwd   -> scratch r23/cube_{state}_{period}.pkl
MD held is the existing r22 cube of L2_static (same code, same seed), so it is not retrained."""
import sys, os, pickle, time
sys.path.insert(0, '/mnt/project-files/ratapani/fsi/scouting/code/system_rebuild')
import pandas as pd
import common as C
C.SC = '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r23/'   # symlinks to r22 inputs
import features as Fe, run as R, variants as VV


def shifted(V):
    V2 = V.copy(); n = V2.daynight.values == 'N'
    V2.loc[n, 'ld'] = V2.loc[n, 'ld'] - pd.Timedelta('1D'); V2['season'] = V2.ld.dt.year.astype('int16')
    return V2


if __name__ == '__main__':
    state, per = sys.argv[1], sys.argv[2]
    fn = C.SC + f'cube_{state}_{per}.pkl'
    V = C.load_det()
    if state == 'MN':
        Vs = shifted(V); _h = Fe.history
        Fe.history = lambda y, cfg, V_, fpw=None: _h(y, cfg, V, fpw)   # history from the unshifted table
        V = Vs
    tr, te = C.PERIODS[per]; cfg = {}; t0 = time.time()
    X, y, w, ts, ci, names = R.collect(tr, cfg, V, VV.ex_static)
    print('train rows', len(y), 'pos', int(y.sum()), 'feats', len(names), flush=True)
    m = R.fit(X, y, w, names, cfg); del X
    print('trained', round(time.time() - t0), flush=True)
    cube = R.predict_cubes([R.Wrapped(m)], te, cfg, V, VV.ex_static)
    pickle.dump(cube, open(fn, 'wb'), protocol=4); print('saved', fn, flush=True)
