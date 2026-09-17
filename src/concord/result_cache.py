"""Content-verified cache; keys include solver/runtime and numerical contracts."""
import fcntl
import hashlib
from importlib import metadata, util
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import uuid
from .bem import Response


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def runtime_identity(backend):
    source=Path(__file__).parent
    names=['analysis.py','acoustic_mesh.py','local_refinement.py','cpu_bem.py','geometry.py',
           'mesh.py','config.py','frequency.py','bem.py','campaign.py','fast_campaign.py','result_cache.py']
    packages={}
    for name in ['numpy','scipy','gmsh','meshio','bempp-cl','hornlab-metal-bem','numba']:
        try:packages[name]=metadata.version(name)
        except metadata.PackageNotFoundError:packages[name]='not-installed'
    kernel={}
    if backend.startswith('hornlab-metal'):
        spec=util.find_spec('hornlab_metal_bem')
        if spec and spec.origin:
            root=Path(spec.origin).parent
            for p in sorted(root.rglob('*')):
                if p.is_file() and p.suffix in ('.py','.swift','.metal') and '.build' not in p.parts:
                    kernel[str(p.relative_to(root))]=digest(p)
            helper=root/'metal/native_helper/.build/release/HornlabMetalBemNative'
            if helper.exists():kernel['native_helper']=digest(helper)
    env={k:v for k,v in os.environ.items() if k.startswith(('HORNLAB_','NUMBA_')) or k in ('VECLIB_MAXIMUM_THREADS','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS')}
    value=dict(version=1,backend=backend,python=sys.version,platform=platform.platform(),packages=packages,
               source={n:digest(source/n) for n in names},kernel=kernel,
               environment_sha256=hashlib.sha256(json.dumps(env,sort_keys=True).encode()).hexdigest())
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


class ResultCache:
    def __init__(self, root, identity):
        self.root=Path(root);self.identity=identity
        self.root.mkdir(parents=True,exist_ok=True)

    def evaluate(self, contract, destination, compute, *, reference=False):
        key=hashlib.sha256(json.dumps({'runtime':self.identity,'contract':contract},sort_keys=True).encode()).hexdigest()
        entry=self.root/key;destination=Path(destination)
        if destination.exists():raise ValueError('Cached evaluation destination must not exist')
        with (self.root/(key+'.lock')).open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if entry.exists():
                try:
                    manifest=json.loads((entry/'manifest.json').read_text())
                    if manifest['key']!=key:raise ValueError('Cache identity mismatch')
                    payload=entry/'payload'
                    if entry.is_symlink() or payload.is_symlink() or any(p.is_symlink() for p in payload.rglob('*')):raise ValueError('Cache symlink')
                    actual={str(p.relative_to(payload)):digest(p) for p in payload.rglob('*') if p.is_file()}
                    if not actual or actual!=manifest['files']:raise ValueError('Cache content changed')
                    self._check(payload,contract,reference)
                except (ValueError,KeyError,OSError):
                    entry.rename(self.root/(key+'.invalid-'+uuid.uuid4().hex))
                else:
                    shutil.copytree(payload,destination)
                    return {'cache_hit':True,'cache_key':key}
            compute(destination)
            self._check(destination,contract,reference)
            temporary=self.root/(key+'.tmp-'+uuid.uuid4().hex)
            try:
                if destination.is_symlink() or any(p.is_symlink() for p in destination.rglob('*')):raise ValueError('Cannot cache symlinks')
                shutil.copytree(destination,temporary/'payload')
                files={str(p.relative_to(destination)):digest(p) for p in destination.rglob('*') if p.is_file()}
                (temporary/'manifest.json').write_text(json.dumps({'key':key,'files':files},indent=2)+'\n')
                temporary.rename(entry)
            finally:
                if temporary.exists():shutil.rmtree(temporary)
            return {'cache_hit':False,'cache_key':key}

    @staticmethod
    def _check(folder,contract,reference):
        if reference:
            if json.loads((folder/'reference-check.json').read_text()).get('passed') is not True:
                raise ValueError('Failed reference cannot enter the cache')
        else:
            r=Response.model_validate_json((folder/'response.json').read_text())
            if r.synthetic or r.design_sha256!=contract['design_sha256'] or r.frequencies_hz!=contract['frequencies_hz']:
                raise ValueError('Cached response does not match its numerical contract')
