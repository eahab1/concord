"""Explicit provisional search; separate screening and convergence evidence."""
import fcntl
import json
import math
from pathlib import Path
import time
from .bem import Response
from .campaign import objective, offspring
from .config import load, save, bounds
from .frequency import resolve
from .result_cache import ResultCache, runtime_identity, digest
from .viewer import atomic_text, design_hash


def screen(config, out, backend, max_frequency, edge_mm, *, max_edge_mm=None, reference_provider=None):
    from .analysis import prepare, solve_job, reference_check
    from .cli import build_run
    from .viewer import attach_result
    design = resolve(load(config), max_frequency)
    if not design.manual.hf_only:
        raise ValueError('Screening requires HF-only geometry')
    build_run(design, out)
    (reference_provider or reference_check)(out/'reference', backend)
    _, report = prepare(design, out/'level-0', edge_mm, max_edge_mm=max_edge_mm)
    if not report['wavelength_resolution_pass']:
        raise ValueError('Screening mesh is too coarse for this band; reduce edge sizes or set --max-edge-mm')
    _, response = solve_job(out/'level-0/bem-job.json', out/'level-0/solution', backend)
    response = response.model_copy(update={
        'analysis_status': 'reference_validated',
        'notes': ['Provisional single-mesh screening; mesh convergence has NOT been established.',
                  'Ideal HF source in an infinite baffle; no LF, array, crossover or measured driver response.']})
    (out/'response.json').write_text(response.model_dump_json(indent=2)+'\n')
    attach_result(out, 'baseline', out/'response.json')


def publish(out, state):
    atomic_text(out/'campaign.json', json.dumps(state, indent=2, allow_nan=False)+'\n')
    lines = ['Concord fast campaign', state['status'],
             'Screening ranks are provisional. Validation scores are separate. Lower scores are better.',
             'Candidate viewers show geometry and responses; the campaign HTML update is pending.', '']
    for generation in state['generations']:
        lines.append(f"Generation {generation['index']:03d}")
        for c in generation['candidates']:
            def label(stage):
                r = c.get(stage, {})
                score = r.get('score')
                return f"{r.get('status', 'pending')}, score={score['objective']:.5f}" if score else r.get('status', 'pending')
            lines.append(f"  {c['id']} | screen #{c.get('screening_rank', '-')} {label('screening')} | validation #{c.get('validation_rank', '-')} {label('validation')}")
            for stage in ('screening', 'validation'):
                if c.get(stage, {}).get('response'):
                    lines.append(f"    {stage}: {c[stage]['response']} (cache hit: {c[stage]['cache_hit']})")
                if c.get(stage, {}).get('error'):
                    lines.append(f"    {stage}: {c[stage]['error']}")
        lines.append('')
    atomic_text(out/'summary.txt', '\n'.join(lines)+'\n')


def run(config, out, generations=2, population=4, seed=42, backend='bempp-cpu',
        max_frequency=2000., edges=(24.,16.,10.), resume=False, propose_only=False,
        min_frequency=None, frequency_points=None, frequency_spacing='log', max_edge_mm=None,
        finalists=1, cache_dir=None, screener=None, analyzer=None):
    if not 1 <= generations <= 100 or not 2 <= population <= 100:
        raise ValueError('Use 1–100 generations and 2–100 candidates per generation')
    if not 1 <= finalists <= population:
        raise ValueError('Finalists must be between 1 and population')
    if len(edges)<3 or any(not math.isfinite(e) or not .5<=e<=40 for e in edges) or any(a<=b for a,b in zip(edges,edges[1:])):
        raise ValueError('Use at least three decreasing mesh edges between 0.5 and 40 mm')
    if max_edge_mm is not None and not .5<=max_edge_mm<=40:
        raise ValueError('Local maximum edge must be between 0.5 and 40 mm')
    design = resolve(load(config), max_frequency, min_frequency, frequency_points, frequency_spacing)
    if not design.manual.hf_only: raise ValueError('Campaigns require HF-only geometry')
    out = Path(out)
    identity = runtime_identity(backend)
    cache = ResultCache(cache_dir or out.parent/'.concord-cache', identity)
    settings = dict(mode='fast', population=population, seed=seed, backend=backend,
                    frequencies_hz=design.manual.frequencies_hz, edges=list(edges), max_edge_mm=max_edge_mm,
                    baseline_sha256=design_hash(design), finalists=finalists, runtime=identity,
                    objective='pattern_mse_v1', cache_dir=str(cache.root.resolve()))
    from .analysis import analyze, reference_check
    from .cli import build_run
    screener = screener or screen
    analyzer = analyzer or analyze
    def reference_provider(destination, requested_backend):
        hit = cache.evaluate({'stage':'reference', 'backend':requested_backend}, destination,
                             lambda p: reference_check(p, requested_backend), reference=True)
        report = json.loads((destination/'reference-check.json').read_text())
        return dict(report, **hit)
    out.mkdir(parents=True, exist_ok=True)
    with (out/'.run.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('This campaign is already running')
        if (out/'campaign.json').exists():
            if not resume: raise ValueError('Existing campaign; use --resume')
            state = json.loads((out/'campaign.json').read_text())
            if not isinstance(state, dict) or state.get('version')!=2 or not state.get('generations'):
                raise ValueError('Not a fast campaign. Start with a new --out directory without --resume')
            if state.get('settings')!=settings:
                raise ValueError('Resume settings/config/solver must match original campaign; start a new directory after changes')
        else:
            if resume: raise ValueError('No campaign exists to resume')
            if any(p.name!='.run.lock' for p in out.iterdir()): raise ValueError('Output must be empty')
            state = dict(version=2, settings=settings, status='proposed', generations=[], bounds=bounds())
            save(design, out/'baseline.yaml')
        def create(index, proposals):
            generation = dict(index=index, candidates=[])
            for i, (d, parent) in enumerate(proposals):
                root=out/f'generation-{index:03d}'/f'candidate-{i:04d}'
                if (root/'resolved.yaml').exists():
                    if design_hash(load(root/'resolved.yaml'))!=design_hash(d):
                        raise ValueError('Incomplete proposal conflicts with requested design')
                else: build_run(d, root)
                generation['candidates'].append(dict(id=root.name, config=str((root/'resolved.yaml').relative_to(out)),
                    design_sha256=design_hash(d), parent_sha256=parent,
                    parameters={k:v for k,v in d.optimized.model_dump().items() if not k.startswith('lf_')}))
            state['generations'].append(generation); publish(out, state)
        def evaluate(c, stage):
            cfg=out/c['config']; d=load(cfg)
            if design_hash(d)!=c['design_sha256']: raise ValueError('Saved candidate was edited; start a new campaign')
            if c.get(stage, {}).get('status') in ('complete','unqualified','failed'):
                record=c[stage]
                if record.get('response'):
                    # Completed checkpoints must still match the stored score and response.
                    if digest(out/record['response'])!=record['response_sha256']:
                        raise ValueError('Completed response changed; restore it or start a new campaign')
                    r=Response.model_validate_json((out/record['response']).read_text())
                    if stage=='screening' or r.analysis_status=='mesh_converged':
                        if objective(d,r,provisional=stage=='screening')!=record['score']:
                            raise ValueError('Completed response changed; restore it or start a new campaign')
                return
            attempt=0
            while (cfg.parent/f'{stage}-{attempt:03d}').exists(): attempt+=1
            dest=cfg.parent/f'{stage}-{attempt:03d}'
            c[stage]={'status':'running'}; state['status']='running'; publish(out,state)
            start=time.monotonic()
            contract=dict(stage=stage, design_sha256=design_hash(d), frequencies_hz=d.manual.frequencies_hz,
                          backend=backend, edges=[edges[0]] if stage=='screening' else list(edges), max_edge_mm=max_edge_mm)
            def compute(p):
                fn=screener if stage=='screening' else analyzer
                fn(cfg,p,backend,max_frequency,edges[0] if stage=='screening' else edges,
                   max_edge_mm=max_edge_mm,reference_provider=reference_provider)
            try:
                hit=cache.evaluate(contract,dest,compute)
                r=Response.model_validate_json((dest/'response.json').read_text())
                qualified = stage=='screening' or r.analysis_status=='mesh_converged'
                c[stage]=dict(status='complete' if qualified else 'unqualified',
                    score=objective(d,r,provisional=stage=='screening') if qualified else None,
                    response=str((dest/'response.json').relative_to(out)), response_sha256=digest(dest/'response.json'),
                    viewer=str((dest/'viewer.html').relative_to(out)), elapsed_seconds=time.monotonic()-start, **hit)
            except (ValueError,RuntimeError,OSError,ImportError) as exc:
                c[stage]=dict(status='failed',error=str(exc),elapsed_seconds=time.monotonic()-start)
            publish(out,state)
        try:
            if not state['generations']:
                create(0,[(design,None),*offspring([design],population-1,seed,0)])
            if not propose_only:
                for index in range(generations):
                    generation=state['generations'][index]
                    for c in generation['candidates']: evaluate(c,'screening')
                    ranked=sorted([c for c in generation['candidates'] if c['screening']['status']=='complete'],
                                  key=lambda c:c['screening']['score']['objective'])
                    for rank,c in enumerate(ranked,1): c['screening_rank']=rank
                    for c in ranked[:finalists]: evaluate(c,'validation')
                    validated=sorted([c for c in ranked if c.get('validation',{}).get('status')=='complete'],
                                     key=lambda c:c['validation']['score']['objective'])
                    for rank,c in enumerate(validated,1): c['validation_rank']=rank
                    # Explicit fast mode breeds from provisional ranks, but rejects known validation failures.
                    eligible=[c for c in ranked if c.get('validation',{}).get('status') not in ('failed','unqualified')]
                    if not validated:
                        state['status']='blocked: no validated finalists; inspect failures before continuing'
                        publish(out,state); return state
                    if len(state['generations'])==index+1:
                        parents=[load(out/c['config']) for c in eligible[:max(1,population//2)]]
                        create(index+1,[(parents[0],design_hash(parents[0])),*offspring(parents,population-1,seed,index+1)])
            state['status']='proposed' if propose_only else 'complete; next generation proposed'
            publish(out,state); return state
        except BaseException:
            state['status']='interrupted; resume to continue'; publish(out,state); raise
