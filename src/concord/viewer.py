"""Offline, progressively published design viewer. No web service or CDN required."""
from __future__ import annotations

import hashlib
from importlib.resources import files
import json
from pathlib import Path
import re

from .bem import Response
from .config import Design, load
from .geometry import build
from .optimization import score


def design_hash(design):
    return hashlib.sha256(json.dumps(Design.model_validate(design.model_dump()).model_dump(), sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def atomic_text(path, text):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    temporary.replace(path)


def javascript_json(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def record(out, identifier, design, config_path, mesh=None):
    # Keep large searches responsive: previews resample the same geometry builder.
    # The original configuration/hash is retained; exports still use full resolution.
    if mesh is None:
        data = design.model_dump()
        data["manual"]["angular_segments"] = min(design.manual.angular_segments, 32)
        data["manual"]["length_segments"] = min(design.manual.length_segments, 8)
        mesh = build(Design.model_validate(data))
        resolution = "Inspection preview, at most 32 angular × 8 length segments"
    else:
        resolution = "Full exported concept mesh"
    mesh_data = {"vertices": [[round(v, 8) for v in xyz] for xyz in mesh.vertices],
                 "triangles": mesh.triangles}
    previews = out / "previews"
    previews.mkdir(exist_ok=True)
    sha = design_hash(design)
    atomic_text(previews / f"{identifier}.js",
                f"window.concordMesh({javascript_json(identifier)},{javascript_json(sha)},{javascript_json(mesh_data)});\n")
    return {"id": identifier, "design_sha256": sha, "config": config_path,
            "bounds_m": [[min(v[i] for v in mesh.vertices), max(v[i] for v in mesh.vertices)] for i in range(3)],
            "hf_only": design.manual.hf_only,
            "parameters": {k:v for k,v in design.optimized.model_dump().items()
                           if not (design.manual.hf_only and k.startswith("lf_"))}, "coverage": design.manual.coverage.model_dump(),
            "resolution": resolution, "triangles": len(mesh.triangles), "result": None}


def publish(out, state):
    # JSON is the persistent source for later result attachment. JS supports file://.
    atomic_text(out / "viewer-state.json", json.dumps(state, indent=2, allow_nan=False) + "\n")
    atomic_text(out / "viewer-data.js", f"window.concordUpdate({javascript_json(state)});\n")


def initialize(out, baseline, config_path, total, mesh=None):
    (out / "viewer.html").write_text(files("concord").joinpath("data/viewer.html").read_text())
    state = {"version": 1, "status": "generating", "total": total,
             "baseline": record(out, "baseline", baseline, config_path, mesh), "candidates": []}
    publish(out, state)
    return state


def attach_result(out: Path, identifier: str, response_path: Path):
    if not re.fullmatch(r"baseline|candidate-\d{4}", identifier):
        raise ValueError("Candidate must be baseline or candidate-NNNN")
    state = json.loads((out / "viewer-state.json").read_text())
    if state["status"] != "complete":
        raise ValueError("Wait for proposal generation to finish before attaching results")
    records = [state["baseline"], *state["candidates"]]
    selected = next((r for r in records if r["id"] == identifier), None)
    if selected is None:
        raise ValueError("Candidate is not part of this viewer")
    config = (out / selected["config"]).resolve()
    if not config.is_relative_to(out.resolve()):
        raise ValueError("Viewer configuration must be inside the output directory")
    design = load(config)
    response = Response.model_validate_json(response_path.read_text())
    if response.design_sha256 != design_hash(design) or response.design_sha256 != selected["design_sha256"]:
        raise ValueError("Response/configuration hash does not match the selected candidate")
    if response.synthetic:
        raise ValueError("Synthetic data cannot rank design candidates")
    if response.frequencies_hz != design.manual.frequencies_hz:
        raise ValueError("Response frequencies do not match design request")
    if response.analysis_status != "mesh_converged":
        scored = {"objective": None, "reason": "Mesh convergence has not passed; plots only."}
    else:
        try:
            scored = score(design, response)
        except ValueError as exc:
            if "crossings" not in str(exc):
                raise
            scored = {"objective": None, "reason": str(exc)}
    (out / "viewer.html").write_text(files("concord").joinpath("data/viewer.html").read_text())
    selected["result"] = {"score": scored, "response": response.model_dump()}
    results = out / "results"
    results.mkdir(exist_ok=True)
    atomic_text(results / f"{identifier}.json", response.model_dump_json(indent=2) + "\n")
    publish(out, state)
    return scored
