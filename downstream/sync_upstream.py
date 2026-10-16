#!/usr/bin/env python3
"""Create a review branch for a new stable upstream release. Never deploy or merge it.

Run only from the trusted default branch. This script never executes fetched code.
On conflicts it fails visibly; the maintainer resolves them on the candidate branch.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

def run(*args):
    return subprocess.check_output(args,text=True).strip()

repo=os.environ.get('GITHUB_REPOSITORY','i-am-an-op/mihomo')
if repo!='i-am-an-op/mihomo':raise SystemExit('Unexpected destination repository')
pin=json.loads(Path('downstream/UPSTREAM.json').read_text())
latest=json.loads(run('gh','api','repos/MetaCubeX/mihomo/releases/latest'))
tag=latest['tag_name']
if latest['draft'] or latest['prerelease'] or not re.fullmatch(r'v\d+\.\d+\.\d+',tag):
    raise SystemExit('Unexpected upstream stable release format')
run('git','fetch','--no-tags','https://github.com/MetaCubeX/mihomo.git','refs/tags/'+tag)
upstream=run('git','rev-parse','FETCH_HEAD^{commit}')
if tag==pin['tag']:
    if upstream!=pin['commit']:raise SystemExit('Pinned upstream tag moved; manual investigation required')
    print('Already tracking latest stable release:',tag);raise SystemExit(0)
if tuple(map(int,tag[1:].split('.'))) < tuple(map(int,pin['tag'][1:].split('.'))):
    raise SystemExit('Upstream latest points to an older version; manual investigation required')
branch='upstream-update/'+tag
existing=run('git','ls-remote','--heads','origin','refs/heads/'+branch)
if existing:
    head=existing.split()[0]
    runs=json.loads(run('gh','run','list','--repo',repo,'--workflow','downstream-ci.yml','--branch',branch,'--commit',head,'--json','headSha,status,conclusion'))
    if not any(r.get('headSha')==head and r.get('conclusion')=='success' for r in runs):
        raise SystemExit('Existing update branch lacks successful CI on its exact head; review and dispatch/re-run CI manually: '+branch)
    print('Tested existing update branch awaits owner review:',branch);raise SystemExit(0)
base=run('git','rev-parse','HEAD')
run('git','switch','-c',branch)
merge=subprocess.run(['git','-c','core.hooksPath=/dev/null','-c','user.name=github-actions[bot]','-c','user.email=41898282+github-actions[bot]@users.noreply.github.com','merge','--no-commit','--no-ff',upstream],capture_output=True,text=True)
if merge.returncode:
    conflicts=run('git','diff','--name-only','--diff-filter=U')
    merge_head=Path(run('git','rev-parse','--git-path','MERGE_HEAD'))
    if merge_head.exists():run('git','merge','--abort')
    # Report the actual cause even when merge never created MERGE_HEAD.
    raise SystemExit('Upstream merge needs manual investigation:\n'+conflicts+'\n'+merge.stderr[-2000:])
# Never activate newly fetched workflows in a privileged synchronization job.
# CI changes require a separate explicit review, even when upstream is trusted.
for p in Path('.github/workflows').glob('*'):
    if p.is_file():p.unlink()
run('git','restore','--source='+base,'--staged','--worktree','.github/workflows')
run('git','add','-A','.github/workflows')
pin['tag']=tag;pin['commit']=upstream
pin['downstream_version']=tag+'-dns.1-rc.1'
Path('downstream/UPSTREAM.json').write_text(json.dumps(pin,indent=2)+'\n')
run('git','add','downstream/UPSTREAM.json')
run('git','-c','user.name=github-actions[bot]','-c','user.email=41898282+github-actions[bot]@users.noreply.github.com','commit','-m','Review upstream '+tag)
run('git','push','origin','HEAD:refs/heads/'+branch)
url=f'https://github.com/{repo}/compare/dns-maintained...{branch}?expand=1'
print('Review and open a PR:',url)
if os.environ.get('GITHUB_STEP_SUMMARY'):
    with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
        f.write(f'Upstream {tag} ({upstream}) prepared for [owner review]({url}). No promotion or deployment occurred.\n')
# Token-created pushes may not start normal CI; explicitly dispatch read-only CI.
run('gh','workflow','run','downstream-ci.yml','--repo',repo,'--ref',branch)
