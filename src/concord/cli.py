from __future__ import annotations

import argparse
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import sys
import webbrowser

from . import __version__
from .config import Design,load,save
from .geometry import build,blockers
from .mesh import audit,write_msh,write_obj,refine_gmsh
from .bem import Response,job_spec,HornLabMetalBackend,BoundaryLabBackend
from .optimization import candidates,score
from .viewer import initialize,record,publish,attach_result,design_hash


def digest(d):
    return design_hash(d)


def write_json(path,data):
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")


def fresh(path):
    path.mkdir(parents=True,exist_ok=True)
    if any(path.iterdir()):
        raise ValueError(f"Output directory must be empty: {path}")


def build_run(design,out):
    fresh(out)
    mesh=build(design)
    save(design,out/"resolved.yaml")
    write_msh(mesh,out/"concept.msh")
    write_obj(mesh,out/"concept.obj")
    limit=design.manual.sound_speed_m_s/(max(design.manual.frequencies_hz)*design.manual.elements_per_wavelength)
    report=audit(mesh,limit)
    report["blockers"]=blockers(design)
    report["hf_only"]=design.manual.hf_only
    write_json(out/"mesh-report.json",report)
    mesh_hash=hashlib.sha256((out/"concept.msh").read_bytes()).hexdigest()
    write_json(out/"bem-job.json",job_spec(design,digest(design),mesh_hash))
    write_json(out/"manifest.json",{"package_version":__version__,"design_sha256":digest(design),
                                     "mesh_sha256":mesh_hash,"geometry":"concept_lofts_not_ath_osse",
                                     "bem_ready":False,"python":sys.version})
    (out/"inspect.geo").write_text('Merge "concept.msh";\nMesh.SurfaceFaces = 1;\n')
    state=initialize(out,design,"resolved.yaml",0,mesh)
    state["status"]="complete"
    publish(out,state)
    print(json.dumps({"output":str(out.resolve()),"triangles":report["triangles"],"bem_ready":False}))


def main(argv=None):
    parser=argparse.ArgumentParser(description="Concord editable line-array scaffold (concept geometry)")
    sub=parser.add_subparsers(dest="command",required=True)
    for name in ("validate","build","propose","score"):
        p=sub.add_parser(name)
        p.add_argument("config",type=Path)
        if name in ("build","propose"):
            p.add_argument("--out",type=Path,required=True)
            p.add_argument("--open",action="store_true",help="Open the local design viewer")
        if name=="propose":
            p.add_argument("--count",type=int,default=8)
            p.add_argument("--seed",type=int,default=42)
        if name=="score":
            p.add_argument("response",type=Path)
    p=sub.add_parser("schema")
    p.add_argument("--out",type=Path,required=True)
    p=sub.add_parser("export-ath")
    p.add_argument("--out",type=Path,required=True)
    p=sub.add_parser("refine")
    p.add_argument("mesh",type=Path)
    p.add_argument("--out",type=Path,required=True)
    p=sub.add_parser("solve")
    p.add_argument("job",type=Path)
    p.add_argument("--backend",choices=["hornlab-metal","hornlab-metal-f32","bempp-cpu","boundary-lab"],required=True)
    p=sub.add_parser("view")
    p.add_argument("output",type=Path)
    p=sub.add_parser("attach-result")
    p.add_argument("output",type=Path)
    p.add_argument("--candidate",required=True)
    p.add_argument("--response",type=Path,required=True)
    p=sub.add_parser("prepare-bem")
    p.add_argument("config",type=Path)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--edge-mm",type=float,default=16.)
    p.add_argument("--max-edge-mm",type=float,help="Locally split edges above this cap")
    p=sub.add_parser("analyze")
    p.add_argument("config",type=Path)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--backend",choices=["bempp-cpu","hornlab-metal","hornlab-metal-f32"],default="bempp-cpu")
    p.add_argument("--max-frequency",type=float,default=2000.,help="Upper frequency in Hz (default: 2000)")
    p.add_argument("--min-frequency",type=float,help="Lower frequency in Hz")
    p.add_argument("--frequency-points",type=int,help="Sample count including both endpoints (2–1000)")
    p.add_argument("--frequency-spacing",choices=["log","linear"],default="log")
    p.add_argument("--edges-mm",type=float,nargs="+",default=[24.,16.,10.])
    p.add_argument("--max-edge-mm",type=float,help="Optional local edge cap for each analysis mesh")
    p=sub.add_parser("campaign",help="Analyze generations, rank results, and propose offspring")
    p.add_argument("config",type=Path)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--generations",type=int,default=2)
    p.add_argument("--population",type=int,default=4)
    p.add_argument("--seed",type=int,default=42)
    p.add_argument("--backend",choices=["bempp-cpu","hornlab-metal","hornlab-metal-f32"],default="bempp-cpu")
    p.add_argument("--max-frequency",type=float,default=2000.,help="Upper frequency in Hz (default: 2000)")
    p.add_argument("--min-frequency",type=float,help="Lower frequency in Hz")
    p.add_argument("--frequency-points",type=int,help="Sample count including both endpoints (2–1000)")
    p.add_argument("--frequency-spacing",choices=["log","linear"],default="log")
    p.add_argument("--edges-mm",type=float,nargs="+",default=[24.,16.,10.])
    p.add_argument("--max-edge-mm",type=float,help="Optional local edge cap for each analysis mesh")
    p.add_argument("--resume",action="store_true")
    p.add_argument("--propose-only",action="store_true")
    p.add_argument("--mode",choices=["validated","fast"],default="validated",help="Fast: screen all candidates, validate only finalists")
    p.add_argument("--finalists",type=int,default=1,help="Finalists to validate in fast mode; 0 advances generations using provisional screening only")
    p.add_argument("--cache-dir",type=Path,help="Shared result cache for fast campaigns")
    p=sub.add_parser("preflight",help="Check high-frequency meshes and matrix sizes without solving")
    p.add_argument("config",type=Path)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--max-frequency",type=float,default=20000.)
    p.add_argument("--edges-mm",type=float,nargs="+",default=[2.,1.5,1.25])
    args=parser.parse_args(argv)
    try:
        if args.command=="preflight":
            from .preflight import preflight
            result=preflight(args.config,args.out,args.max_frequency,args.edges_mm)
            if not result['levels'][-1]['mesh']['wavelength_resolution_pass']: return 2
        elif args.command=="campaign":
            if args.mode=="fast":
                from .fast_campaign import run
                extra=dict(finalists=args.finalists,cache_dir=args.cache_dir)
            else:
                from .campaign import run
                if args.cache_dir is not None or args.finalists!=1:
                    raise ValueError("--cache-dir and --finalists require --mode fast")
                extra={}
            result=run(args.config,args.out,args.generations,args.population,args.seed,args.backend,
                       args.max_frequency,args.edges_mm,args.resume,args.propose_only,
                       min_frequency=args.min_frequency,frequency_points=args.frequency_points,
                       frequency_spacing=args.frequency_spacing,max_edge_mm=args.max_edge_mm,**extra)
            report=args.out/("summary.txt" if args.mode=="fast" else "viewer.html")
            print(f"{result['status']}: {report}")
            if result['status'].startswith('blocked'): return 2
        elif args.command=="analyze":
            from .analysis import analyze
            qualification=analyze(args.config,args.out,args.backend,args.max_frequency,args.edges_mm,
                                  args.min_frequency,args.frequency_points,args.frequency_spacing,args.max_edge_mm)
            if not qualification["mesh_converged"]:
                return 2
        elif args.command=="prepare-bem":
            from .analysis import prepare
            prepare(load(args.config),args.out,args.edge_mm,args.max_edge_mm)
            print(f"Prepared BEM job: {args.out/'bem-job.json'}")
        elif args.command=="view":
            viewer=args.output/"viewer.html"
            if not viewer.is_file():
                raise ValueError("No viewer in this output; regenerate with build or propose")
            webbrowser.open(viewer.resolve().as_uri())
        elif args.command=="attach-result":
            print(json.dumps(attach_result(args.output,args.candidate,args.response),indent=2))
        elif args.command=="schema":
            args.out.mkdir(parents=True,exist_ok=True)
            write_json(args.out/"design.schema.json",Design.model_json_schema())
            write_json(args.out/"response.schema.json",Response.model_json_schema())
        elif args.command=="export-ath":
            if args.out.exists():
                raise ValueError("ATH output already exists")
            args.out.parent.mkdir(parents=True,exist_ok=True)
            args.out.write_bytes(files("concord").joinpath("data/concord_v2.ath").read_bytes())
        elif args.command=="refine":
            if args.out.exists():
                raise ValueError("Refinement output already exists")
            args.out.parent.mkdir(parents=True,exist_ok=True)
            refine_gmsh(args.mesh,args.out)
        elif args.command=="solve":
            if args.backend=="boundary-lab":
                BoundaryLabBackend().solve({})
            else:
                from .analysis import solve_job
                solve_job(args.job,args.job.parent/"solution",args.backend)
        else:
            design=load(args.config)
            if args.command=="validate":
                print(f"Valid design; m=8 locked; design_sha256={digest(design)}; concept only")
            elif args.command=="build":
                build_run(design,args.out)
                if args.open:
                    webbrowser.open((args.out/"viewer.html").resolve().as_uri())
            elif args.command=="propose":
                proposed=candidates(design,args.count,args.seed)
                fresh(args.out)
                save(design,args.out/"baseline.yaml")
                state=initialize(args.out,design,"baseline.yaml",args.count)
                if args.open:
                    webbrowser.open((args.out/"viewer.html").resolve().as_uri())
                for i,candidate in enumerate(proposed):
                    identifier=f"candidate-{i:04d}"
                    save(candidate,args.out/f"{identifier}.yaml")
                    state["candidates"].append(record(args.out,identifier,candidate,f"{identifier}.yaml"))
                    publish(args.out,state)
                state["status"]="complete"
                publish(args.out,state)
                write_json(args.out/"campaign.json",{"seed":args.seed,"count":args.count,"parent_sha256":digest(design),"status":"proposed_only_not_simulated"})
                print(f"Viewer: {(args.out/'viewer.html').resolve()}")
            elif args.command=="score":
                response=Response.model_validate_json(args.response.read_text())
                if response.design_sha256!=digest(design):
                    raise ValueError("Response design hash does not match configuration")
                print(json.dumps(score(design,response),indent=2))
        return 0
    except (ValueError,OSError,RuntimeError,NotImplementedError,ImportError) as exc:
        print(f"concord: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
