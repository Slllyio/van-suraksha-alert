"""Read the appended-gzip outline file, skipping any batch (gzip member) cut short by a killed run.
Usage: from read_geom import read_geom; G = read_geom(path)  -> DataFrame event_id, geometry (WKT)."""
import zlib, io, pandas as pd


def read_geom(path):
    raw = open(path, "rb").read()
    starts = [i for i in range(len(raw) - 2) if raw[i] == 0x1f and raw[i + 1] == 0x8b and raw[i + 2] == 8]
    out, bad = [], 0
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(raw)
        try:
            d = zlib.decompressobj(16 + zlib.MAX_WBITS)
            txt = d.decompress(raw[s:e]).decode()
            if not d.eof:
                raise ValueError("truncated")
        except Exception:
            bad += 1
            continue
        if txt.startswith("event_id,geometry"):
            txt = txt.split("\n", 1)[1]
        out.append(txt)
    G = pd.read_csv(io.StringIO("event_id,geometry\n" + "".join(out)))
    G.attrs["bad_batches"] = bad
    return G.drop_duplicates("event_id", keep="last")


def read_hist_geom(out_dir="/mnt/project-files/fire-alert-scars/mp/out", name="scars_mp_hist"):
    """All MP history outlines: the clean one-piece file of everything written before 18 Oct 07:00Z
    (<name>_geom_part1.csv.gz, rebuilt from the old appended file, which is kept as <name>_geom.backup_2026-10-18.csv.gz)
    plus one small file per batch in <name>_geom/. A later outline for the same event (a redo) wins."""
    import glob, os
    parts = [pd.read_csv(os.path.join(out_dir, f"{name}_geom_part1.csv.gz"))]
    parts += [pd.read_csv(f) for f in sorted(glob.glob(os.path.join(out_dir, f"{name}_geom", "*.csv.gz")))]
    return pd.concat(parts, ignore_index=True).drop_duplicates("event_id", keep="last")
