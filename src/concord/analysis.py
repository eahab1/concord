"""Reproducible baseline qualification, mesh ladder, solver adapters and artifacts."""
from pathlib import Path
import hashlib
import json
import platform
from importlib.metadata import version

from .config import Design,load,save
from .bem import Response
from .viewer import design_hash,atomic_text

HORNLAB_REVISION = "2c2c712c7bafc2de7ab08a571d9f4211cf9624b5"
LIMITS = {"polar_max_db": .5, "complex_relative_l2": .05,
          "on_axis_max_db": .5, "loading_relative_l2": .10}


def write(path,value):
    atomic_text(path,json.dumps(value,indent=2,allow_nan=False)+"\n")


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(design,out,edge_mm,max_edge_mm=None):
    from .acoustic_mesh import make_mesh
    out.mkdir(parents=True,exist_ok=False)
    save(design,out/"resolved.yaml")
    report=make_mesh(design,out/"boundary.msh",edge_mm,max_edge_mm=max_edge_mm)
    report["target_max_edge_m"]=design.manual.sound_speed_m_s/(6*max(design.manual.frequencies_hz))
    report["wavelength_resolution_pass"]=report["max_edge_m"]<=report["target_max_edge_m"]
    write(out/"mesh-report.json",report)
    job={"schema_version":2,"status":"prepared_hf_baffle_approximation", "mesh":"boundary.msh",
         "config":"resolved.yaml", "design_sha256":design_hash(design),"mesh_sha256":file_hash(out/"boundary.msh"),
         "frequencies_hz":design.manual.frequencies_hz,"speed_m_s":design.manual.sound_speed_m_s,
         "density_kg_m3":design.manual.density_kg_m3,"angle_step_deg":2,"distance_m":10,
         "formulation":"coupled_infinite_baffle","symmetry":"yz+xz", "source_tag":2,"aperture_tag":12,
         "normal_velocity_m_s":1,"mesh_units":"m"}
    write(out/"bem-job.json",job)
    return job,report


def metal_solve(path,frequencies,*,speed=343.,density=1.21,angle_step=2.,distance=10.,precision="float64"):
    import numpy as np
    from hornlab_metal_bem import native_config,solve_frequencies,ObservationConfig,ObservationFrame
    from hornlab_metal_bem.metal import discover_native_runtime
    from .acoustic_mesh import read_mesh
    status=discover_native_runtime(run_smoke_test=True)
    if not status.available:
        raise RuntimeError("HornLab Metal unavailable: "+"; ".join(status.unavailable_reasons)+
                           ". Use --backend bempp-cpu, or run directly in Terminal with GPU access.")
    if precision not in ("float32","float64"):
        raise ValueError("Metal precision must be float32 or float64")
    origin=np.zeros(3)
    frame=ObservationFrame(axis=np.array([0.,0.,1.]),origin=origin,u=np.array([1.,0.,0.]),
                           v=np.array([0.,1.,0.]),mouth_center=origin,source_center=np.array([0.,0.,float(read_mesh(path)[0][:,2].min())]))
    config=native_config(velocity_sources={2:1.},velocity_mode="velocity",speed_of_sound=speed,
                         air_density=density,aperture_tag=12,native_symmetry_plane="yz+xz",
                         dense_solve_dtype=precision,frame_override=frame,mesh_repair_normals=False,
                         observation=ObservationConfig(distance_m=distance,angle_min_deg=-90,angle_max_deg=90,
                                                       angle_count=round(180/angle_step)+1,
                                                       planes=["horizontal","vertical"],origin="mouth"))
    # The low-memory backend never batches multiple frequency factorizations.
    batches=[[f] for f in frequencies] if precision=="float32" else [frequencies]
    results=[]
    for batch in batches:
        print(f"Metal {precision}: {', '.join(f'{f:g}' for f in batch)} Hz · {path}",flush=True)
        results.append(solve_frequencies(str(path),batch,config))
    return {"pressure":np.concatenate([r.pressure_complex for r in results]),
            "loading":np.concatenate([np.atleast_1d(r.impedance) for r in results]),
            "angles":results[0].observation_angles_deg,
            "frequencies":np.concatenate([r.frequencies_hz for r in results]),
            "diagnostics":[item for r in results for item in r.native_diagnostics],
            "backend":"hornlab-metal" if precision=="float64" else "hornlab-metal-f32",
            "phase_convention":"exp(-i*omega*t)","normal_velocity_m_s":1.,"observation_distance_m":distance}


def run_backend(backend,path,frequencies,**kwargs):
    if backend=="bempp-cpu":
        from .cpu_bem import solve
        return solve(path,frequencies,**kwargs)
    if backend in ("hornlab-metal","hornlab-metal-f32"):
        return metal_solve(path,frequencies,precision="float32" if backend.endswith("-f32") else "float64",**kwargs)
    raise ValueError("Unknown acoustic backend")


def response_from(raw,design,status="unqualified",notes=None):
    import numpy as np
    pressure=raw["pressure"]
    zero=np.flatnonzero(abs(raw["angles"])<1e-8)
    if len(zero)!=1 or not np.all(np.isfinite(pressure)) or np.any(abs(pressure[:,:,zero[0]])<1e-20):
        raise ValueError("Invalid pressure or zero on-axis reference")
    db=20*np.log10(np.maximum(abs(pressure/pressure[:,:,zero[0],None]),1e-12))
    return Response(design_sha256=design_hash(design),solver=raw["backend"],
                    frequencies_hz=raw["frequencies"].tolist(),angles_deg=raw["angles"].tolist(),
                    horizontal_db=db[:,0,:].tolist(),vertical_db=db[:,1,:].tolist(),
                    analysis_status=status,analysis_notes=notes or [])


def archive_raw(out,raw,design,mesh_path):
    import numpy as np
    out.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(out/"fields.npz",pressure_pa=raw["pressure"],source_loading_pa_per_m_s=raw["loading"],
                        angles_deg=raw["angles"],frequencies_hz=raw["frequencies"])
    package_names=["numpy","scipy","gmsh","meshio", "bempp-cl" if not raw["backend"].startswith("hornlab-metal") else "hornlab-metal-bem"]
    provenance={"backend":raw["backend"],"phase_convention":raw["phase_convention"],
                "source_normal_velocity_m_s":1,"observation_distance_m":raw["observation_distance_m"],
                "design_sha256":design_hash(design) if design is not None else None,"mesh_sha256":file_hash(mesh_path),
                "platform":platform.platform(),"packages":{p:version(p) for p in package_names},
                "formulation":"coupled_infinite_rigid_baffle","symmetry":"yz+xz",
                "limits":"Ideal uniform-velocity throat; no DH450 electrical response, losses, LF or array.",
                "diagnostics":raw["diagnostics"]}
    if raw["backend"].startswith("hornlab-metal"):
        provenance["hornlab_tested_revision"]=HORNLAB_REVISION
    # Upstream Metal diagnostics may contain arrays or NumPy scalar types.
    write(out/"provenance.json",json.loads(json.dumps(provenance,default=lambda x:x.tolist())))


def solve_job(job_path,out,backend):
    from .acoustic_mesh import read_mesh,check_boundary
    job_path=Path(job_path).resolve()
    job=json.loads(job_path.read_text())
    if job.get("status")!="prepared_hf_baffle_approximation":
        raise ValueError("Run prepare-bem first; preview/concept jobs cannot be solved")
    parent=job_path.parent
    mesh=(parent/job["mesh"]).resolve();config=(parent/job["config"]).resolve()
    if not mesh.is_relative_to(parent) or not config.is_relative_to(parent):
        raise ValueError("Job files must be inside its output directory")
    design=load(config)
    if not design.manual.hf_only or design_hash(design)!=job["design_sha256"] or file_hash(mesh)!=job["mesh_sha256"]:
        raise ValueError("BEM configuration or mesh hash mismatch")
    expected={"formulation":"coupled_infinite_baffle","symmetry":"yz+xz","source_tag":2,"aperture_tag":12,
              "normal_velocity_m_s":1,"mesh_units":"m","frequencies_hz":design.manual.frequencies_hz,
              "speed_m_s":design.manual.sound_speed_m_s,"density_kg_m3":design.manual.density_kg_m3,
              "angle_step_deg":2,"distance_m":10}
    if any(job.get(k)!=v for k,v in expected.items()):
        raise ValueError("Unsupported or inconsistent BEM job contract")
    check_boundary(*read_mesh(mesh))
    out=Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Solution output must be empty")
    out.mkdir(parents=True,exist_ok=True)
    raw=run_backend(backend,mesh,job["frequencies_hz"],speed=job["speed_m_s"],density=job["density_kg_m3"])
    archive_raw(out,raw,design,mesh)
    response=response_from(raw,design,notes=["Single resolution; mesh convergence has not been established."])
    (out/"response.json").write_text(response.model_dump_json(indent=2)+"\n")
    return raw,response


def reference_check(out,backend):
    import numpy as np
    from scipy.special import j1
    from .acoustic_mesh import make_mesh
    out.mkdir(parents=True,exist_ok=False)
    design=Design()
    make_mesh(design,out/"reference.msh",10,reference=True)
    raw=run_backend(backend,out/"reference.msh",[800.,2000.],speed=343.,density=1.21)
    archive_raw(out,raw,None,out/"reference.msh")
    metrics=[]
    for i,f in enumerate(raw["frequencies"]):
        k=2*np.pi*f/343.;r=.04;distance=10.
        expected=-1.21*343*(np.exp(1j*k*np.hypot(distance,r))-np.exp(1j*k*distance))
        zero=int(np.argmin(abs(raw["angles"])))
        ratio=raw["pressure"][i,:,zero]/expected
        argument=k*r*np.sin(np.deg2rad(raw["angles"]))
        airy=np.ones_like(argument);mask=abs(argument)>1e-10
        airy[mask]=2*j1(argument[mask])/argument[mask]
        db=20*np.log10(abs(raw["pressure"][i]/raw["pressure"][i,:,zero,None]))
        delta=float(np.max(abs(db-20*np.log10(abs(airy)))))
        metrics.append({"frequency_hz":float(f),"polar_error_db":delta,
                        "on_axis_magnitude_error_fraction":float(np.max(abs(abs(ratio)-1))),
                        "on_axis_phase_error_deg":float(np.max(abs(np.angle(ratio,deg=True))))})
    passed=all(x["polar_error_db"]<.3 and x["on_axis_magnitude_error_fraction"]<.2
               and x["on_axis_phase_error_deg"]<15 for x in metrics)
    report={"reference":"80 mm baffled piston approximated by 3 mm shallow channel",
            "analytic":"2 J1(ka sin(theta))/(ka sin(theta)); exact on-axis Rayleigh pressure",
            "thresholds":{"polar_db":.3,"magnitude_fraction":.2,"phase_deg":15},
            "passed":passed,"metrics":metrics}
    write(out/"reference-check.json",report)
    if not passed:
        raise ValueError("Reference check failed; see reference-check.json")
    return report


def compare(a,b):
    import numpy as np
    zero=int(np.argmin(abs(b["angles"])))
    pa,pb=a["pressure"],b["pressure"]
    da=20*np.log10(np.maximum(abs(pa/pa[:,:,zero,None]),1e-12))
    db=20*np.log10(np.maximum(abs(pb/pb[:,:,zero,None]),1e-12))
    significant=(da>-25)|(db>-25)
    return {"polar_max_db":float(np.max(abs(da[significant]-db[significant]))),
            "complex_relative_l2":float(np.max(np.linalg.norm(pa-pb,axis=(1,2))/np.linalg.norm(pb,axis=(1,2)))),
            "on_axis_max_db":float(np.max(abs(20*np.log10(abs(pa[:,:,zero]/pb[:,:,zero]))))),
            "loading_relative_l2":float(np.linalg.norm(a["loading"]-b["loading"])/np.linalg.norm(b["loading"]))}



def compare_by_frequency(a,b):
    """Expose failures hidden by band summaries; use the same thresholds."""
    import numpy as np
    if not np.array_equal(a['frequencies'],b['frequencies']) or not np.array_equal(a['angles'],b['angles']):
        raise ValueError('Comparison requires matching frequency and angle grids')
    rows=[]
    for i,f in enumerate(b['frequencies']):
        def one(raw):
            return {**raw, 'pressure':raw['pressure'][i:i+1], 'loading':raw['loading'][i:i+1]}
        metrics=compare(one(a),one(b))
        rows.append({'frequency_hz':float(f),'metrics':metrics,
                     'passed':all(metrics[k]<=limit for k,limit in LIMITS.items())})
    return rows


def analyze(config,out,backend="bempp-cpu",max_frequency=2000,edges=(24.,16.,10.),
            min_frequency=None,frequency_points=None,frequency_spacing="log",max_edge_mm=None,reference_provider=None):
    from .cli import build_run
    from .viewer import attach_result
    design=load(config)
    if not design.manual.hf_only:
        raise ValueError("Analysis requires HF-only geometry")
    original_hash=design_hash(design)
    from .frequency import resolve
    design=resolve(design,max_frequency,min_frequency,frequency_points,frequency_spacing)
    if len(edges)<3 or any(a<=b for a,b in zip(edges,edges[1:])):
        raise ValueError("Use at least three strictly decreasing target edge sizes")
    build_run(design,out)
    progress={"status":"reference_check","backend":backend,"requested_design_sha256":original_hash,
              "analyzed_design_sha256":design_hash(design),"frequencies_hz":design.manual.frequencies_hz,
              "edge_sizes_mm":list(edges),"local_edge_cap_mm":max_edge_mm,"levels":[]}
    write(out/"analysis-progress.json",progress)
    try:
        reference=(reference_provider or reference_check)(out/"reference",backend)
        previous=None;comparisons=[];frequency_comparisons=[]
        for i,edge in enumerate(edges):
            level=out/f"level-{i}"
            _,report=prepare(design,level,edge,max_edge_mm=max_edge_mm)
            raw,response=solve_job(level/"bem-job.json",level/"solution",backend)
            if previous is not None:
                comparisons.append(compare(previous,raw))
                frequency_comparisons.append(compare_by_frequency(previous,raw))
            previous=raw
            progress["status"]="mesh_ladder"
            progress["levels"].append({"target_edge_mm":edge,"mesh":report,"comparison_to_previous":comparisons[-1] if comparisons else None})
            write(out/"analysis-progress.json",progress)
        converged=(all(comparisons[-1][key]<=limit for key,limit in LIMITS.items())
                   and all(row["passed"] for row in frequency_comparisons[-1])
                   and report["wavelength_resolution_pass"])
        status="mesh_converged" if converged else "reference_validated"
        notes=["Infinite rigid baffle; ideal HF throat velocity. No LF, array, crossover or measured DH450 response.",
               f"Analyzed {min(design.manual.frequencies_hz):g}–{max(design.manual.frequencies_hz):g} Hz only.",
               "Three-level mesh check passed in this band." if converged else "Mesh convergence failed; refine before ranking designs."]
        response=response_from(raw,design,status,notes)
        (out/"response.json").write_text(response.model_dump_json(indent=2)+"\n")
        qualification={"status":status,"mesh_converged":converged,"thresholds":LIMITS,
                       "comparisons":comparisons,"per_frequency_comparisons":frequency_comparisons,"reference":reference,"frequency_band_hz":design.manual.frequencies_hz,
                       "finest_mesh":report,"notes":notes}
        write(out/"qualification.json",qualification)
        attach_result(out,"baseline",out/"response.json")
        progress["status"]=status
        write(out/"analysis-progress.json",progress)
        print(f"Analysis {status}: {out.resolve() / 'viewer.html'}",flush=True)
        return qualification
    except Exception as exc:
        progress.update(status="failed",error=str(exc))
        write(out/"analysis-progress.json",progress)
        raise
