import requests, io
class RangeFile(io.RawIOBase):
    """Minimal read-only file object over HTTP range requests, with a block cache."""
    def __init__(self, url, block=1<<20):
        self.url=url; self.pos=0; self.block=block; self.cache={}; self.s=requests.Session()
        r=self.s.head(url,timeout=60); self.size=int(r.headers['Content-Length']); self.nreq=0
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos
    def seek(self, off, whence=0):
        self.pos = off if whence==0 else (self.pos+off if whence==1 else self.size+off); return self.pos
    def _blk(self,i):
        if i not in self.cache:
            a=i*self.block; b=min(self.size,a+self.block)-1
            for k in range(4):
                try:
                    r=self.s.get(self.url,headers={'Range':f'bytes={a}-{b}'},timeout=120); r.raise_for_status(); break
                except Exception as e: err=e
            else: raise err
            self.cache[i]=r.content; self.nreq+=1
        return self.cache[i]
    def readinto(self, b):
        n=len(b); 
        if self.pos>=self.size: return 0
        n=min(n,self.size-self.pos); out=bytearray()
        while len(out)<n:
            i=(self.pos+len(out))//self.block; off=(self.pos+len(out))%self.block
            out+=self._blk(i)[off:off+n-len(out)]
        b[:n]=out; self.pos+=n; return n
