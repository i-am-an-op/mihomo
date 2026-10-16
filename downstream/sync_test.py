import argparse
import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def git(path,*args):
    return subprocess.check_output(['/usr/bin/git','-C',str(path),*args],text=True,stderr=subprocess.PIPE).strip()
def write(path,text,mode=0o644):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text);path.chmod(mode)

def sync_fixture(root,conflict=False):
    base=root/'base';base.mkdir(parents=True)
    git(base,'init','-b','dns-maintained');git(base,'config','user.name','Fixture');git(base,'config','user.email','fixture@example.invalid')
    write(base/'file','base\n');write(base/'.github/workflows/downstream-ci.yml','trusted workflow\n')
    git(base,'add','.');git(base,'commit','-m','base');sha=git(base,'rev-parse','HEAD')
    write(base/'downstream/UPSTREAM.json',json.dumps({'tag':'v1.0.0','commit':sha,'downstream_version':'v1.0.0-dns.1-rc.1'}))
    git(base,'add','.');git(base,'commit','-m','pin')
    upstream=root/'upstream';git(root,'clone',str(base),str(upstream))
    git(upstream,'config','user.name','Fixture');git(upstream,'config','user.email','fixture@example.invalid')
    write(upstream/'file','upstream\n');write(upstream/'.github/workflows/new-unreviewed.yml','must not execute\n')
    git(upstream,'add','.');git(upstream,'commit','-m','new stable');git(upstream,'tag','v1.1.0')
    if conflict:write(base/'file','downstream conflict\n');git(base,'add','.');git(base,'commit','-m','conflict')
    origin=root/'origin.git';git(root,'clone','--bare',str(base),str(origin))
    work=root/'work';git(root,'clone',str(origin),str(work))
    write(root/'latest.json',json.dumps({'tag_name':'v1.1.0','draft':False,'prerelease':False}))
    write(root/'bin/gh','''#!/usr/bin/python3
import json,os,pathlib,subprocess,sys
p=pathlib.Path(os.environ['FIXTURE_ROOT']);a=sys.argv[1:]
with (p/'gh-calls').open('a') as f:f.write(json.dumps(a)+'\\n')
if a[0]=='api':
 if (p/'fail-api').exists():sys.exit(42)
 print((p/'latest.json').read_text())
elif a[:2]==['workflow','run']:
 if (p/'fail-dispatch').exists():sys.exit(43)
 (p/'dispatched').write_text('yes')
elif a[:2]==['run','list']:
 head=a[a.index('--commit')+1]
 print(json.dumps([{'headSha':head,'status':'completed','conclusion':'success'}] if (p/'ci-success').exists() else []))
else:sys.exit(99)
''',0o755)
    write(root/'bin/git','''#!/usr/bin/python3
import os,sys
a=sys.argv[1:]
if a and a[0]=='fetch':
 a=[os.environ['FIXTURE_ROOT']+'/upstream' if x=='https://github.com/MetaCubeX/mihomo.git' else x for x in a]
if any('https://' in x or 'http://' in x for x in a):sys.exit(99)
os.execv('/usr/bin/git',['git',*a])
''',0o755)
    env={**os.environ,'PATH':str(root/'bin')+':/usr/bin','FIXTURE_ROOT':str(root),
        'GITHUB_REPOSITORY':'i-am-an-op/mihomo','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null',
        'GITHUB_STEP_SUMMARY':str(root/'summary')}
    return work,origin,env


def main():
    script=ROOT/'downstream/sync_upstream.py'
    def run(work,env):return subprocess.run(['python3',str(script)],cwd=work,env=env,capture_output=True,timeout=30).returncode
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)
        work,origin,env=sync_fixture(p/'dispatch');(p/'dispatch/fail-dispatch').touch()
        assert run(work,env)!=0 and git(origin,'branch','--list','upstream-update/*')
        git(work,'switch','dns-maintained');assert run(work,env)!=0
        (p/'dispatch/fail-dispatch').unlink();(p/'dispatch/ci-success').touch();assert run(work,env)==0
        assert not (work/'.github/workflows/new-unreviewed.yml').exists()
        work,origin,env=sync_fixture(p/'conflict',True);assert run(work,env)!=0 and not git(origin,'branch','--list','upstream-update/*')
        work,origin,env=sync_fixture(p/'api');(p/'api/fail-api').touch();before=git(work,'rev-parse','HEAD');assert run(work,env)!=0 and git(work,'rev-parse','HEAD')==before
        work,origin,env=sync_fixture(p/'moved');pin=json.loads((work/'downstream/UPSTREAM.json').read_text());pin['tag']='v1.1.0';(work/'downstream/UPSTREAM.json').write_text(json.dumps(pin));assert run(work,env)!=0
    print('sync failure/recovery fixtures passed; no external GitHub mutation')
if __name__=='__main__':main()
