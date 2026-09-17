#!/usr/bin/env python3
"""Read-only, localhost results catalogue. No solver imports or dependencies."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
from urllib.parse import parse_qs, unquote, urlsplit

DOCUMENTS = {'campaign.json','response.json','qualification.json','analysis-progress.json',
             'reference-check.json','resource-check.json','resources.json','precision-comparison.json',
             'mesh-report.json','bem-job.json','manifest.json','benchmark.json','provenance.json','viewer-state.json'}
MARKERS = DOCUMENTS - {'provenance.json','viewer-state.json'}
LIMIT = 8 * 1024 * 1024
HTML = Path(__file__).with_name('results_browser.html')


class Catalogue:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        self.cache = {}
        self.lock = threading.Lock()

    def safe(self, relative):
        relative = Path(relative)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Path outside results root')
        path = self.root
        for part in relative.parts:
            if part.startswith('.'):
                raise ValueError('Hidden paths are excluded')
            path = path / part
            if path.is_symlink():
                raise ValueError('Symlinks are excluded')
        path.resolve().relative_to(self.root)
        return path

    def read(self, path):
        try:
            stat = path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
            if stat.st_size > LIMIT:
                return None, 'Metadata exceeds size limit'
            cached = self.cache.get(path)
            if cached and cached[0] == stamp:
                return cached[1], cached[2]
            try:
                value = json.loads(path.read_text(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
                error = None
            except (ValueError, OSError, UnicodeError) as exc:
                value, error = None, f'Incomplete/unreadable metadata: {exc}'
            self.cache[path] = (stamp, value, error)
            return value, error
        except OSError:
            return None, 'File unavailable; it may be changing'

    def scan(self):
        with self.lock:
            rows = []; scores = {}; seen = set()
            for folder, dirs, names in os.walk(self.root, followlinks=False):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('__pycache__','node_modules','cache') and not (Path(folder)/d).is_symlink()]
                path = Path(folder)
                available = set(names) & DOCUMENTS
                if not (set(names) & MARKERS or 'viewer.html' in names):
                    continue
                docs = {}; errors = []
                for name in available:
                    p=path/name
                    if p.is_symlink(): continue
                    seen.add(p); value, error = self.read(p)
                    if error: errors.append(f'{name}: {error}')
                    if isinstance(value, dict): docs[name]=value
                    elif value is not None: docs[name]={'items':value}
                relative = path.relative_to(self.root).as_posix()
                campaign = docs.get('campaign.json', {})
                for generation in campaign.get('generations', []) or []:
                    if not isinstance(generation,dict): continue
                    for c in generation.get('candidates', []) or []:
                        if not isinstance(c,dict): continue
                        stages = [('validated',c)] if 'score' in c else [(s,c.get(s,{})) for s in ('screening','validation')]
                        for stage, result in stages:
                            if isinstance(result,dict) and isinstance(result.get('response'),str):
                                try:
                                    target=self.safe((path.relative_to(self.root)/result['response']).as_posix())
                                    key=target.parent.relative_to(self.root).as_posix()
                                except ValueError: continue
                                scores[key] = {'stage':stage,'score':result.get('score'),'rank':result.get('rank',c.get(stage+'_rank')),
                                               'parameters':c.get('parameters',{}),'cache_hit':result.get('cache_hit'),
                                               'generation':generation.get('index'), 'candidate':c.get('id')}
                response=docs.get('response.json', {}); qualification=docs.get('qualification.json', {})
                progress=docs.get('analysis-progress.json', {}); reference=docs.get('reference-check.json', {})
                job=docs.get('bem-job.json', {}); mesh=docs.get('mesh-report.json', {})
                resource=docs.get('resource-check.json',docs.get('resources.json',{}))
                kind='mesh'; status='prepared'
                if 'campaign.json' in docs: kind='campaign'; status=campaign.get('status','unknown')
                elif 'qualification.json' in docs: kind='validation'; status=qualification.get('status','unknown')
                elif 'analysis-progress.json' in docs: kind='analysis'; status=progress.get('status','unknown')
                elif response: kind='response'; status=response.get('analysis_status','unqualified')
                elif reference: kind='reference test'; status='passed' if reference.get('passed') else 'failed'
                elif 'precision-comparison.json' in docs:
                    kind='precision test'; items=docs['precision-comparison.json'].get('items',[])
                    status='passed' if items and all(v.get('passed') for v in items) else 'inspect'
                elif resource: kind='resource test'; status='failed' if resource.get('stopped_reason') or resource.get('exit_code',0) else 'recorded'
                elif 'benchmark.json' in docs: kind='benchmark'; status='recorded'
                elif 'manifest.json' in docs or 'viewer.html' in names: kind='proposal'; status='geometry only'
                if response.get('synthetic'): status='synthetic — not validation'
                freqs=response.get('frequencies_hz',progress.get('frequencies_hz',job.get('frequencies_hz',campaign.get('settings',{}).get('frequencies_hz',[]))))
                times=[]
                for name in available:
                    try: times.append((path/name).stat().st_mtime)
                    except OSError: pass
                rows.append(dict(path=relative,run=relative.split('/')[0],kind=kind,status=status,
                    frequencies=freqs,backend=response.get('solver',progress.get('backend',campaign.get('settings',{}).get('backend',''))),
                    updated=max(times,default=0),completed_at=(path/'response.json').stat().st_mtime if response else None,
                    errors=errors,viewer='viewer.html' in names,
                    triangles=mesh.get('quarter_triangles',mesh.get('triangles')),
                    mesh_label='Concept triangles' if 'manifest.json' in docs else ('Quarter-mesh triangles' if 'quarter_triangles' in mesh else 'Mesh triangles'),resource=resource,
                    levels_completed=len(progress.get('levels',[]))))
            for row in rows:
                row['ranking']=scores.get(row['path'])
                if row['ranking'] and row['ranking']['stage']=='screening': row['kind']='screening'
            self.cache={p:v for p,v in self.cache.items() if p in seen}
            return dict(root=str(self.root),scanned_at=time.time(),rows=sorted(rows,key=lambda r:(-r['updated'],r['path'])))

    def detail(self, relative):
        path=self.safe(relative)
        if not path.is_dir(): raise ValueError('Not a result directory')
        docs={}; files=[]
        with self.lock:
            for p in sorted(path.iterdir()):
                if p.is_symlink() or not p.is_file() or p.name.startswith('.'): continue
                files.append(dict(name=p.name,size=p.stat().st_size))
                if p.name in DOCUMENTS:
                    value,error=self.read(p); docs[p.name]=value if error is None else {'read_error':error}
                elif p.suffix in ('.log','.yaml','.txt'):
                    with p.open('rb') as stream:
                        stream.seek(max(0,p.stat().st_size-16000))
                        docs[p.name]=stream.read(16000).decode('utf-8',errors='replace')
        return dict(path=relative,documents=docs,files=files)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,catalogue,**kwargs):
        self.catalogue=catalogue
        super().__init__(*args,directory=str(catalogue.root),**kwargs)

    def log_message(self,*args): pass

    def end_headers(self):
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        super().end_headers()

    def payload(self, value, mime='application/json; charset=utf-8'):
        content = json.dumps(value,allow_nan=False).encode() if mime.startswith('application/json') else value
        self.send_response(200); self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(content))); self.end_headers(); self.wfile.write(content)

    def do_GET(self):
        url=urlsplit(self.path)
        try:
            if url.path=='/': return self.payload(HTML.read_bytes(),'text/html; charset=utf-8')
            if url.path=='/api/index': return self.payload(self.catalogue.scan())
            if url.path=='/api/detail': return self.payload(self.catalogue.detail(parse_qs(url.query).get('path',['.'])[0]))
            if url.path.startswith('/files/'):
                relative=unquote(url.path[len('/files/'):]); p=self.catalogue.safe(relative)
                if not p.is_file(): return self.send_error(404)
                self.path='/'+url.path[len('/files/'):]
                return super().do_GET()
            return self.send_error(404)
        except (ValueError,OSError,TypeError,KeyError): self.send_error(400,'Results unavailable or invalid path')

    def do_HEAD(self): self.send_error(405)


def server(root,port):
    return ThreadingHTTPServer(('127.0.0.1',port),partial(Handler,catalogue=Catalogue(root)))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]/'runs')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--follow-latest',action='store_true',help='Enable following newly completed responses in the launch URL')
    parser.add_argument('--open',action='store_true',help='Open the results browser')
    args=parser.parse_args()
    with server(args.root,args.port) as app:
        url=f'http://127.0.0.1:{app.server_port}/'+('?follow=1' if args.follow_latest else '')
        print(f'Concord results: {url} — read-only: {args.root.resolve()}',flush=True)
        if args.open:
            import webbrowser
            webbrowser.open(url)
        try: app.serve_forever()
        except KeyboardInterrupt: pass


if __name__=='__main__': main()
