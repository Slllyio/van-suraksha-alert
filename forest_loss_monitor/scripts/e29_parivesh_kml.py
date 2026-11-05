"""For each approved MP proposal, read the public Part-I report and download the KMLs of the diverted land (segments, patches, mining lease).
Compensatory afforestation KMLs are listed but not downloaded. Every file is checked to really be KML. One request per second, resumable.
Output: ground_truth/parivesh_kml_manifest.csv, ground_truth/parivesh_kml/*.kml"""
import csv
import re
import subprocess
import time
import urllib.parse

import pandas as pd

from common import ROOT

GT = ROOT / "ground_truth"
BASE = "https://forestsclearance.nic.in/"
UA = "Mozilla/5.0 forest-loss research; single-user, low rate"
MANIFEST = GT / "parivesh_kml_manifest.csv"
KML = GT / "parivesh_kml"
LINK = re.compile(r"""href=['"]\.\./DownloadPdfFile\.aspx\?FileName=([^'"&]+\.km[lz])&(?:amp;)?FilePath=([^'"]+)['"]""", re.I)
TYPE = re.compile(r"""testmap1\.aspx\?type=([^&'"]+)&(?:amp;)?fname=([^&'"]+)""")


def get(url, path=None):
    cmd = ["curl", "-sS", "-m", "120", "-A", UA, url] + (["-o", str(path)] if path else [])
    r = subprocess.run(cmd, capture_output=True)
    time.sleep(1)
    return r.stdout.decode("utf-8", "ignore") if not path else r.returncode == 0


def is_kml(path):
    b = open(path, "rb").read(600)
    return b[:2] == b"PK" or b"<kml" in b.lower()


def main():
    KML.mkdir(exist_ok=True)
    d = pd.read_csv(GT / "parivesh_mp_proposals.csv")
    seen = set(pd.read_csv(MANIFEST).proposal) if MANIFEST.exists() else set()
    new = not MANIFEST.exists()
    good = bad = 0
    with open(MANIFEST, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["proposal", "n", "fname", "type", "folder", "saved", "ok"])
        for i, p in enumerate(d["Proposal No."]):
            if p in seen:
                continue
            h = get(BASE + "viewreport.aspx?pid=" + urllib.parse.quote(p, safe="/"))
            types = {b: a for a, b in TYPE.findall(h)}
            links = list(dict.fromkeys(LINK.findall(h)))
            if not links:
                w.writerow([p, "", "", "", "", "", 0])
            for n, (name, folder) in enumerate(links[:15]):
                t = types.get(name, "")
                saved, ok = "", 0
                if t != "cak":
                    out = KML / f"{re.sub(r'[^A-Za-z0-9]', '_', p)}_{n}{name[-4:].lower()}"
                    q = urllib.parse.urlencode(dict(FileName=name, FilePath=folder.replace("../", "")), safe="/")
                    get(BASE + "DownloadPdfFile.aspx?" + q, out)
                    ok = int(out.exists() and is_kml(out))
                    good += ok
                    bad += 1 - ok
                    saved = out.name if ok else ""
                    if not ok and out.exists():
                        out.unlink()
                w.writerow([p, n, name, t, folder, saved, ok])
            f.flush()
            if i % 25 == 0:
                print(i, p, "good", good, "bad", bad, flush=True)
    print("FINISHED good", good, "bad", bad)


if __name__ == "__main__":
    main()
