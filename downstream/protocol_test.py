#!/usr/bin/env python3
"""Read-only, offline release comparison. Uses high loopback ports only."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import datetime
import hashlib
import json
import ipaddress
import os
import socket
from pathlib import Path
import tempfile
import time
import dns.flags
import dns.message
import dns.query
import dns.rcode
import dns.rrset
import yaml
import socketserver
import ssl
import struct
import subprocess
import threading

class ThreadTCP(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

class ThreadUDP(socketserver.ThreadingUDPServer):
    allow_reuse_address = True
    daemon_threads = True

def read_exact(sock, n):
    out = b''
    while len(out) < n:
        part = sock.recv(n-len(out))
        if not part:
            raise EOFError()
        out += part
    return out

class TCPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        sock = self.request
        try:
            if self.server.tls:
                sock = self.server.tls.wrap_socket(sock, server_side=True)
            sock.settimeout(7)
            while True:
                n, = struct.unpack('!H', read_exact(sock, 2))
                q = dns.message.from_wire(read_exact(sock, n))
                r = self.server.reply(q)
                if r is not None:
                    data = r.to_wire(max_size=65535)
                    sock.sendall(struct.pack('!H', len(data))+data)
        except (EOFError, OSError, ssl.SSLError):
            pass
        finally:
            sock.close()

class UDPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        data, sock = self.request
        q = dns.message.from_wire(data)
        r = self.server.reply(q)
        if r is not None:
            sock.sendto(r.to_wire(max_size=65535), self.client_address)

def serve(port, reply, tls=None):
    servers = [ThreadTCP(('127.0.0.1', port), TCPHandler)]
    if tls is None:
        servers.append(ThreadUDP(('127.0.0.1', port), UDPHandler))
    for server in servers:
        server.reply = reply
        server.tls = tls
        threading.Thread(target=server.serve_forever, daemon=True).start()
    return servers

def start(cmd, directory, name, env=None):
    log = (directory/(name+'.log')).open('w')
    p = subprocess.Popen(cmd, stdout=log, stderr=log, env=env)
    time.sleep(.3)
    if p.poll() is not None:
        log.close()
        raise RuntimeError((directory/(name+'.log')).read_text()[-4000:])
    return p, log



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mihomo', required=True)
    ap.add_argument('--mosdns')
    ap.add_argument('--disable-cache', action='store_true')
    ap.add_argument('--expect-fixed', action='store_true')
    ap.add_argument('--enhanced-mode', choices=['redir-host','fake-ip'], default='redir-host')
    ap.add_argument('--cache-max-size', type=int)
    ap.add_argument('--upstream-mihomo', help='Put a patched DNS relay behind the tested frontend')
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    checks, servers, processes = [], [], []
    count = Counter()
    def reply(q):
        name = q.question[0].name.to_text()
        count[name] += 1
        if name.startswith('flight.'):
            time.sleep(.2)
        r = dns.message.make_response(q)
        r.flags |= dns.flags.RA
        n = 2 if q.flags & dns.flags.CD else 1
        if name.startswith('expire.'):
            n = min(count[name], 2)
        if name.startswith('negative.') and count[name] == 1:
            r.set_rcode(dns.rcode.NXDOMAIN)
            r.authority = [dns.rrset.from_text(name, 1, 'IN', 'SOA',
                'ns.example. hostmaster.example. 1 60 60 60 1')]
        elif name.startswith('collision.') and q.question[0].rdtype == 1:
            r.set_rcode(dns.rcode.SERVFAIL)
        elif name.startswith('do.'):
            r.answer = [dns.rrset.from_text(name, 30, 'IN', 'TXT',
                '"do=%d"' % bool(q.ednsflags & dns.flags.DO))]
        elif q.question[0].rdtype == 257:
            r.answer = [dns.rrset.from_text(name, 30, 'IN', 'CAA', '0 issue "example.org"')]
        else:
            r.answer = [dns.rrset.from_text(name, 1 if name.startswith('expire.') else 30,
                'IN', 'A', '192.0.2.' + str(n))]
        return r
    def query(port, name, kind='A', cd=False, do=True):
        q = dns.message.make_query(name, kind, want_dnssec=do)
        if cd: q.flags |= dns.flags.CD
        return dns.query.tcp(q, '127.0.0.1', port=port, timeout=5)
    def ready(port):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    return
            except OSError:
                time.sleep(.05)
        raise TimeoutError('DNS fixture listener did not become ready')
    def addr(r):
        return r.answer[0][0].to_text() if r.answer else ''
    def check(name, ok, observed):
        checks.append(dict(test=name, passed=bool(ok), observed=observed))
    with tempfile.TemporaryDirectory(prefix='official-dns-regression-') as td:
        d = Path(td)
        try:
            servers += serve(17100, reply)
            upstream_port=17100
            if a.upstream_mihomo:
                relay={'mode':'rule','rules':['MATCH,DIRECT'],'dns':{'enable':True,
                    'listen':'127.0.0.1:17104','enhanced-mode':'redir-host','disable-cache':True,
                    'default-nameserver':['127.0.0.1:17100'],'nameserver':['tcp://127.0.0.1:17100']}}
                relay_path=d/'relay.yaml';relay_path.write_text(yaml.safe_dump(relay))
                processes.append(start([a.upstream_mihomo,'-d',str(d/'relay'),'-f',str(relay_path)],d,'relay'))
                ready(17104)
                upstream_port=17104
            for i, alg in enumerate(('lru', 'arc')):
                port = 17101+i
                cfg = {'ipv6': True, 'mode': 'rule', 'rules': ['MATCH,DIRECT'],
                       'dns': {'enable': True, 'listen': f'127.0.0.1:{port}',
                               'enhanced-mode': a.enhanced_mode, 'cache-algorithm': alg,
                               'disable-cache': a.disable_cache,
                               'default-nameserver': ['127.0.0.1:17100'],
                               'nameserver': [f'tcp://127.0.0.1:{upstream_port}']}}
                if a.enhanced_mode == 'fake-ip':
                    cfg['dns']['fake-ip-filter']=['+.example']
                if a.cache_max_size is not None:
                    cfg['dns']['cache-max-size']=a.cache_max_size
                path=d/(alg+'.yaml'); path.write_text(yaml.safe_dump(cfg))
                processes.append(start([a.mihomo, '-d', str(d/alg), '-f', str(path)], d, alg))
                ready(port)
                if a.enhanced_mode=='fake-ip':
                    fake=query(port,'mapping.test')
                    check(alg+': synthetic mapping remains separate',
                          ipaddress.ip_address(addr(fake)) in ipaddress.ip_network('198.18.0.0/16') and count['mapping.test.']==0,
                          {'address':addr(fake),'fixture_queries':count['mapping.test.']})
                raw=query(port, f'flags.{alg}.example', cd=True)
                validated=query(port, f'flags.{alg}.example')
                check(alg+': CD separation', addr(raw)=='192.0.2.2' and addr(validated)=='192.0.2.1',
                      [addr(raw),addr(validated)])
                do0=query(port, f'do.{alg}.example', 'TXT', do=False)
                do1=query(port, f'do.{alg}.example', 'TXT')
                check(alg+': DO separation', addr(do0)=='"do=0"' and addr(do1)=='"do=1"', [addr(do0),addr(do1)])
                first=query(port, f'expire.{alg}.example')
                nx=query(port, f'negative.{alg}.example')
                time.sleep(1.2)
                newer=query(port, f'expire.{alg}.example')
                nowexists=query(port, f'negative.{alg}.example')
                check(alg+': expired positive not served', addr(newer)=='192.0.2.2', [addr(first),addr(newer)])
                check(alg+': expired negative not served', nx.rcode()==3 and nowexists.rcode()==0,
                      [nx.rcode(),nowexists.rcode()])
                with ThreadPoolExecutor(2) as pool:
                    f=pool.submit(query, port, f'flight.{alg}.example', cd=True)
                    time.sleep(.04)
                    g=pool.submit(query, port, f'flight.{alg}.example')
                    x,y=f.result(),g.result()
                check(alg+': concurrent CD separation', addr(x)=='192.0.2.2' and addr(y)=='192.0.2.1', [addr(x),addr(y)])
            if a.mosdns:
                cfg={'plugins': [
                    {'tag':'cache', 'type':'cache','args':{'size':1024}},
                    {'tag':'forward','type':'forward','args':{'upstreams':[{'addr':'tcp://127.0.0.1:17100'}]}},
                    {'tag':'main','type':'sequence','args':[{'exec':'$cache'},
                        {'matches':['has_resp'],'exec':'accept'},{'exec':'$forward'}]},
                    {'type':'tcp_server','args':{'entry':'main','listen':'127.0.0.1:17103'}}]}
                path=d/'mosdns.yaml';path.write_text(yaml.safe_dump(cfg))
                processes.append(start([a.mosdns,'start','-c',str(path)],d,'mosdns'))
                r=query(17103,'do.mosdns.example','TXT')
                check('mosdns: DO reaches upstream',addr(r)=='"do=1"',addr(r))
                x=query(17103,'collision.example')
                try:
                    y=query(17103,'collision.example','CAA')
                    check('mosdns: A/CAA cache separation',x.rcode()==2 and y.rcode()==0,[x.rcode(),y.rcode()])
                except dns.query.BadResponse:
                    check('mosdns: A/CAA cache separation',False,'cached response has wrong question type')
            result={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'scope':'host binary, synthetic loopback fixtures; no routers',
                    'mihomo_binary_sha256':hashlib.sha256(Path(a.mihomo).read_bytes()).hexdigest(),
                    'disable_cache':a.disable_cache,'enhanced_mode':a.enhanced_mode,
                    'cache_max_size':a.cache_max_size,
                    'managed_dns_env':os.environ.get('MIHOMO_MANAGED_DNS')=='1','checks':checks}
            result['patched_upstream_relay']=bool(a.upstream_mihomo)
            if a.upstream_mihomo:
                result['upstream_relay_sha256']=hashlib.sha256(Path(a.upstream_mihomo).read_bytes()).hexdigest()
            a.output.write_text(json.dumps(result,indent=2)+'\n')
            print(json.dumps({'passed':sum(c['passed'] for c in checks),'total':len(checks),
                              'failed':[c['test'] for c in checks if not c['passed']]}))
        finally:
            for p,log in processes:
                p.terminate();p.wait(timeout=5);log.close()
            for s in servers:s.shutdown();s.server_close()
    if a.expect_fixed and not all(c['passed'] for c in checks): raise SystemExit(1)

if __name__=='__main__':main()
