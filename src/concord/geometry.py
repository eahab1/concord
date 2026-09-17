"""Concept surface lofts, not an ATH OS-SE implementation or joined BEM boundary."""
from __future__ import annotations

from dataclasses import dataclass, field
import math

from .config import Design

TAGS = {1: "rigid_wall", 2: "hf_source", 3: "lf_left_source", 4: "lf_right_source"}
BLOCKERS = [
    "LF slot junctions are separate lofts; no Boolean cut, sewn junction, or continuous blended lip yet.",
    "No closed exterior cabinet/baffle/wall thickness; open-mouth winding requires solver-specific review.",
    "HF transformer is a simple loft, not a path-equalized line-source manifold.",
    "LF inlets are geometric proxies, not verified driver cone/basket/chamber geometry.",
    "Preview horn uses a superformula loft, not canonical ATH OS-SE/termination equations.",
]


def blockers(design):
    if design.manual.hf_only:
        return [b for b in BLOCKERS if not b.startswith("LF")]
    return BLOCKERS


@dataclass
class Mesh:
    vertices: list[tuple[float, float, float]] = field(default_factory=list)
    triangles: list[tuple[int, int, int, int]] = field(default_factory=list)


def ring(width, height, n, p=None):
    points = []
    for i in range(n):
        t = 2*math.pi*i/n
        r = 1.0 if p is None else (abs(math.cos(8*t/4)/p.sf_a)**p.sf_n2 + abs(math.sin(8*t/4)/p.sf_b)**p.sf_n3)**(-1/p.sf_n1)
        points.append((r*math.cos(t), r*math.sin(t)))
    sx, sy = max(abs(x) for x,y in points), max(abs(y) for x,y in points)
    return [(x*width/(2*sx), y*height/(2*sy)) for x,y in points]


def loft(mesh, rings, centers, source_tag=None):
    n, base = len(rings[0]), len(mesh.vertices)
    for points, (cx,cy,cz) in zip(rings, centers):
        mesh.vertices.extend(((x+cx)/1000, (y+cy)/1000, cz/1000) for x,y in points)
    for j in range(len(rings)-1):
        for i in range(n):
            a,b = base+j*n+i, base+j*n+(i+1)%n
            c,d = b+n, a+n
            mesh.triangles.extend([(a,b,c,1), (a,c,d,1)])
    if source_tag:
        center = len(mesh.vertices)
        mesh.vertices.append(tuple(v/1000 for v in centers[0]))
        for i in range(n):
            mesh.triangles.append((center,base+(i+1)%n,base+i,source_tag))


def build(design: Design) -> Mesh:
    # Revalidation stops bypassed Pydantic construction from reaching geometry.
    d = Design.model_validate(design.model_dump())
    p,m = d.optimized,d.manual
    n,k = m.angular_segments,m.length_segments
    mesh = Mesh()
    throat = ring(d.fixed.throat_diameter_mm,d.fixed.throat_diameter_mm,n)
    spine = ring(p.hf_aperture_width_mm,p.hf_aperture_height_mm,n)
    mouth = ring(p.mouth_width_mm,p.mouth_height_mm,n,p)
    def blend(a,b,t):
        return [(x+(u-x)*t,y+(v-y)*t) for (x,y),(u,v) in zip(a,b)]
    # One connected HF surface from round throat through tall spine to main mouth.
    rings,centers = [],[]
    for j in range(k+1):
        t=j/k
        rings.append(blend(throat,spine,t*t*(3-2*t)))
        centers.append((0,0,-m.hf_transformer_depth_mm*(1-t)))
    for j in range(1,k+1):
        t=j/k
        rings.append(blend(spine,mouth,t**p.morph_rate))
        centers.append((0,0,p.horn_length_mm*t))
    loft(mesh,rings,centers,2)
    if m.hf_only:
        return mesh
    for side,tag in [(-1,3),(1,4)]:
        inlet=ring(m.lf_inlet_diameter_mm,m.lf_inlet_diameter_mm,n)
        slot=ring(p.lf_slot_width_mm,p.lf_slot_height_mm,n,p)
        end_z=p.horn_length_mm*p.lf_slot_z_fraction
        rings,centers=[],[]
        for j in range(k+1):
            t=j/k
            s=t*t*(3-2*t)
            rings.append(blend(inlet,slot,s))
            centers.append((side*(m.lf_inlet_center_x_mm+(p.lf_slot_center_x_mm-m.lf_inlet_center_x_mm)*s),0,end_z-m.lf_transition_depth_mm*(1-t)))
        loft(mesh,rings,centers,tag)
    return mesh
