import json
from pathlib import Path
import pytest
from concord.config import Design, save, load
from concord.frequency import resolve
from concord.campaign import run, objective, offspring
from concord.viewer import design_hash
from concord.bem import Response


def test_frequency_sweep():
    assert resolve(Design(), 4000, 1000, 3).manual.frequencies_hz == pytest.approx([1000,2000,4000])
    assert resolve(Design(), 4000, 1000, 3, 'linear').manual.frequencies_hz == [1000,2500,4000]
    assert resolve(Design(), 2000, 1250).manual.frequencies_hz == [1250,1600,2000]
    for args in [(2000,None,5),(2000,3000,5),(2000,1000,1),(2000,2000,2),(float('nan'),1000,3),(500,100,None)]:
        with pytest.raises(ValueError): resolve(Design(),*args)


def test_mutation_deterministic_and_fixed():
    parents=[Design()]
    a=offspring(parents,3,42,1); b=offspring(parents,3,42,1)
    assert [design_hash(d) for d,_ in a]==[design_hash(d) for d,_ in b]
    for d,parent in a:
        assert d.fixed==parents[0].fixed
        assert d.manual==parents[0].manual
        assert d.optimized.lf_slot_width_mm==parents[0].optimized.lf_slot_width_mm
        assert parent==design_hash(parents[0])


def response(design, qualified=True):
    return Response(design_sha256=design_hash(design),solver='test fixture only',synthetic=False,
                    analysis_status='mesh_converged' if qualified else 'unqualified',
                    frequencies_hz=design.manual.frequencies_hz,angles_deg=[-90,0,90],
                    horizontal_db=[[-2,0,-2]]*len(design.manual.frequencies_hz),
                    vertical_db=[[-20,0,-20]]*len(design.manual.frequencies_hz))


def test_score_handles_truncated_beam_and_rejects_unqualified():
    d=Design(); assert objective(d,response(d))['objective']>0
    with pytest.raises(ValueError): objective(d,response(d,False))
    with pytest.raises(ValueError): objective(d,response(d).model_copy(update={'synthetic':True}))


def test_generations_resume_and_proposals(tmp_path):
    config=tmp_path/'config.yaml'; save(Design(),config); out=tmp_path/'run'; calls=[]
    def fake_analyze(cfg,dest,*args):
        calls.append(cfg);dest.mkdir()
        (dest/'response.json').write_text(response(load(cfg)).model_dump_json())
    kwargs=dict(population=2,generations=1,min_frequency=1000,frequency_points=3,analyzer=fake_analyze)
    s=run(config,out,propose_only=True,**kwargs)
    assert not calls and len(s['generations'])==1
    s=run(config,out,resume=True,**kwargs)
    assert len(calls)==2 and len(s['generations'])==2
    assert sorted(c['rank'] for c in s['generations'][0]['candidates'])==[1,2]
    assert all(c['status']=='proposed' for c in s['generations'][1]['candidates'])
    run(config,out,resume=True,**kwargs); assert len(calls)==2
    kwargs['generations']=2
    run(config,out,resume=True,**kwargs); assert len(calls)==4
    kwargs['frequency_points']=4
    with pytest.raises(ValueError,match='match'):run(config,out,resume=True,**kwargs)


def test_unqualified_blocks_breeding(tmp_path):
    cfg=tmp_path/'c.yaml';save(Design(),cfg)
    def fake(cfg,dest,*args):
        dest.mkdir();(dest/'response.json').write_text(response(load(cfg),False).model_dump_json())
    s=run(cfg,tmp_path/'run',population=2,generations=1,analyzer=fake)
    assert s['status'].startswith('blocked') and len(s['generations'])==1


def test_interrupted_solve_resumes_in_new_attempt(tmp_path):
    cfg=tmp_path/'c.yaml';save(Design(),cfg);out=tmp_path/'run'
    def interrupt(cfg,dest,*args):
        dest.mkdir();raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):run(cfg,out,population=2,generations=1,analyzer=interrupt)
    def complete(cfg,dest,*args):
        dest.mkdir();(dest/'response.json').write_text(response(load(cfg)).model_dump_json())
    result=run(cfg,out,population=2,generations=1,resume=True,analyzer=complete)
    c=result['generations'][0]['candidates'][0]
    assert 'analysis-001' in c['response']
    assert (out/Path(c['config']).parent/'analysis-000').is_dir()


@pytest.mark.parametrize('state', [
    {'seed':42,'count':8,'status':'proposed_only_not_simulated'},
    {}, [], {'version':1,'settings':{},'generations':None},
])
def test_resume_rejects_legacy_or_invalid_state_without_changes(tmp_path, state, capsys):
    from concord.cli import main
    cfg=tmp_path/'config.yaml';save(Design(),cfg)
    out=tmp_path/'existing';out.mkdir()
    (out/'campaign.json').write_text(json.dumps(state))
    (out/'viewer.html').write_text('original viewer')
    (out/'candidate-0000.yaml').write_text('original candidate')
    before={p.name:p.read_bytes() for p in out.iterdir()}
    assert main(['campaign',str(cfg),'--out',str(out),'--resume'])==2
    error=capsys.readouterr().err
    assert 'Traceback' not in error
    assert ('legacy' if isinstance(state,dict) and state.get('count') else 'Invalid') in error
    assert all((out/name).read_bytes()==data for name,data in before.items())


def test_local_cap_is_part_of_resume_contract(tmp_path):
    cfg=tmp_path/'config.yaml';save(Design(),cfg)
    out=tmp_path/'campaign'
    state=run(cfg,out,population=2,generations=1,propose_only=True,max_edge_mm=2.8)
    assert state['settings']['max_edge_mm']==2.8
    with pytest.raises(ValueError,match='match'):
        run(cfg,out,population=2,generations=1,propose_only=True,resume=True,max_edge_mm=2.7)
    with pytest.raises(ValueError,match='match'):
        run(cfg,out,population=2,generations=1,propose_only=True,resume=True)
    seen=[]
    def fake(cfg,dest,*args,**kwargs):
        seen.append(kwargs['max_edge_mm']);dest.mkdir()
        (dest/'response.json').write_text(response(load(cfg)).model_dump_json())
    run(cfg,out,population=2,generations=1,resume=True,max_edge_mm=2.8,analyzer=fake)
    assert seen==[2.8,2.8]
