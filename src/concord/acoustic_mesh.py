"""Gmsh quarter-domain boundary for an HF channel flush in an infinite baffle.

The same station contours as the preview are interpolated by OCC splines.
All normals face into the channel: source +Z, aperture -Z. Mouth is at z=0.
Mirror planes x=0 and y=0 are omitted, not rigid physical surfaces.
"""
from pathlib import Path


def make_mesh(design, path: Path, edge_mm: float, *, reference=False, max_edge_mm=None):
    import gmsh
    import numpy as np
    from .geometry import build

    if not design.manual.hf_only:
        raise ValueError("Analysis currently supports hf_only: true")
    if not .5 <= edge_mm <= 40:
        raise ValueError("BEM target edge must be between 0.5 and 40 mm")
    if max_edge_mm is not None and not .5 <= max_edge_mm <= 40:
        raise ValueError("Local maximum edge must be between 0.5 and 40 mm")
    if reference:
        # 80 mm piston feeding a 3 mm shallow channel, an independent reference.
        theta = np.linspace(0, np.pi/2, 17)
        rings = [np.column_stack((.04*np.cos(theta), .04*np.sin(theta), np.full(17,z)))
                 for z in (-.003, 0)]
        depth = .003
    else:
        n, k = design.manual.angular_segments, design.manual.length_segments
        full = np.array(build(design).vertices[:(2*k+1)*n]).reshape(2*k+1,n,3)
        full[:,:,2] -= design.optimized.horn_length_mm/1000
        rings = full[:,:n//4+1,:]
        depth = (design.optimized.horn_length_mm + design.manual.hf_transformer_depth_mm)/1000
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", 1)
        gmsh.model.add("concord-quarter-coupled-baffle")
        wires = []
        arc_counts = []
        for ring in rings:
            pts = [gmsh.model.occ.addPoint(float(x),float(y),float(z)) for x,y,z in ring]
            center = gmsh.model.occ.addPoint(0,0,float(ring[0,2]))
            arc = gmsh.model.occ.addSpline(pts)
            arc_counts.append((arc,max(len(ring),int(np.ceil(np.linalg.norm(np.diff(ring,axis=0),axis=1).sum()/(edge_mm/1000)))+1)))
            wires.append(gmsh.model.occ.addWire([arc,gmsh.model.occ.addLine(pts[-1],center),
                                                gmsh.model.occ.addLine(center,pts[0])]))
        gmsh.model.occ.addThruSections(wires,makeSolid=True,makeRuled=True)
        gmsh.model.occ.synchronize()
        for arc,count in arc_counts:
            gmsh.model.mesh.setTransfiniteCurve(arc,count)
        groups = {1:[], 2:[], 12:[]}
        for dim,tag in gmsh.model.getEntities(2):
            b = gmsh.model.getBoundingBox(dim,tag)
            if (abs(b[0])<1e-6 and abs(b[3])<1e-6) or (abs(b[1])<1e-6 and abs(b[4])<1e-6):
                continue
            physical = 12 if abs(b[2])<1e-6 and abs(b[5])<1e-6 else (
                2 if abs(b[2]+depth)<1e-6 and abs(b[5]+depth)<1e-6 else 1)
            groups[physical].append(tag)
        for tag,surfaces in groups.items():
            if not surfaces:
                raise ValueError(f"Missing acoustic boundary {tag}")
            gmsh.model.addPhysicalGroup(2,surfaces,tag)
            gmsh.model.setPhysicalName(2,tag,{1:"rigid_wall",2:"hf_source",12:"mouth_aperture"}[tag])
        gmsh.option.setNumber("Mesh.MeshSizeMax",edge_mm/1000)
        gmsh.option.setNumber("Mesh.MeshSizeMin",min(.001,edge_mm/4000))
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature",0)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints",0)
        gmsh.model.mesh.generate(2)
        gmsh.model.mesh.reverse()  # OCC solid outward -> interior-domain convention.
        gmsh.option.setNumber("Mesh.MshFileVersion",2.2)
        gmsh.write(str(path.resolve()))
    finally:
        gmsh.finalize()
    vertices,triangles,tags = read_mesh(path)
    refinement_rounds=0
    if max_edge_mm is not None:
        from .local_refinement import limit_edges
        import meshio
        vertices,triangles,tags,refinement_rounds=limit_edges(vertices,triangles,tags,max_edge_mm/1000)
        meshio.write(str(path),meshio.Mesh(vertices,[("triangle",triangles)],
                     cell_data={"gmsh:physical":[tags],"gmsh:geometrical":[tags]},
                     field_data={"rigid_wall":[1,2],"hf_source":[2,2],"mouth_aperture":[12,2]}),
                     file_format="gmsh22",binary=False)
    report = check_boundary(vertices,triangles,tags)
    report.update(local_edge_cap_mm=max_edge_mm,local_refinement_rounds=refinement_rounds)
    report.update(target_edge_mm=edge_mm, formulation="coupled_infinite_baffle",
                  symmetry="yz+xz", mouth_z_m=0, source_z_m=-depth,
                  geometry="OCC spline station contours; ruled longitudinal interpolation",
                  self_intersection_test="not exhaustive; monotone axial station loft")
    return report


def read_mesh(path):
    import meshio
    mesh = meshio.read(str(path))
    return mesh.points,mesh.cells_dict["triangle"],mesh.cell_data_dict["gmsh:physical"]["triangle"]


def reflect_quarter(vertices,triangles,tags):
    import numpy as np
    lookup,points,faces,domains = {},[],[],[]
    for quadrant,(sx,sy) in enumerate(((1,1),(-1,1),(1,-1),(-1,-1))):
        mapping = []
        for xyz in vertices*np.array([sx,sy,1]):
            key = tuple(np.round(xyz,10))
            if key not in lookup:
                lookup[key] = len(points)
                points.append(xyz)
            mapping.append(lookup[key])
        reflected = np.array(mapping)[triangles]
        if sx*sy<0:
            reflected = reflected[:,[0,2,1]]
        faces.extend(reflected)
        domains.extend(tags+20*quadrant)
    return np.array(points),np.array(faces),np.array(domains)


def check_boundary(vertices,triangles,tags):
    import numpy as np
    from .geometry import Mesh
    from .mesh import audit
    if set(tags)!={1,2,12}:
        raise ValueError("Expected rigid wall, HF source and mouth aperture only")
    if np.min(vertices[:,:2]) < -1e-8 or np.max(vertices[:,2])>1e-8:
        raise ValueError("Mesh must occupy x>=0,y>=0,z<=0")
    fullv,fullt,fulltags = reflect_quarter(vertices,triangles,tags)
    full = Mesh(fullv.tolist(),[(*t,int(tag)%20) for t,tag in zip(fullt,fulltags)])
    report = audit(full,float("inf"))
    for key in ("boundary_edges","nonmanifold_edges","inconsistent_winding_edges","degenerate_triangles"):
        if report[key]:
            raise ValueError(f"Invalid reflected acoustic boundary: {key}={report[key]}")
    # Ensure every triangle belongs to the single closed shell.
    adjacency = [set() for _ in fullv]
    for a,b,c in fullt:
        adjacency[a].update((b,c)); adjacency[b].update((a,c)); adjacency[c].update((a,b))
    seen,pending = set(),[int(fullt[0,0])]
    while pending:
        point = pending.pop()
        if point not in seen:
            seen.add(point); pending.extend(adjacency[point]-seen)
    if len(seen)!=len(fullv):
        raise ValueError("Disconnected boundary")
    nodes = vertices[triangles]
    normals = np.cross(nodes[:,1]-nodes[:,0],nodes[:,2]-nodes[:,0])
    if np.any(normals[tags==2,2]<=0) or np.any(normals[tags==12,2]>=0):
        raise ValueError("Source must point +Z and aperture -Z")
    if np.max(abs(nodes[tags==12,:,2]))>1e-8:
        raise ValueError("Aperture is not flush at z=0")
    volume = float(np.sum(np.einsum('ij,ij->i',fullv[fullt[:,0]],
                         np.cross(fullv[fullt[:,1]],fullv[fullt[:,2]])))/6)
    if volume>=0:
        raise ValueError("Expected negative interior-domain signed volume")
    report.pop("bem_ready")
    report["solver_boundary_ready"] = True
    report.pop("target_max_edge_m")
    report.pop("wavelength_resolution_pass")
    report.update(quarter_triangles=len(triangles),quarter_vertices=len(vertices),
                  signed_volume_m3=volume,source_area_m2=float(2*np.linalg.norm(normals[tags==2],axis=1).sum()),
                  boundary_contract_pass=True)
    return report
