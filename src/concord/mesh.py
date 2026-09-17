"""Portable tagged MSH 2.2 export and inspection; optional native Gmsh refinement."""
from collections import Counter
import math
from pathlib import Path

from .geometry import Mesh,TAGS


def sub(a,b):
    return tuple(x-y for x,y in zip(a,b))


def norm(a):
    return math.sqrt(sum(x*x for x in a))


def audit(mesh: Mesh, max_edge_m: float) -> dict:
    edges=Counter()
    directed=Counter()
    areas=[]
    longest=0.0
    min_angle=180.0
    for a,b,c,tag in mesh.triangles:
        xyz=[mesh.vertices[i] for i in (a,b,c)]
        lengths=[norm(sub(xyz[i],xyz[(i+1)%3])) for i in range(3)]
        longest=max(longest,*lengths)
        u,v=sub(xyz[1],xyz[0]),sub(xyz[2],xyz[0])
        areas.append(norm((u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]))/2)
        for i in range(3):
            x,y,z=lengths[i],lengths[(i+1)%3],lengths[(i+2)%3]
            angle=math.degrees(math.acos(max(-1,min(1,(x*x+y*y-z*z)/(2*x*y))))) if x*y else 0
            min_angle=min(min_angle,angle)
        for u,v in ((a,b),(b,c),(c,a)):
            edges[tuple(sorted((u,v)))]+=1
            directed[(u,v)]+=1
    return {"vertices":len(mesh.vertices),"triangles":len(mesh.triangles),
            "tag_counts":dict(Counter(t[3] for t in mesh.triangles)),
            "boundary_edges":sum(v==1 for v in edges.values()),
            "nonmanifold_edges":sum(v>2 for v in edges.values()),
            "inconsistent_winding_edges":sum(v==2 and (directed[e]==2 or directed[e[::-1]]==2) for e,v in edges.items()),
            "degenerate_triangles":sum(a<1e-14 for a in areas),
            "min_angle_deg":min_angle,"max_edge_m":longest,
            "target_max_edge_m":max_edge_m,"wavelength_resolution_pass":longest<=max_edge_m,
            "bem_ready":False,"self_intersections_checked":False}


def write_msh(mesh: Mesh,path: Path):
    active_tags={t[3] for t in mesh.triangles}
    lines=["$MeshFormat","2.2 0 8","$EndMeshFormat","$PhysicalNames",str(len(active_tags))]
    lines += [f'2 {tag} "{TAGS[tag]}"' for tag in sorted(active_tags)]
    lines += ["$EndPhysicalNames","$Nodes",str(len(mesh.vertices))]
    lines += [f"{i} {x:.12g} {y:.12g} {z:.12g}" for i,(x,y,z) in enumerate(mesh.vertices,1)]
    lines += ["$EndNodes","$Elements",str(len(mesh.triangles))]
    lines += [f"{i} 2 2 {tag} {tag} {a+1} {b+1} {c+1}" for i,(a,b,c,tag) in enumerate(mesh.triangles,1)]
    path.write_text("\n".join(lines+["$EndElements",""]))


def write_obj(mesh: Mesh,path: Path):
    lines=["# Metres. Concept only; see mesh-report.json for active limitations."]
    lines += [f"v {x} {y} {z}" for x,y,z in mesh.vertices]
    for tag,name in TAGS.items():
        if not any(t[3]==tag for t in mesh.triangles):
            continue
        lines.append(f"g {name}")
        lines += [f"f {a+1} {b+1} {c+1}" for a,b,c,t in mesh.triangles if t==tag]
    path.write_text("\n".join(lines)+"\n")


def refine_gmsh(source: Path,destination: Path):
    try:
        import gmsh
    except (ImportError,OSError) as exc:
        raise RuntimeError("Install concord-line-array[mesh] and the Gmsh native library prerequisites") from exc
    gmsh.initialize()
    try:
        gmsh.open(str(source.resolve()))
        gmsh.model.mesh.refine()
        gmsh.option.setNumber("Mesh.MshFileVersion",2.2)
        gmsh.write(str(destination.resolve()))
    finally:
        gmsh.finalize()
