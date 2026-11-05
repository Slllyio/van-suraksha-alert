"""Watch for the end of Restricted Mode, then move the run to 10 threads; fall back to 3 if refusals return. Never changes the tier.
A probe = 8 parallel small requests every 10 minutes; a clean probe has no refusals and a median under 60 s. Two clean probes in a row raise the run.
Cloud usage figures are not read here, so refusals stand in for the 80% guard. Log: work/watch.log"""
import statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import ee

from common import WORK, init

LOG = WORK / "watch.log"
RUN = "e33_map10m"


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"{datetime.now():%m-%d %H:%M} {msg}\n")


def one(i):
    t = time.time()
    try:
        ee.Number(i).add(1).getInfo()
        ee.Image(i).reduceRegion(ee.Reducer.first(), ee.Geometry.Point(78 + i * .01, 23), 30).getInfo()
        return time.time() - t, False
    except Exception as e:
        return time.time() - t, "Too Many" in str(e)


def probe():
    with ThreadPoolExecutor(8) as ex:
        r = list(ex.map(one, range(8)))
    return statistics.median(a for a, _ in r), sum(b for _, b in r)


def restart(threads):
    ps = 'Get-CimInstance Win32_Process -Filter "Name=\'python.exe\'" | Where-Object {$_.CommandLine -match \'' + RUN + '\'} | ForEach-Object {Stop-Process -Id $_.ProcessId -Force}'
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)
    time.sleep(5)
    start = f"Start-Process cmd.exe -ArgumentList '/c cd /d E:\\FIRE\\forest_loss_monitor\\scripts && python e33_map10m.py state {threads} >> E:\\FIRE\\forest_loss_monitor\\work\\map10s3.log 2>&1' -WindowStyle Hidden"
    subprocess.run(["powershell", "-NoProfile", "-Command", start], capture_output=True)
    log(f"run restarted with {threads} threads")


def main():
    init()
    threads, clean, bad = 3, 0, 0
    log("watch started")
    while True:
        try:
            med, refused = probe()
        except Exception as e:
            log("probe error " + str(e)[:120])
            time.sleep(600)
            continue
        log(f"threads {threads} median {med:.1f}s refused {refused}/8")
        ok = refused == 0 and med < 60
        clean, bad = (clean + 1, 0) if ok else (0, bad + 1)
        if threads == 3 and clean >= 2:
            restart(10)
            threads = 10
        elif threads == 10 and bad >= 3:
            restart(3)
            threads, clean = 3, 0
        time.sleep(600)


if __name__ == "__main__":
    main()
