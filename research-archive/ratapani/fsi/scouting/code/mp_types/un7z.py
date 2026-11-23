"""Decode a single-file 7z archive whose one coder is LZMA2 (dict prop 0x18 = 16 MB), using stdlib lzma raw mode."""
import lzma, sys
src, dst, packsize = sys.argv[1], sys.argv[2], int(sys.argv[3])
d = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[{'id': lzma.FILTER_LZMA2, 'dict_size': 16 << 20}])
with open(src, 'rb') as f, open(dst, 'wb') as o:
    f.seek(32); left = packsize; n = 0
    while left > 0:
        b = f.read(min(1 << 20, left)); left -= len(b)
        out = d.decompress(b); o.write(out); n += len(out)
print('wrote', n)
