from importlib.resources import files
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from concord.config import Design,load,bounds
from concord.geometry import build
from concord.mesh import audit
from concord.cli import main,build_run,digest
from concord.bem import Response,HornLabMetalBackend,BoundaryLabBackend
from concord.optimization import candidates,beamwidth,score

ROOT=Path(__file__).resolve().parents[1]


def test_baseline_and_defaults_agree():
    assert load(ROOT/"configs/baseline.yaml")==Design()


@pytest.mark.parametrize("field,value",[("superformula_m",4),("superformula_m",8.1),("lf_count",4),("lf_driver","other"),("hf_driver","other"),("throat_diameter_mm",36)])
def test_fixed_invariants(field,value):
    data=Design().model_dump()
    data["fixed"][field]=value
    with pytest.raises(ValidationError):
        Design.model_validate(data)


@pytest.mark.parametrize("mutation",[
    lambda d:d["optimized"].update(sf_m=8),
    lambda d:(d["manual"].update(hf_only=False),d["optimized"].update(lf_slot_center_x_mm=35,lf_slot_width_mm=45,hf_aperture_width_mm=22)),
    lambda d:d["optimized"].update(hf_aperture_height_mm=250),
    lambda d:d["manual"].update(array_splay_deg=[1]),
    lambda d:d["manual"].update(frequencies_hz=[]),
    lambda d:d["manual"].update(frequencies_hz=[2000,1000]),
    lambda d:d["manual"].update(sound_speed_m_s=float("nan")),
    lambda d:d["manual"].update(module_depth_mm=30),
])
def test_invalid_configuration(mutation):
    data=Design().model_dump()
    mutation(data)
    with pytest.raises(ValidationError):
        Design.model_validate(data)


def test_duplicate_yaml_rejected(tmp_path):
    path=tmp_path/"bad.yaml"
    path.write_text("fixed:\n  superformula_m: 4\n  superformula_m: 8\n")
    with pytest.raises(ValueError,match="Duplicate"):
        load(path)


def test_preserved_ath(tmp_path):
    target=tmp_path/"v2.ath"
    assert main(["export-ath","--out",str(target)])==0
    text=target.read_text()
    assert target.read_bytes()==files("concord").joinpath("data/concord_v2.ath").read_bytes()
    expected={"Throat.Profile":"1","Throat.Diameter":"25.4","Throat.Angle":"0","Length":"140",
              "Term.s":"1.165551339","Term.q":"0.8006927592","Term.n":"4.948341464","OS.k":"2.326215907",
              "Slot.Length":"0","GCurve.Type":"2","GCurve.Width":"64.69512195","GCurve.Dist":"0.2776715106",
              "GCurve.SF":"1.375827392,1.437994835,8,2.152737774,5.245161223,3.01531782",
              "GCurve.Rot":"0","GCurve.AspectRatio":"1","Morph.TargetWidth":"353","Morph.TargetHeight":"353",
              "Morph.TargetShape":"1","Morph.FixedPart":"0.3455704293","Morph.Rate":"3.693701077",
              "Morph.CornerRadius":"14","Morph.AllowShrinkage":"1","Mesh.AngularSegments":"64",
              "Mesh.LengthSegments":"12","Mesh.CornerSegments":"4","Mesh.ThroatResolution":"4",
              "Mesh.MouthResolution":"22","Mesh.Quadrants":"1234","Mesh.SubdomainSlices":"",
              "Spacing":"29,29,29,29","Depth":"330","EdgeRadius":"6","EdgeType":"2",
              "FrontResolution":"36,36,36,36","BackResolution":"48,48,48,48","ABEC.SimType":"2"}
    parsed={k.strip():v.strip() for line in text.splitlines() if "=" in line for k,v in [line.split("=",1)]}
    for key,value in expected.items():
        assert parsed[key]==value
    assert main(["export-ath","--out",str(target)])==2


def test_mesh_topology_units_and_sources():
    d=Design()
    mesh=build(d)
    report=audit(mesh,0.0035)
    assert report["degenerate_triangles"]==0
    assert report["nonmanifold_edges"]==0
    assert report["inconsistent_winding_edges"]==0
    assert report["boundary_edges"]==d.manual.angular_segments
    assert set(report["tag_counts"])=={1,2}
    assert max(v[2] for v in mesh.vertices)==pytest.approx(0.14)
    assert max(v[0] for v in mesh.vertices)==pytest.approx(0.19)
    assert not report["bem_ready"]
    assert not report["wavelength_resolution_pass"]


def test_reproducible_build_and_no_overwrite(tmp_path):
    a,b=tmp_path/"a",tmp_path/"b"
    build_run(Design(),a)
    build_run(Design(),b)
    assert (a/"concept.msh").read_bytes()==(b/"concept.msh").read_bytes()
    job=json.loads((a/"bem-job.json").read_text())
    assert job["design_sha256"]==digest(Design())
    assert job["status"]=="blocked_concept_geometry"
    with pytest.raises(ValueError,match="empty"):
        build_run(Design(),a)


def test_candidates_bounded_reproducible_and_locked():
    a=candidates(Design(),20,42)
    assert a==candidates(Design(),20,42)
    assert a!=candidates(Design(),20,43)
    for candidate in a:
        assert candidate.fixed==Design().fixed
        assert candidate.manual==Design().manual
        for key,(lo,hi) in bounds().items():
            assert lo<=getattr(candidate.optimized,key)<=hi


def response():
    angles=list(range(-90,91,5))
    # Analytic test fixture only; never emitted as a simulated response.
    return Response(design_sha256=digest(Design()),solver="unit-test-fixture",
                    frequencies_hz=Design().manual.frequencies_hz,angles_deg=angles,
                    horizontal_db=[[-6*(a/45)**2 for a in angles]]*13,
                    vertical_db=[[-6*(a/5)**2 for a in angles]]*13)


def test_score_known_crossings():
    assert score(Design(),response())["objective"]==pytest.approx(0)
    assert beamwidth([-10,0,10],[-12,0,-12])==10
    with pytest.raises(ValueError,match="crossings"):
        beamwidth([-10,0,10],[-1,0,-1])
    data=response().model_dump()
    data["synthetic"]=True
    with pytest.raises(ValueError,match="Synthetic"):
        score(Design(),Response.model_validate(data))


def test_response_shape_and_hash(tmp_path):
    data=response().model_dump()
    data["horizontal_db"][0]=[0]
    with pytest.raises(ValidationError):
        Response.model_validate(data)
    data=response().model_dump()
    data["design_sha256"]="0"*64
    path=tmp_path/"response.json"
    path.write_text(json.dumps(data))
    assert main(["score",str(ROOT/"configs/baseline.yaml"),str(path)])==2


@pytest.mark.parametrize("backend",[BoundaryLabBackend])
def test_unimplemented_solver_cannot_fake_results(backend):
    with pytest.raises(NotImplementedError):
        backend().solve({})


def test_gmsh_reads_tags_and_refines(tmp_path):
    gmsh=pytest.importorskip("gmsh")
    build_run(Design(),tmp_path/"run")
    source=tmp_path/"run/concept.msh"
    target=tmp_path/"refined.msh"
    assert main(["refine",str(source),"--out",str(target)])==0
    gmsh.initialize()
    try:
        gmsh.open(str(target))
        assert {tag for dim,tag in gmsh.model.getPhysicalGroups(2)}=={1,2}
        assert gmsh.model.getPhysicalName(2,2)=="hf_source"
        types,tags,_=gmsh.model.mesh.getElements(2)
        assert list(types)==[2]
        assert sum(map(len,tags))==4*len(build(Design()).triangles)
    finally:
        gmsh.finalize()


def test_hf_only_freezes_lf_and_has_one_connected_surface():
    from concord.bem import job_spec
    design=Design()
    mesh=build(design)
    neighbors={i:set() for i in range(len(mesh.vertices))}
    for a,b,c,_ in mesh.triangles:
        for u,v in ((a,b),(b,c),(c,a)):
            neighbors[u].add(v)
            neighbors[v].add(u)
    seen=set()
    todo=[0]
    while todo:
        v=todo.pop()
        if v not in seen:
            seen.add(v)
            todo.extend(neighbors[v]-seen)
    assert len(seen)==len(mesh.vertices)
    assert {t[3] for t in mesh.triangles}=={1,2}
    for candidate in candidates(design,10,42):
        for key,value in design.optimized.model_dump().items():
            if key.startswith('lf_'):
                assert getattr(candidate.optimized,key)==value
    job=job_spec(design,digest(design),'test')
    assert job['source_plan']['tags']==[2]
    assert set(job['physical_groups'])=={1,2}
    assert not any(b.startswith('LF') for b in job['blockers'])


def test_full_concept_remains_explicit_opt_in():
    data=Design().model_dump()
    data['manual']['hf_only']=False
    assert {t[3] for t in build(Design.model_validate(data)).triangles}=={1,2,3,4}
