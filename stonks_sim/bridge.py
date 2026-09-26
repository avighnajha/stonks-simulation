import json
import os
from pathlib import Path
import queue
import subprocess
import threading

def node_command(script):
    root=Path(os.environ['STONKS_EXCHANGE_DIR']).resolve()
    return [os.environ.get('NODE_BINARY','node'),str(root/'services'/'trading_service'/'dist'/'research'/script)]

def provision(operation, name):
    completed=subprocess.run(node_command('provision.js')+[operation,name],capture_output=True,text=True,timeout=60)
    if completed.returncode: raise RuntimeError(completed.stderr[-1000:])
    return json.loads(completed.stdout)

class Bridge:
    def __init__(self, url):
        # Provisioner credentials are never passed to the Node engine child.
        env={k:v for k,v in os.environ.items() if k not in ('RESEARCH_DATABASE_ADMIN_URL','RESEARCH_WORKER_KEY')}
        env['RUN_DATABASE_URL']=url
        self.process=subprocess.Popen(node_command('engine-adapter.js'),env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1)
        self.responses=queue.Queue();self.stderr=[]
        def read():
            for line in self.process.stdout:self.responses.put(line)
            self.responses.put(None)
        def errors():
            for line in self.process.stderr:self.stderr[:]=[line[-1000:]]
        threading.Thread(target=read,daemon=True).start();threading.Thread(target=errors,daemon=True).start()
    def request(self,op,tick,**payload):
        self.process.stdin.write(json.dumps({'op':op,'tick':tick,**payload},allow_nan=False)+'\n');self.process.stdin.flush()
        try:line=self.responses.get(timeout=45)
        except queue.Empty:raise TimeoutError('Exchange adapter did not respond within 45 seconds')
        if line is None:raise RuntimeError('Exchange adapter exited: '+''.join(self.stderr))
        message=json.loads(line)
        if not message['ok']:raise ValueError(message['error'])
        return message['result']
    def close(self):
        try:
            self.process.stdin.close();self.process.wait(timeout=5)
        except (BrokenPipeError,subprocess.TimeoutExpired):self.process.kill();self.process.wait()
        finally:
            self.process.stdout.close();self.process.stderr.close()
