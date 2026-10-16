#!/usr/bin/env python3
"""Build twice, compare, and describe an artifact. No publishing or networking."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

def run(*args, env=None):
    return subprocess.check_output(args, env=env, text=True).strip()

pin=json.loads(Path('downstream/UPSTREAM.json').read_text())
if run('go','env','GOVERSION')!='go'+pin['go']:
    raise SystemExit('Use the exact pinned official Go toolchain')
subprocess.run(['git','diff','--exit-code'],check=True,stdout=subprocess.DEVNULL)
go=str(Path(run('go','env','GOROOT'))/'bin/go')
commit=run('git','rev-parse','HEAD')
when=run('git','show','-s','--format=%cI','HEAD')
arch=run('go','env','GOARCH')
version=pin['downstream_version']+'+'+commit[:12]
env={**os.environ,'CGO_ENABLED':'0','GOOS':'linux','GOARCH':arch,
     'GOFLAGS':'','GOEXPERIMENT':'','GOTOOLCHAIN':'local'}
flags=f'-s -w -buildid= -X github.com/metacubex/mihomo/constant.Version={version} -X github.com/metacubex/mihomo/constant.BuildTime={when}'
out=Path('dist');out.mkdir(exist_ok=True)
binary=out/f'mihomo-linux-{arch}'
subprocess.run([go,'build','-mod=readonly','-trimpath','-buildvcs=false','-tags','with_gvisor','-ldflags',flags,'-o',str(binary),'.'],env=env,check=True)
with tempfile.TemporaryDirectory() as td:
    repeat=Path(td)/'mihomo'
    subprocess.run([go,'build','-mod=readonly','-trimpath','-buildvcs=false','-tags','with_gvisor','-ldflags',flags,'-o',str(repeat),'.'],env=env,check=True)
    if binary.read_bytes()!=repeat.read_bytes():raise SystemExit('Reproducibility comparison failed')
metadata={'upstream':pin,'source_commit':commit,'source_time':when,'version':version,
          'go_version':run(go,'version'),'architecture':arch,'cgo':False,
          'tags':['with_gvisor'],'trimpath':True,'buildvcs':False,
          'reproducibility':'two byte-identical builds on this runner; not an independent-builder attestation',
          'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
          'go_sum_sha256':hashlib.sha256(Path('go.sum').read_bytes()).hexdigest()}
(out/f'build-info-{arch}.json').write_text(json.dumps(metadata,indent=2)+'\n')
stream=run(go,'list','-m','-json','all',env=env);dec=json.JSONDecoder();modules=[]
while stream:
    m,n=dec.raw_decode(stream);stream=stream[n:].lstrip();modules.append(m)
components=[]
for m in modules:
    if m.get('Main'):continue
    actual=m.get('Replace',m)
    components.append({'type':'library','name':actual['Path'],'version':actual['Version'],
                       'purl':f'pkg:golang/{actual["Path"]}@{actual["Version"]}',
                       'properties':[{'name':'requested-module','value':m['Path']}]})
bom={'bomFormat':'CycloneDX','specVersion':'1.6','version':1,
     'metadata':{'component':{'type':'application','name':'mihomo-dns-downstream','version':version},
                 'properties':[{'name':'scope','value':'Go module inventory; includes unused modules, excludes OS and Go standard-library component detail'}]},
     'components':components}
(out/f'sbom-{arch}.cdx.json').write_text(json.dumps(bom,indent=2)+'\n')
subprocess.run(['git','archive','--format=tar.gz','-o',str(out/f'source-{arch}.tar.gz'),'HEAD'],check=True)
files=[binary,out/f'build-info-{arch}.json',out/f'sbom-{arch}.cdx.json',out/f'source-{arch}.tar.gz']
(out/f'SHA256SUMS-{arch}').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in files))
print(json.dumps(metadata,indent=2))
