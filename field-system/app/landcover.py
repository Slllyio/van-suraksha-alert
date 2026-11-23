"""Forest share around a fire point from ESA WorldCover 10 m (2021), read straight from its public
cloud-optimised GeoTIFFs with HTTP range requests: only the 1024 x 1024 blocks a point needs are fetched.

FSI keeps only alerts inside Recorded Forest Area + forest cover. MP beats also cover farmland,
so without this most dry-season and Oct-Nov points inside beats are crop burning.
"""
import io, math, threading
from collections import OrderedDict
import numpy as np
import requests
import tifffile

URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
TREE, SHRUB, CROP = 10, 20, 40
_lock = threading.Lock()


class _HTTPFile(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos, self.ses = url, 0, requests.Session()
        self.size = int(self.ses.head(url, timeout=60).headers["Content-Length"])

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos

    def seek(self, o, whence=0):
        self.pos = o if whence == 0 else (self.pos + o if whence == 1 else self.size + o)
        return self.pos

    def readinto(self, b):
        n = len(b)
        if n == 0 or self.pos >= self.size:
            return 0
        d = self.ses.get(self.url, headers={"Range": f"bytes={self.pos}-{self.pos + n - 1}"}, timeout=60).content
        b[:len(d)] = d
        self.pos += len(d)
        return len(d)


class WorldCover:
    def __init__(self, max_blocks=400):
        self.files, self.blocks, self.max_blocks = {}, OrderedDict(), max_blocks

    def _page(self, tile):
        if tile not in self.files:
            fh = io.BufferedReader(_HTTPFile(URL.format(tile=tile)), buffer_size=1 << 16)
            self.files[tile] = (fh, tifffile.TiffFile(fh).pages[0])
        return self.files[tile]

    def _block(self, tile, bi, bj):
        key = (tile, bi, bj)
        if key in self.blocks:
            self.blocks.move_to_end(key)
            return self.blocks[key]
        fh, page = self._page(tile)
        n_across = math.ceil(page.shape[1] / page.tilewidth)
        idx = bi * n_across + bj
        fh.seek(page.dataoffsets[idx])
        data = fh.read(page.databytecounts[idx])
        arr = page.decode(data, idx)[0].reshape(page.tilelength, page.tilewidth)
        self.blocks[key] = arr
        if len(self.blocks) > self.max_blocks:
            self.blocks.popitem(last=False)
        return arr

    def share(self, lat, lon, radius_km):
        """(tree, tree+shrub) share of 10 m pixels within radius_km of the point."""
        out = self.classes(lat, lon, radius_km)
        return None if out is None else (float((out == TREE).mean()), float(np.isin(out, (TREE, SHRUB)).mean()))

    def crop_share(self, lat, lon, radius_km):
        """Cropland share of 10 m pixels within radius_km of the point."""
        out = self.classes(lat, lon, radius_km)
        return None if out is None else float((out == CROP).mean())

    def classes(self, lat, lon, radius_km):
        """WorldCover class of every 10 m pixel within radius_km of the point (None outside the tiles)."""
        with _lock:
            la0, lo0 = 3 * math.floor(lat / 3), 3 * math.floor(lon / 3)
            tile = f"N{la0:02d}E{lo0:03d}"
            res = 1 / 12000                      # 10 m pixels, 3 degree tiles of 36000 px
            row, col = (la0 + 3 - lat) / res, (lon - lo0) / res
            r_px = radius_km / 111.32 / res
            vals = []
            for i in range(int(row - r_px), int(row + r_px) + 1):
                for j in range(int(col - r_px * 1.0), int(col + r_px) + 1):
                    if (i - row) ** 2 + (j - col) ** 2 > r_px ** 2 or not (0 <= i < 36000 and 0 <= j < 36000):
                        continue
                    vals.append((i, j))
            if not vals:
                return None
            ij = np.array(vals)
            out = np.empty(len(ij), np.uint8)
            bi, bj = ij[:, 0] // 1024, ij[:, 1] // 1024
            for key in set(zip(bi.tolist(), bj.tolist())):
                m = (bi == key[0]) & (bj == key[1])
                blk = self._block(tile, *key)
                out[m] = blk[ij[m, 0] % 1024, ij[m, 1] % 1024]
            return out
