#!/usr/bin/env python3
"""Exercise proposed managed API controls on an isolated loopback binary."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    checks=[]
    def record(name,ok,detail):checks.append({'test':name,'passed':bool(ok),'observed':detail})
    with tempfile.TemporaryDirectory(prefix='managed-api-') as td:
        root=Path(td);cfg={'mode':'rule','external-controller':'127.0.0.1:19390','rules':['RULE-SET,fixture,DIRECT','MATCH,DIRECT'],
            'rule-providers':{'fixture':{'type':'inline','behavior':'domain','payload':['example.org']}},'proxy-groups':[{'name':'TEST','type':'select','proxies':['DIRECT']}],
            'dns':{'enable':True,'listen':'127.0.0.1:19391','disable-cache':True,
            'nameserver':['127.0.0.1:19392'],'default-nameserver':['127.0.0.1:19392']}}
        path=root/'config.json';path.write_text(json.dumps(cfg))
        env={**os.environ,'MIHOMO_MANAGED_DNS':'1'}
        proc=subprocess.Popen([str(a.binary.resolve()),'-d',td,'-f',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env)
        def request(method,target,body=None):
            req=urllib.request.Request('http://127.0.0.1:19390'+target,
                data=None if body is None else json.dumps(body).encode(),method=method,
                headers={'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req,timeout=2) as response:return response.status
            except urllib.error.HTTPError as error:return error.code
        try:
            for _ in range(200):
                try:
                    if request('GET','/version')==200 and request('GET','/proxies/TEST')==200 and request('GET','/providers/rules/fixture')==200:break
                    time.sleep(.05)
                except OSError:time.sleep(.05)
            record('read-only version API available',request('GET','/version')==200,{})
            for method,target in [('PUT','/configs'),('PATCH','/configs'),('POST','/upgrade'),('POST','/restart'),('POST','/configs/geo'),('POST','/upgrade/geo'),('PATCH','/rules/disable'),('PUT','/providers/rules/fixture')]:
                status=request(method,target,{})
                record(method+' '+target+' rejected before mutation',status==409,{'status':status})
            selection=request('PUT','/proxies/TEST',{'name':'DIRECT'})
            record('proxy selection retained',selection==204,{'status':selection})
            record('process survives rejected mutations',proc.poll() is None and request('GET','/version')==200,{})
        finally:proc.terminate();proc.wait(timeout=5)
        cfg['dns']['disable-cache']=False;path.write_text(json.dumps(cfg))
        managed=subprocess.run([str(a.binary.resolve()),'-t','-d',td,'-f',str(path)],env=env,capture_output=True,timeout=10)
        unmanaged=subprocess.run([str(a.binary.resolve()),'-t','-d',td,'-f',str(path)],env={**os.environ,'MIHOMO_MANAGED_DNS':''},capture_output=True,timeout=10)
        record('managed startup refuses omitted behavior',managed.returncode!=0,{'exit':managed.returncode})
        record('unmanaged parser behavior preserved',unmanaged.returncode==0,{'exit':unmanaged.returncode})
    result={'scope':__doc__,'binary_sha256':hashlib.sha256(a.binary.read_bytes()).hexdigest(),
        'checks':checks,'passed':sum(c['passed'] for c in checks),'total':len(checks),'release_artifact':False,'router_execution':False}
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'passed':result['passed'],'total':result['total']}))
    if result['passed']!=result['total']:raise SystemExit(1)

if __name__=='__main__':main()
