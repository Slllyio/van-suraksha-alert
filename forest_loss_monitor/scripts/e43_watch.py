"""Watch for the end of Restricted Mode, then move the run to 10 threads; fall back to 3 if refusals return. Never changes the tier.
A probe = 4 parallel real map requests every 10 minutes; a clean probe has no refusals or errors and a median under 120 s. Two clean probes in a row raise the run.
Cloud usage figures are not read here, so refusals stand in for the 80% guard. Log: work/watch.log"""
import json
import statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import ee

from common import WKT, WORK
from e33_map10m import init_retry, jobs, product

LOG = WORK / "watch.log"
RUN = "e33_map10m"
PROBES = [(j[0], j[1], j[2]) for j in jobs(tiles=["r02c03"])[:4]]


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"{datetime.now():%m-%d %H:%M} {msg}\n")


def one(i):
    """A real map request: the run's own expression on 1 km of forest, read with computePixels."""
    s_, r, c = PROBES[i]
    t = time.time()
    x0, y1 = s_.x0 + c * 10, s_.y1 - r * 10
    roi = ee.Geometry.Rectangle([x0, y1 - 1000, x0 + 1000, y1], ee.Projection(WKT), False).transform("EPSG:4326", 10)
    try:
        ee.data.computePixels(dict(expression=product(roi), fileFormat="NPY", grid=dict(dimensions=dict(width=100, height=100), crsWkt=WKT,
                                   affineTransform=dict(scaleX=10, shearX=0, translateX=x0, shearY=0, scaleY=-10, translateY=y1))))
        return time.time() - t, False, ""
    except Exception as e:
        return time.time() - t, "Too Many" in str(e), str(e)[:80]


def probe():
    """Four at once, on top of the run: passes only if there is headroom for more threads."""
    with ThreadPoolExecutor(len(PROBES)) as ex:
        r = list(ex.map(one, range(len(PROBES))))
    return statistics.median(a[0] for a in r), sum(a[1] for a in r), sum(bool(a[2]) for a in r)


def tier():
    try:
        log("project config " + json.dumps(ee.data.getProjectConfig())[:300])
    except Exception as e:
        log("project config not readable: " + str(e)[:150])


def restart(threads):
    ps = 'Get-CimInstance Win32_Process -Filter "Name=\'python.exe\'" | Where-Object {$_.CommandLine -match \'' + RUN + '\'} | ForEach-Object {Stop-Process -Id $_.ProcessId -Force}'
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)
    time.sleep(5)
    start = f"Start-Process cmd.exe -ArgumentList '/c cd /d E:\\FIRE\\forest_loss_monitor\\scripts && python e33_map10m.py state {threads} >> E:\\FIRE\\forest_loss_monitor\\work\\map10s3.log 2>&1' -WindowStyle Hidden"
    subprocess.run(["powershell", "-NoProfile", "-Command", start], capture_output=True)
    log(f"run restarted with {threads} threads")


def main():
    init_retry()
    threads, clean, bad = 2, 0, 0
    log("watch started, real map probes")
    tier()
    while True:
        try:
            med, refused, errors = probe()
        except Exception as e:
            log("probe error " + str(e)[:120])
            time.sleep(600)
            continue
        log(f"threads {threads} median {med:.1f}s refused {refused}/4 errors {errors}/4")
        ok = refused == 0 and errors == 0 and med < 120
        clean, bad = (clean + 1, 0) if ok else (0, bad + 1)
        if threads < 10 and clean >= 2:
            restart(10)
            threads = 10
        elif threads == 10 and bad >= 3:
            restart(3)
            threads, clean = 3, 0
        time.sleep(600)


if __name__ == "__main__":
    main()
