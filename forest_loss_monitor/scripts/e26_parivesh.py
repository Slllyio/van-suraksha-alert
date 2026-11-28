"""MP forest-clearance proposals from the public Parivesh search page (no login, no CAPTCHA), politely, one request per second.
Output: ground_truth/parivesh_mp_proposals.csv. Usage: e26_parivesh.py probe | run"""
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse

import pandas as pd

from common import ROOT

URL = "https://forestsclearance.nic.in/Online_Status.aspx"
GT = ROOT / "ground_truth"
P = "ctl00$ContentPlaceHolder1$"
UA = {"User-Agent": "Mozilla/5.0 forest-loss research; single-user, low rate"}


def hidden(html):
    return {k: v for k, v in re.findall(r'<input[^>]*type="hidden"[^>]*name="([^"]+)"[^>]*value="([^"]*)"', html)}


class Curl:
    """curl validates this site's certificate through the Windows store; Python's certifi bundle lacks its chain."""

    def __init__(self):
        self.jar = tempfile.NamedTemporaryFile(suffix=".txt", delete=False).name

    def fetch(self, body=None):
        cmd = ["curl", "-sS", "-m", "180", "-A", UA["User-Agent"], "-b", self.jar, "-c", self.jar, URL]
        if body is not None:
            cmd += ["--data-binary", "@-"]
        r = subprocess.run(cmd, input=body.encode() if body else None, capture_output=True, check=True)
        return r.stdout.decode("utf-8", "ignore")


def post(s, html, **fields):
    data = hidden(html)
    data.update(fields)
    time.sleep(1)
    return s.fetch(urllib.parse.urlencode(data))


def search(s, year, status="Approved"):
    html = s.fetch()
    base = {P + "RadioButtonList1": "New", P + "ddlyear": str(year), P + "ddlcategory": "-Select All-", P + "DropDownList1": status,
            P + "ddl1": "Select", P + "ddl3": "MP", P + "txtsearch": ""}
    # the state list posts back on change; then the search button
    html = post(s, html, __EVENTTARGET=P + "ddl3", __EVENTARGUMENT="", **base)
    return post(s, html, **{P + "Button1": "Search"}, **base), base


def tables(html):
    """All HTML tables with at least 5 columns, as rows of text and links."""
    out = []
    for t in re.findall(r"<table[^>]*>.*?</table>", html, re.S):
        rows = []
        for tr in re.findall(r"<tr[^>]*>.*?</tr>", t, re.S):
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
            rows.append([re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip() for c in cells])
        if rows and max(len(r) for r in rows) >= 5:
            out.append(rows)
    return out


def main():
    s = Curl()
    if sys.argv[1] == "probe":
        html, _ = search(s, 2022)
        open(GT / "raw" / "fc_probe.html", "w", encoding="utf-8").write(html)
        print(len(html), "captcha" in html.lower())
        for t in tables(html):
            print(len(t), t[0][:14])
            print(t[1][:14] if len(t) > 1 else "")
        print(re.findall(r"(?:Total|Records?|No\.? of)[^<]{0,50}", html)[:6])
        return
    rows = []
    for y in range(2015, 2027):
        html, base = search(s, y)
        page, grid = 1, ""
        while True:
            ts = sorted(tables(html), key=len, reverse=True)
            if not ts:
                break
            head = ts[0][0]
            new = [dict(zip(head, r), query_year=y, page=page) for r in ts[0][1:] if len(r) == len(head) and r[0].isdigit()]
            assert all(r["State Name"] == "Madhya Pradesh" and r["Proposal Status"] == "APPROVED" for r in new), "filters lost"
            rows += new
            page += 1
            m = re.search(r"__doPostBack\(&#39;([^&]+)&#39;,&#39;Page\$%d&#39;\)" % page, html) or re.search(r"__doPostBack\('([^']+)','Page\$%d'\)" % page, html)
            if not m:
                break
            html = post(s, html, __EVENTTARGET=m.group(1), __EVENTARGUMENT=f"Page${page}", **base)  # keep the filters across pages
        print(y, "pages", page, "rows so far", len(rows), flush=True)
    d = pd.DataFrame(rows).drop_duplicates("Proposal No.")
    d.to_csv(GT / "parivesh_mp_proposals.csv", index=False)
    print(d.shape, d.columns.tolist())


if __name__ == "__main__":
    main()
