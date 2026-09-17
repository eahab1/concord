import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("meshio")
pytest.importorskip("gmsh")

from concord.acoustic_mesh import make_mesh,read_mesh,check_boundary,reflect_quarter
from concord.analysis import prepare,solve_job,compare,response_from,LIMITS
from concord.config import Design
from concord.viewer import initialize,publish,attach_result
from concord.config import save


def test_prepared_boundary_and_source_area(tmp_path):
    _,report=prepare(Design(),tmp_path/"mesh",24)
    assert report["boundary_contract_pass"]
    assert report["boundary_edges"]==0
    assert report["source_area_m2"]==pytest.approx(np.pi*.0127**2,rel=.003)
    assert report["signed_volume_m3"]<0
    v,t,tags=read_mesh(tmp_path/"mesh/boundary.msh")
    assert set(tags)=={1,2,12}
    _,fullt,_=reflect_quarter(v,t,tags)
    assert len(fullt)==4*len(t)
    wrong=t.copy()
    wrong[tags==12]=wrong[tags==12][:,[0,2,1]]
    with pytest.raises(ValueError):
        check_boundary(v,wrong,tags)


def test_job_contract_and_hash_rejected_before_solve(tmp_path):
    folder=tmp_path/"job"
    job,_=prepare(Design(),folder,24)
    job["symmetry"]="none"
    (folder/"bem-job.json").write_text(json.dumps(job))
    with pytest.raises(ValueError,match="contract"):
        solve_job(folder/"bem-job.json",tmp_path/"result","bempp-cpu")
    job["symmetry"]="yz+xz"
    job["mesh_sha256"]="0"*64
    (folder/"bem-job.json").write_text(json.dumps(job))
    with pytest.raises(ValueError,match="hash"):
        solve_job(folder/"bem-job.json",tmp_path/"result","bempp-cpu")
    job["status"]="blocked_concept_geometry"
    (folder/"bem-job.json").write_text(json.dumps(job))
    with pytest.raises(ValueError,match="prepare-bem"):
        solve_job(folder/"bem-job.json",tmp_path/"result","bempp-cpu")


def test_compare_and_response_normalization():
    design=Design()
    raw={"pressure":np.ones((13,2,3),dtype=complex)*(1+2j),"loading":np.ones(13,dtype=complex),
         "angles":np.array([-90.,0.,90.]),"frequencies":np.array(design.manual.frequencies_hz),"backend":"test"}
    assert all(x==0 for x in compare(raw,raw).values())
    changed={**raw,"pressure":raw["pressure"]*1.1}
    assert compare(changed,raw)["complex_relative_l2"]>LIMITS["complex_relative_l2"]
    response=response_from(raw,design,"mesh_converged")
    assert np.max(np.abs(response.horizontal_db))==0
    raw["pressure"][:,:,1]=0
    with pytest.raises(ValueError,match="on-axis"):
        response_from(raw,design)


def test_unrankable_real_polars_can_be_viewed(tmp_path):
    design=Design()
    save(design,tmp_path/"resolved.yaml")
    state=initialize(tmp_path,design,"resolved.yaml",0)
    state["status"]="complete";publish(tmp_path,state)
    raw={"pressure":np.ones((13,2,3),dtype=complex),"angles":np.array([-90.,0.,90.]),
         "frequencies":np.array(design.manual.frequencies_hz),"backend":"test fixture"}
    for status in ("unqualified","mesh_converged"):
        response=response_from(raw,design,status)
        (tmp_path/"response.json").write_text(response.model_dump_json())
        result=attach_result(tmp_path,"baseline",tmp_path/"response.json")
        assert result["objective"] is None
        assert result["reason"]
    stored=json.loads((tmp_path/"viewer-state.json").read_text())
    assert stored["baseline"]["result"]["response"]["horizontal_db"]


def test_hornlab_wrapper_rejects_unprepared_dictionary():
    from concord.bem import HornLabMetalBackend
    with pytest.raises(ValueError,match="prepared"):
        HornLabMetalBackend().solve({})


def test_sub_two_mm_mesh_has_valid_source_and_tags(tmp_path):
    # Small reference fixture verifies the former 2 mm limit and size floor
    # without adding a 75k-element full horn to routine tests.
    report=make_mesh(Design(),tmp_path/'fine.msh',1.25,reference=True)
    assert report['boundary_contract_pass']
    assert report['max_edge_m'] < .00286
    assert report['source_area_m2']==pytest.approx(np.pi*.04**2,rel=.005)
    with pytest.raises(ValueError,match='0.5'):
        make_mesh(Design(),tmp_path/'invalid.msh',.1)


def test_mesh_cost_is_an_array_size_not_peak_memory():
    from concord.preflight import mesh_cost
    cost=mesh_cost({'quarter_vertices':1000},100)
    assert cost['one_complex128_pressure_matrix_gib']==pytest.approx(16e6/2**30)
    assert cost['one_complex128_cross_matrix_gib']==pytest.approx(16e5/2**30)
    assert 'not peak RAM' in cost['memory_note']


def test_frequency_comparison_flags_only_failed_frequency():
    from concord.analysis import compare_by_frequency
    raw=dict(pressure=np.ones((2,2,3),complex),loading=np.ones(2,complex),
             frequencies=np.array([500.,10000.]),angles=np.array([-90.,0.,90.]))
    changed={**raw,'pressure':raw['pressure'].copy()}
    changed['pressure'][1]*=1.2
    rows=compare_by_frequency(raw,changed)
    assert rows[0]['passed'] and not rows[1]['passed']
    with pytest.raises(ValueError,match='matching'):
        compare_by_frequency(raw,{**changed,'angles':np.array([-80.,0.,80.])})


def test_metal_precision_backend_is_explicit(monkeypatch):
    import concord.analysis as analysis
    calls=[]
    def fake(path,frequencies,**kwargs):
        calls.append(kwargs);return kwargs
    monkeypatch.setattr(analysis,'metal_solve',fake)
    analysis.run_backend('hornlab-metal','mesh',[1000.])
    analysis.run_backend('hornlab-metal-f32','mesh',[1000.])
    assert [c['precision'] for c in calls]==['float64','float32']
    with pytest.raises(ValueError,match='Unknown'):
        analysis.run_backend('hornlab-metal-gmres','mesh',[1000.])


@pytest.mark.parametrize('cap',[1.9,1.3,.7])
def test_local_refinement_preserves_area_orientation_and_shared_edges(cap):
    from concord.local_refinement import limit_edges
    v=np.array([[0,0,0],[2,0,0],[2,1,0],[0,1,0]],float)
    t=np.array([[0,1,2],[0,2,3]])
    v,t,tags,rounds=limit_edges(v,t,[1,12],cap)
    face=v[t];normals=np.cross(face[:,1]-face[:,0],face[:,2]-face[:,0])
    assert np.all(normals[:,2]>0)
    assert normals[:,2].sum()/2==pytest.approx(2.)
    assert set(tags)=={1,12}
    edges=np.sort(np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]),axis=1)
    unique,counts=np.unique(edges,axis=0,return_counts=True)
    assert np.max(np.linalg.norm(v[unique[:,0]]-v[unique[:,1]],axis=1))<=cap*(1+1e-12)
    for e in unique[counts==1]:
        points=v[e]
        assert any(np.allclose(points[:,axis],value) for axis,value in [(0,0),(0,2),(1,0),(1,1)])


def test_local_cap_preserves_acoustic_boundary(tmp_path):
    r=make_mesh(Design(),tmp_path/'local.msh',3.,reference=True,max_edge_mm=2.)
    assert r['boundary_contract_pass']
    assert r['max_edge_m']<=.002*(1+1e-12)
    v,t,tags=read_mesh(tmp_path/'local.msh')
    assert check_boundary(v,t,tags)['boundary_edges']==0


def test_low_memory_metal_submits_one_frequency_at_a_time(monkeypatch):
    from types import SimpleNamespace
    hornlab=pytest.importorskip('hornlab_metal_bem')
    import hornlab_metal_bem.metal as metal
    import concord.acoustic_mesh as acoustic
    from concord.analysis import metal_solve
    monkeypatch.setattr(metal,'discover_native_runtime',lambda **k:SimpleNamespace(available=True))
    monkeypatch.setattr(acoustic,'read_mesh',lambda p:(np.array([[0.,0.,-.225]]),None,None))
    calls=[]
    def solve(path,frequencies,config):
        calls.append(list(frequencies))
        return SimpleNamespace(pressure_complex=np.ones((len(frequencies),2,3),complex),
            impedance=np.ones(len(frequencies),complex),observation_angles_deg=np.array([-90,0,90]),
            frequencies_hz=np.array(frequencies),native_diagnostics=[{'frequency':f} for f in frequencies])
    monkeypatch.setattr(hornlab,'solve_frequencies',solve)
    raw=metal_solve('unused',[500.,2000.],precision='float32')
    assert calls==[[500.],[2000.]]
    assert raw['pressure'].shape==(2,2,3)
    assert raw['backend']=='hornlab-metal-f32'
    assert len(raw['diagnostics'])==2
