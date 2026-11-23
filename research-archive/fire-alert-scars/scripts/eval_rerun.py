"""Re-run alert_scar.py on the exact alert and control sample in out/eval_chip.csv (for comparing versions).
Usage: python eval_rerun.py <workers> <outname>"""
import sys, pandas as pd
from multiprocessing import Pool
from eval_chip import run, OUT
if __name__ == "__main__":
    D = pd.read_csv(OUT + "eval_chip.csv")
    jobs = D[[c for c in D if c.startswith("in_")]].rename(columns=lambda c: c[3:]).to_dict("records")
    with Pool(int(sys.argv[1])) as p:
        res = p.map(run, jobs, chunksize=1)
    pd.DataFrame(res).to_csv(OUT + sys.argv[2], index=False)
