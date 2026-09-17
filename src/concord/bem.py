"""Validated BEM response schema and explicit external solver entrypoints."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .config import Design, Model, Positive
from .geometry import blockers,TAGS
from pydantic import Field,model_validator
from typing import Literal


class Response(Model):
    schema_version: Literal[1] = 1
    design_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    solver: str = Field(min_length=1)
    synthetic: bool = False
    analysis_status: Literal["unqualified", "reference_validated", "mesh_converged"] = "unqualified"
    analysis_notes: list[str] = []
    frequencies_hz: list[Positive]
    angles_deg: list[float]
    horizontal_db: list[list[float]]
    vertical_db: list[list[float]]

    @model_validator(mode="after")
    def arrays(self):
        f,a=self.frequencies_hz,self.angles_deg
        if not f or f!=sorted(set(f)):
            raise ValueError("frequencies must be nonempty and strictly increasing")
        if len(a)<3 or a!=sorted(set(a)) or 0 not in a or a[0]>=0 or a[-1]<=0:
            raise ValueError("angles must be increasing, straddle and include zero")
        for matrix in (self.horizontal_db,self.vertical_db):
            if len(matrix)!=len(f) or any(len(row)!=len(a) for row in matrix):
                raise ValueError("polar arrays must have shape (frequency, angle)")
            if any(abs(row[a.index(0)])>1e-6 for row in matrix):
                raise ValueError("each polar must be normalized to 0 dB on axis")
        return self


class BEMBackend(Protocol):
    def solve(self, job: str | Path) -> Response:
        """Return on-axis normalized horizontal and vertical pressure levels."""
        ...


class HornLabMetalBackend:
    def solve(self,job):
        from .analysis import solve_job
        if not isinstance(job,(str,Path)):
            raise ValueError("Pass a prepared bem-job.json path")
        path=Path(job)
        return solve_job(path,path.parent/"solution","hornlab-metal")[1]


class BoundaryLabBackend:
    def solve(self,job):
        raise NotImplementedError("Boundary Lab project adapter is intentionally unconnected. See docs/integration.md.")


def job_spec(d: Design,design_hash: str,mesh_hash: str) -> dict:
    return {"schema_version":1,"status":"blocked_concept_geometry","design_sha256":design_hash,
            "mesh_sha256":mesh_hash,"mesh":"concept.msh","mesh_units":"m","mesh_scale":1,
            "coordinate_frame":{"x":"horizontal","y":"vertical","z":"forward"},
            "symmetry":"none_full_mesh","hf_only":d.manual.hf_only,
            "physical_groups":{k:v for k,v in TAGS.items() if not d.manual.hf_only or k in (1,2)},
            "frequencies_hz":d.manual.frequencies_hz,
            "sound_speed_m_s":d.manual.sound_speed_m_s,"density_kg_m3":d.manual.density_kg_m3,
            "source_plan":{"mode":"separate_unit_normal_velocity_solves",
                           "tags":[2] if d.manual.hf_only else [2,3,4],"velocity_m_s":1,"phase_deg":0,
                           "note":"Excite each source independently; combine complex fields with measured transfer functions and crossover later."},
            "observations":{"radius_m":10,"angles_deg":list(range(-90,91,5)),
                            "horizontal_xyz":"r*(sin(theta),0,cos(theta))",
                            "vertical_xyz":"r*(0,sin(theta),cos(theta))"},
            "coverage_targets":d.manual.coverage.model_dump(),
            "blockers":blockers(d),"array_implemented":False,"crossover_implemented":False}
