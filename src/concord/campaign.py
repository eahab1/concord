"""Resumable, sequential generations. Every ranked result is a qualified BEM solve."""
from importlib.resources import files
import json
import random
import fcntl
from pathlib import Path
from pydantic import ValidationError
from .config import Design, load, save, bounds
from .bem import Response
from .viewer import atomic_text, javascript_json, design_hash


def objective(design, response, *, provisional=False):
    if response.synthetic or (not provisional and response.analysis_status != 'mesh_converged'):
        raise ValueError('Only real, mesh-converged responses can rank')
    if response.design_sha256 != design_hash(design) or response.frequencies_hz != design.manual.frequencies_hz:
        raise ValueError('Response does not match candidate')
    # A sampled pattern objective remains defined when the -6 dB crossing is
    # outside the measured hemisphere. Equal weight per plane and frequency.
    terms = {}
    for name, rows, target in [('horizontal', response.horizontal_db, design.manual.coverage.horizontal_target_deg),
                               ('vertical', response.vertical_db, design.manual.coverage.vertical_target_deg)]:
        desired = [max(-30., -6 * (2 * abs(a) / target)**2) for a in response.angles_deg]
        terms[name] = sum((max(-30., min(3., value))-want)**2 / 36
                         for row in rows for value, want in zip(row, desired)) / (len(rows)*len(desired))
    return {'objective': sum(terms.values())/2, 'terms': terms,
            'method': 'pattern_mse_v1', 'qualification': 'provisional' if provisional else 'validated', 'scope': 'Equal H/V sampled pattern error; lower is better. Ideal source, analyzed band only.'}


def offspring(parents, count, seed, generation):
    rng = random.Random(seed + generation * 100003)
    limits = bounds(); result = []; seen = {design_hash(p) for p in parents}
    for _ in range(count * 1000):
        parent = parents[rng.randrange(len(parents))]
        data = parent.model_dump()
        for key, (lo, hi) in limits.items():
            if parent.manual.hf_only and key.startswith('lf_'): continue
            sigma = (hi-lo) * max(.025, .15 * .8**generation)
            data['optimized'][key] = max(lo, min(hi, rng.gauss(data['optimized'][key], sigma)))
        try: child = Design.model_validate(data)
        except ValidationError: continue
        sha = design_hash(child)
        if sha in seen: continue
        seen.add(sha); result.append((child, design_hash(parent)))
        if len(result) == count: return result
    raise ValueError('Unable to create unique feasible offspring')


def publish(out, state):
    atomic_text(out/'campaign.json', json.dumps(state, indent=2, allow_nan=False)+'\n')
    atomic_text(out/'campaign-data.js', 'window.concordCampaign('+javascript_json(state)+');\n')


def run(config, out, generations=2, population=4, seed=42, backend='bempp-cpu',
        max_frequency=2000., edges=(24.,16.,10.), resume=False, propose_only=False, analyzer=None, min_frequency=None,
        frequency_points=None, frequency_spacing="log", max_edge_mm=None):
    if not 1 <= generations <= 100 or not 2 <= population <= 100:
        raise ValueError('Use 1–100 generations and 2–100 candidates per generation')
    if len(edges)<3 or any(a<=b for a,b in zip(edges,edges[1:])):
        raise ValueError('Use at least three decreasing mesh edge sizes')
    design = load(config)
    from .frequency import resolve
    design = resolve(design,max_frequency,min_frequency,frequency_points,frequency_spacing)
    if not design.manual.hf_only: raise ValueError('Campaigns currently require HF-only geometry')
    settings = dict(population=population, seed=seed, backend=backend, max_frequency=max_frequency,
                    edges=list(edges), frequencies_hz=design.manual.frequencies_hz, frequency_spacing=frequency_spacing, baseline_sha256=design_hash(design), objective='pattern_mse_v1')
    if max_edge_mm is not None:
        if not .5<=max_edge_mm<=40: raise ValueError("Local maximum edge must be between 0.5 and 40 mm")
        settings["max_edge_mm"]=max_edge_mm
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    with (out/'.run.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('This campaign is already running')
        if (out/'campaign.json').exists():
            if not resume: raise ValueError('Existing campaign; use --resume')
            state = json.loads((out/'campaign.json').read_text())
            if isinstance(state, dict) and state.get('status') == 'proposed_only_not_simulated':
                raise ValueError(
                    f"{out} contains legacy 'concord propose' output, not a generation campaign. "
                    "Existing proposals have been preserved. Start 'concord campaign' with a new "
                    "--out directory and without --resume; add --propose-only to preview first.")
            if (not isinstance(state, dict) or state.get('version') != 1
                    or not isinstance(state.get('settings'), dict)
                    or not isinstance(state.get('generations'), list)
                    or not state['generations']):
                raise ValueError(
                    f"Invalid or unsupported campaign state in {out/'campaign.json'}. "
                    "Use an intact generation campaign or start with a new --out directory.")
            if state['settings'] != settings: raise ValueError('Resume settings/config must match original campaign')
        else:
            if any(p.name != '.run.lock' for p in out.iterdir()): raise ValueError('Output must be empty')
            state = dict(version=1, settings=settings, status='proposed', generations=[], bounds=bounds())
            save(design, out/'baseline.yaml')
        (out/'viewer.html').write_text(files('concord').joinpath('data/campaign.html').read_text())
        from .cli import build_run
        if analyzer is None:
            from .analysis import analyze as analyzer
        def create(index, proposals):
            folder=out/f'generation-{index:03d}'; folder.mkdir(exist_ok=True)
            generation=dict(index=index, candidates=[])
            for i,(candidate,parent) in enumerate(proposals):
                identifier=f'candidate-{i:04d}'; path=folder/identifier
                if (path/'resolved.yaml').exists():
                    if design_hash(load(path/'resolved.yaml'))!=design_hash(candidate):
                        raise ValueError('Incomplete proposal conflicts with requested design')
                else:
                    build_run(candidate,path)
                generation['candidates'].append(dict(id=identifier, config=str((path/'resolved.yaml').relative_to(out)),
                    viewer=str((path/'viewer.html').relative_to(out)), parent_sha256=parent,
                    design_sha256=design_hash(candidate), parameters={k:v for k,v in candidate.optimized.model_dump().items() if not k.startswith('lf_')},
                    status='proposed', score=None, rank=None))
            state['generations'].append(generation); publish(out,state)
        if not state['generations']:
            create(0, [(design,None), *offspring([design],population-1,seed,0)])
        try:
            for index in range(generations):
                generation=state['generations'][index]
                if propose_only: break
                for candidate in generation['candidates']:
                    if candidate['status'] in ('complete','unqualified','failed'): continue
                    cfg=out/candidate['config']; d=load(cfg)
                    if design_hash(d)!=candidate['design_sha256']: raise ValueError('Saved candidate was edited; start a new campaign')
                    candidate['status']='running'; state['status']='running'; publish(out,state)
                    root=cfg.parent; attempt=0
                    # Keep interrupted attempts for inspection; never overwrite raw data.
                    while (root/f'analysis-{attempt:03d}').exists(): attempt+=1
                    result=root/f'analysis-{attempt:03d}'
                    try:
                        extra={"max_edge_mm":max_edge_mm} if max_edge_mm is not None else {}
                        analyzer(cfg,result,backend,max_frequency,edges,**extra)
                        response=Response.model_validate_json((result/'response.json').read_text())
                        candidate['viewer']=str((result/'viewer.html').relative_to(out))
                        candidate['response']=str((result/'response.json').relative_to(out))
                        candidate['status']='unqualified'
                        if response.analysis_status=='mesh_converged':
                            candidate['score']=objective(d,response); candidate['status']='complete'
                            viewer_state=result/'viewer-state.json'
                            if viewer_state.exists():
                                from .viewer import publish as publish_viewer
                                local=json.loads(viewer_state.read_text())
                                local['baseline']['result']['score']=candidate['score']
                                publish_viewer(result,local)
                    except (ValueError,RuntimeError,OSError,ImportError) as exc:
                        candidate['status']='failed'; candidate['error']=str(exc)
                    publish(out,state)
                ranked=sorted([c for c in generation['candidates'] if c['score'] is not None],key=lambda c:c['score']['objective'])
                for rank,c in enumerate(ranked,1): c['rank']=rank
                if not ranked:
                    state['status']='blocked: no qualified candidates'; publish(out,state); return state
                if len(state['generations'])==index+1:
                    parents=[load(out/c['config']) for c in ranked[:max(1,population//2)]]
                    # Preserve an elite and its lineage; analysis is rerun for independent evidence.
                    create(index+1, [(parents[0],design_hash(parents[0])),*offspring(parents,population-1,seed,index+1)])
                publish(out,state)
            state['status']='proposed' if propose_only else 'complete; next generation proposed'
            publish(out,state); return state
        except BaseException:
            state['status']='interrupted; resume to continue'; publish(out,state); raise
