# Minimal ctypes reader for HDF5/netCDF4 files using system libhdf5_serial (no python packages needed).
import ctypes as C, numpy as np
L=C.CDLL('libhdf5_serial.so.103'); L.H5open()
hid=C.c_int64
for f,res,args in [('H5Fopen',hid,[C.c_char_p,C.c_uint,hid]),('H5Dopen2',hid,[hid,C.c_char_p,hid]),('H5Dget_space',hid,[hid]),
  ('H5Sget_simple_extent_dims',C.c_int,[hid,C.POINTER(C.c_ulonglong),C.POINTER(C.c_ulonglong)]),('H5Screate_simple',hid,[C.c_int,C.POINTER(C.c_ulonglong),C.c_void_p]),
  ('H5Sselect_hyperslab',C.c_int,[hid,C.c_int,C.POINTER(C.c_ulonglong),C.c_void_p,C.POINTER(C.c_ulonglong),C.c_void_p]),
  ('H5Dread',C.c_int,[hid,hid,hid,hid,hid,C.c_void_p]),('H5Dclose',C.c_int,[hid]),('H5Sclose',C.c_int,[hid]),('H5Fclose',C.c_int,[hid]),
  ('H5Aget_num_attrs',C.c_int,[hid]),('H5Aopen_idx',hid,[hid,C.c_uint]),('H5Aget_name',C.c_ssize_t,[hid,C.c_size_t,C.c_char_p]),
  ('H5Aget_type',hid,[hid]),('H5Tget_class',C.c_int,[hid]),('H5Aget_space',hid,[hid]),('H5Sget_simple_extent_npoints',C.c_ssize_t,[hid]),
  ('H5Aread',C.c_int,[hid,hid,C.c_void_p]),('H5Aclose',C.c_int,[hid]),('H5Tclose',C.c_int,[hid]),('H5Tget_size',C.c_size_t,[hid]),('H5Tis_variable_str',C.c_int,[hid]),
  ('H5Oopen',hid,[hid,C.c_char_p,hid]),('H5Oclose',C.c_int,[hid])]:
    fn=getattr(L,f); fn.restype=res; fn.argtypes=args
T={k:hid.in_dll(L,'H5T_NATIVE_%s_g'%k).value for k in ['USHORT','DOUBLE','FLOAT','INT','SHORT','UCHAR','LLONG','UINT']}
def attrs(fid,obj='/'):
    o=L.H5Oopen(fid,obj.encode(),0); out={}
    for i in range(L.H5Aget_num_attrs(o)):
        a=L.H5Aopen_idx(o,i); b=C.create_string_buffer(256); L.H5Aget_name(a,256,b); t=L.H5Aget_type(a); cl=L.H5Tget_class(t)
        sp=L.H5Aget_space(a); n=L.H5Sget_simple_extent_npoints(sp)
        if cl in (0,1):  # integer/float -> double
            arr=np.zeros(max(n,1),np.float64); L.H5Aread(a,T['DOUBLE'],arr.ctypes.data); out[b.value.decode()]=arr if n>1 else arr[0]
        elif cl==3:
            if L.H5Tis_variable_str(t):
                p=C.c_char_p(); L.H5Aread(a,t,C.byref(p)); out[b.value.decode()]=p.value.decode(errors='replace') if p.value else ''
            else:
                sz=L.H5Tget_size(t); s=C.create_string_buffer(sz*max(n,1)); L.H5Aread(a,t,s); out[b.value.decode()]=s.raw.split(b'\0')[0].decode(errors='replace')
        L.H5Sclose(sp); L.H5Tclose(t); L.H5Aclose(a)
    L.H5Oclose(o); return out
def read(fid,name,off=None,cnt=None,dtype='USHORT'):
    d=L.H5Dopen2(fid,name.encode(),0); s=L.H5Dget_space(d); dims=(C.c_ulonglong*2)(); L.H5Sget_simple_extent_dims(s,dims,None)
    if off is None: off=(0,0); cnt=(dims[0],dims[1])
    o=(C.c_ulonglong*2)(*off); c=(C.c_ulonglong*2)(*cnt); L.H5Sselect_hyperslab(s,0,o,None,c,None)
    m=L.H5Screate_simple(2,c,None); npd={'USHORT':np.uint16,'DOUBLE':np.float64,'FLOAT':np.float32,'SHORT':np.int16,'UCHAR':np.uint8}[dtype]
    arr=np.zeros(cnt,npd); r=L.H5Dread(d,T[dtype],m,s,0,arr.ctypes.data); L.H5Sclose(m); L.H5Sclose(s); L.H5Dclose(d)
    assert r>=0, 'read failed'; return arr,(dims[0],dims[1])
def fopen(p): return L.H5Fopen(p.encode(),0,0)
