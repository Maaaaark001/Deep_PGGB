"""Generate streaming benchmark data for the paper figure.

Produces work/stream_data.json:
  cores: [{k, lo_ms, hi_ms, null_db}]   null of each 0.5s core vs offline
  head:  [{ms, err_db}]                 error vs offset from stream head
  summary: {len_drift, interior_null_db, head_span_ms, latency_sec}
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np, importlib.util as ilu

def load(n,p):
    s=ilu.spec_from_file_location(n,p); m=ilu.module_from_spec(s); s.loader.exec_module(m); return m

def build():
    dp=load('d','deeppggb/deeppggb.py'); st=load('s','deeppggb/deeppggb_stream.py')
    SRC,DST=44100,88200; N=int(SRC*4.0); CH=2
    t=np.arange(N,dtype=np.float64)/SRC
    x=np.zeros((N,CH))
    for f,a in ((997.,0.4),(4001.,0.25),(12007.,0.15),(18001.,0.1)):
        x[:,0]+=a*np.sin(2*np.pi*f*t); x[:,1]=x[:,0]
    pk=np.abs(x).max(); x*=0.5/pk
    off=dp.resample(x,SRC,DST,block=0.0)
    rs=st.StreamResampler(SRC,DST,channels=CH,core_sec=0.5)
    chunks=[]; CHUNK=int(0.37*SRC)
    for i in range(0,N,CHUNK):
        c=rs.push(x[i:i+CHUNK])
        if c.shape[0]: chunks.append(c)
    tail=rs.flush()
    if tail.shape[0]: chunks.append(tail)
    stream=np.vstack(chunks)
    m=min(stream.shape[0],off.shape[0])
    core_out=int(0.5*DST)
    cores=[]
    for k in range(m//core_out):
        lo=k*core_out; hi=min(lo+core_out,m)
        seg=stream[lo:hi]-off[lo:hi]
        ref=np.sqrt(np.mean(off[lo:hi]**2))
        nd=20*np.log10(ref/np.sqrt(np.mean(seg**2)))
        cores.append({"k":k,"lo_ms":lo/DST*1000,"hi_ms":hi/DST*1000,"null_db":round(float(nd),1)})
    # head zone
    head=[]
    for ms in range(0,120,5):
        lo=int(ms/1000*DST); hi=min(lo+int(0.005*DST),m)
        if hi<=lo: continue
        e=np.abs(stream[lo:hi]-off[lo:hi]).max(axis=1)
        head.append({"ms":ms,"err_db":round(float(20*np.log10(max(e.max(),1e-300)/0.5)),1)})
    # interior null after 200ms
    hh=int(0.2*DST)
    di=stream[hh:]-off[hh:m]
    refi=np.sqrt(np.mean(off[hh:m]**2))
    interior=20*np.log10(refi/np.sqrt(np.mean(di**2)))
    bad=np.where(np.abs(stream[:m]-off[:m]).max(axis=1)>1e-5)[0]
    span=(bad[-1]/DST*1000.0) if bad.size else 0.0
    return {"cores":cores,"head":head,
            "summary":{"len_offline":int(off.shape[0]),"len_stream":int(stream.shape[0]),
                       "len_drift":int(off.shape[0]-stream.shape[0]),
                       "interior_null_db":round(float(interior),1),
                       "head_span_ms":round(float(span),1),
                       "latency_sec":round(float(rs.latency_sec()),3)}}

if __name__=="__main__":
    out=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"work","stream_data.json")
    data=build()
    with open(out,"w") as f: json.dump(data,f,indent=1)
    print("wrote",out)
    print(json.dumps(data["summary"]))
    for c in data["cores"]: print("  core",c["k"],"null %.1f dB"%c["null_db"])
