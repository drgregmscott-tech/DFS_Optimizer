import subprocess, sys
from concurrent.futures import ThreadPoolExecutor
SRC='C:/Users/gmsco/Desktop/DFS_Optimizer'
jobs=[(y,w) for y in (2020,2021) for w in range(2,18)]
def run(a):
    y,w=a
    return subprocess.run([sys.executable,'hist_one.py',str(y),str(w),'sbL','hist_proj_clean',SRC],capture_output=True,text=True).stdout.strip()
with ThreadPoolExecutor(8) as ex:
    for r in ex.map(run,jobs): print(r,flush=True)
print('ALLDONE')
