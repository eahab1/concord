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
    p.add_argument("--backend",choices=["hornlab-metal","boundary-lab"],required=True)
    p=sub.add_parser("view")
    p.add_argument("output",type=Path)
    p=sub.add_parser("attach-result")
    p.add_argument("output",type=Path)
    p.add_argument("--candidate",required=True)
    p.add_argument("--response",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=="view":
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
            job=json.loads(args.job.read_text())
            backend=HornLabMetalBackend() if args.backend=="hornlab-metal" else BoundaryLabBackend()
            backend.solve(job)
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
    except (ValueError,OSError,RuntimeError,NotImplementedError) as exc:
        print(f"concord: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
