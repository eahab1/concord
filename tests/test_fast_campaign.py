import json
import pytest
from concord.config import Design, save, load
from concord.fast_campaign import run
from concord.result_cache import ResultCache
from concord.viewer import design_hash
from test_campaign import response


def setup(tmp_path):
    cfg=tmp_path/'config.yaml'; save(Design(),cfg)
    calls={'screen':0,'validate':0}
    def screen(cfg,dest,*args,**kwargs):
        calls['screen']+=1;dest.mkdir()
        (dest/'response.json').write_text(response(load(cfg),False).model_dump_json())
    def validate(cfg,dest,*args,**kwargs):
        calls['validate']+=1;dest.mkdir()
        (dest/'response.json').write_text(response(load(cfg)).model_dump_json())
    return cfg,calls,dict(screener=screen,analyzer=validate,population=2,generations=2)


def test_elite_cache_separate_scores_and_resume(tmp_path):
    cfg,calls,kw=setup(tmp_path);out=tmp_path/'search'
    s=run(cfg,out,**kw)
    assert calls=={'screen':3,'validate':1}
    assert len(s['generations'])==3
    elite=s['generations'][1]['candidates'][0]
    assert elite['screening']['cache_hit'] and elite['validation']['cache_hit']
    assert elite['screening']['score']['qualification']=='provisional'
    assert elite['validation']['score']['qualification']=='validated'
    assert 'validation' not in s['generations'][0]['candidates'][1]
    run(cfg,out,resume=True,**kw)
    assert calls=={'screen':3,'validate':1}
    with pytest.raises(ValueError,match='match'):
        run(cfg,out,resume=True,edges=(23,16,10),**kw)
    with pytest.raises(ValueError,match='match'):
        run(cfg,out,resume=True,backend='hornlab-metal-f32',**kw)
    with pytest.raises(ValueError,match='match'):
        run(cfg,out,resume=True,frequency_points=3,min_frequency=1000,**kw)


def test_interrupt_preserves_partial_attempt(tmp_path):
    cfg,calls,kw=setup(tmp_path);out=tmp_path/'search'
    def interrupt(cfg,dest,*args,**kwargs):
        dest.mkdir();raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):run(cfg,out,**dict(kw,screener=interrupt))
    s=run(cfg,out,resume=True,**kw)
    c=s['generations'][0]['candidates'][0]
    assert 'screening-001' in c['screening']['response']
    assert (out/'generation-000/candidate-0000/screening-000').exists()


def test_no_validation_no_breeding(tmp_path):
    cfg,calls,kw=setup(tmp_path)
    s=run(cfg,tmp_path/'search',**dict(kw,analyzer=kw['screener']))
    assert s['status'].startswith('blocked') and len(s['generations'])==1
    assert s['generations'][0]['candidates'][0]['validation']['score'] is None


def test_synthetic_screen_cannot_rank(tmp_path):
    cfg,calls,kw=setup(tmp_path)
    def fake(cfg,dest,*args,**kwargs):
        dest.mkdir()
        (dest/'response.json').write_text(response(load(cfg)).model_copy(update={'synthetic':True}).model_dump_json())
    s=run(cfg,tmp_path/'search',**dict(kw,screener=fake))
    assert s['status'].startswith('blocked') and calls['validate']==0


def test_corrupt_cache_recomputed_and_reference_reused(tmp_path):
    cache=ResultCache(tmp_path/'cache','runtime1'); d=Design();calls=[]
    contract=dict(design_sha256=design_hash(d),frequencies_hz=d.manual.frequencies_hz)
    def compute(dest):
        calls.append(dest);dest.mkdir();(dest/'response.json').write_text(response(d).model_dump_json())
    a=cache.evaluate(contract,tmp_path/'a',compute)
    assert not a['cache_hit']
    assert cache.evaluate(contract,tmp_path/'b',compute)['cache_hit']
    payload=cache.root/a['cache_key']/'payload/response.json'
    payload.write_text('corrupt')
    assert not cache.evaluate(contract,tmp_path/'c',compute)['cache_hit']
    assert len(calls)==2
    assert not ResultCache(cache.root,'runtime2').evaluate(contract,tmp_path/'d',compute)['cache_hit']
    refs=[]
    def reference(dest):
        refs.append(dest);dest.mkdir();(dest/'reference-check.json').write_text('{"passed": true}')
    cache.evaluate({'stage':'reference'},tmp_path/'r1',reference,reference=True)
    assert cache.evaluate({'stage':'reference'},tmp_path/'r2',reference,reference=True)['cache_hit']
    assert len(refs)==1


def test_failed_reference_not_cached(tmp_path):
    cache=ResultCache(tmp_path/'cache','runtime');calls=[]
    def bad(dest):
        calls.append(dest);dest.mkdir();(dest/'reference-check.json').write_text('{"passed": false}')
    for n in range(2):
        with pytest.raises(ValueError,match='Failed reference'):
            cache.evaluate({'stage':'reference'},tmp_path/f'r{n}',bad,reference=True)
    assert len(calls)==2


def test_changed_checkpoint_rejected(tmp_path):
    cfg,calls,kw=setup(tmp_path);out=tmp_path/'search'
    s=run(cfg,out,**kw)
    p=out/s['generations'][0]['candidates'][0]['config']
    d=load(p);save(d.model_copy(update={'optimized':d.optimized.model_copy(update={'mouth_width_mm':390})}),p)
    with pytest.raises(ValueError,match='edited'):run(cfg,out,resume=True,**kw)


def test_screening_only_generations_never_validate(tmp_path):
    cfg,calls,kw=setup(tmp_path)
    s=run(cfg,tmp_path/'search',finalists=0,**kw)
    assert calls=={'screen':3,'validate':0}
    assert s['status']=='complete; next generation proposed'
    assert len(s['generations'])==3
    for g in s['generations'][:2]:
        assert all('validation' not in c for c in g['candidates'])
        assert all(c['screening']['score']['qualification']=='provisional' for c in g['candidates'])
    run(cfg,tmp_path/'search',resume=True,finalists=0,**kw)
    assert calls=={'screen':3,'validate':0}
    with pytest.raises(ValueError,match='match'):
        run(cfg,tmp_path/'search',resume=True,finalists=1,**kw)
