"""One active run per worker; start extra workers only within a measured resource budget."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.request
import uuid
from .bridge import Bridge,provision
from .simulation import run,Cancelled

def execute(manifest,run_id,progress=lambda _:None,cancelled=lambda:False):
    name='stonks_run_'+uuid.UUID(run_id).hex;bridge=None;created=False
    try:
        url=provision('create',name)['url'];created=True;bridge=Bridge(url)
        return run(manifest,bridge,progress,cancelled)
    finally:
        if bridge:bridge.close()
        if created:provision('drop',name)

def api(route,body,token=None):
    base=os.environ.get('RESEARCH_API_URL','http://127.0.0.1:3004').rstrip('/')
    headers={'Content-Type':'application/json','x-research-key':os.environ['RESEARCH_WORKER_KEY']}
    if token:headers['x-run-token']=token
    request=urllib.request.Request(base+'/research-worker/'+route,data=json.dumps(body,allow_nan=False).encode(),headers=headers)
    with urllib.request.urlopen(request,timeout=20) as response:
        data=response.read();return json.loads(data) if data else None

def work_once():
    job=api('claim',{})
    if not job:return False
    stop=threading.Event();cancel=threading.Event();state={'tick':0};lost=[]
    def heartbeat():
        while not stop.is_set():
            try:
                response=api(job['id']+'/heartbeat',dict(state),job['token'])
                if response['cancel_requested']:cancel.set()
            except Exception as error:lost.append(str(error));cancel.set();return
            stop.wait(10)
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    status='COMPLETED';result=None;error=''
    try:
        result=execute(job['manifest'],job['id'],lambda p:state.update(p),cancel.is_set)
        result['versions']={'python':os.sys.version.split()[0], 'strategyRegistry':os.environ.get('STONKS_STRATEGY_REGISTRY','{}')}
        root=Path(os.environ['STONKS_EXCHANGE_DIR'])
        for label,cwd in [('exchange',root),('simulation',Path(__file__).resolve().parent.parent)]:
            r=subprocess.run(['git','rev-parse','HEAD'],cwd=cwd,capture_output=True,text=True)
            result['versions'][label]=r.stdout.strip() if r.returncode==0 else 'unversioned'
    except Cancelled as e:status='CANCELLED';error=str(e)
    except Exception as e:status='FAILED';error=str(e)
    finally:stop.set();thread.join(timeout=25)
    if lost:raise RuntimeError('Worker lease lost: '+lost[0])
    api(job['id']+'/finish',{'status':status,'result':result,'error':error},job['token'])
    print(json.dumps({'runId':job['id'],'status':status}),flush=True)
    return True

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest');parser.add_argument('--output');parser.add_argument('--once',action='store_true');args=parser.parse_args()
    if args.manifest:
        if not args.output:parser.error('--output required with --manifest')
        result=execute(json.loads(Path(args.manifest).read_text()),str(uuid.uuid4()))
        Path(args.output).write_text(json.dumps(result,indent=2,allow_nan=False));return
    while True:
        did=work_once()
        if args.once:return
        if not did:time.sleep(2)

if __name__=='__main__':main()
