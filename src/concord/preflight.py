"""Mesh-only feasibility checks. These never allocate dense solver matrices."""
from pathlib import Path
from .config import load
from .analysis import prepare,write
from .acoustic_mesh import read_mesh


def mesh_cost(report, aperture_triangles):
    # Native HornLab uses P1 pressure and DP0 aperture velocity. The Schur
    # implementation still stores dense pressure and aperture operators.
    n = report['quarter_vertices']; a = int(aperture_triangles)
    return {
        'pressure_dofs': n, 'aperture_dofs': a,
        'one_complex128_pressure_matrix_gib': 16*n*n/2**30,
        'one_complex64_pressure_matrix_gib': 8*n*n/2**30,
        'one_complex128_aperture_matrix_gib': 16*a*a/2**30,
        'one_complex128_cross_matrix_gib': 16*n*a/2**30,
        'f32_schur_storage_inventory_gib': (32*n*n+40*n*a+24*a*a)/2**30,
        'inventory_note': 'Source-based inventory: four complex64 pressure buffers, five complex64-equivalent cross buffers and three aperture buffers. Their lifetimes may overlap differently; this is not measured peak RAM and excludes GPU assembly and other workspaces. Aperture factorization stays complex128.',
        'memory_note': 'Individual array sizes only, not peak RAM. Assembly, factorization, copies and GPU buffers require additional memory. No runtime estimate or fit guarantee.'}


def preflight(config, out, maximum=20000., edges=(2.,1.5,1.25)):
    if len(edges)<3 or any(not .5<=e<=40 for e in edges) or any(a<=b for a,b in zip(edges,edges[1:])):
        raise ValueError('Use at least three decreasing edge sizes between 0.5 and 40 mm')
    d=load(config)
    # Include the exact requested maximum even if absent from input YAML.
    from .config import Design
    data=d.model_dump();data['manual']['frequencies_hz']=[maximum]
    d=Design.model_validate(data)
    out=Path(out)
    if out.exists() and any(out.iterdir()): raise ValueError('Preflight output must be empty')
    out.mkdir(parents=True,exist_ok=True)
    result={'status':'meshing','maximum_frequency_hz':maximum,'levels':[],
            'acoustic_convergence_tested':False}
    write(out/'preflight.json',result)
    for i,edge in enumerate(edges):
        folder=out/f'level-{i}'
        _,report=prepare(d,folder,edge)
        _,_,tags=read_mesh(folder/'boundary.msh')
        cost=mesh_cost(report,(tags==12).sum())
        result['levels'].append({'target_edge_mm':edge,'mesh':report,'cost':cost})
        write(out/'preflight.json',result)
        print(f"Mesh {edge:g} mm: {report['quarter_triangles']} quarter triangles; "
              f"largest edge {report['max_edge_m']*1000:.3f} mm; "
              f"resolution {'PASS' if report['wavelength_resolution_pass'] else 'FAIL'}; "
              f"one pressure matrix {cost['one_complex128_pressure_matrix_gib']:.2f} GiB",flush=True)
    result['status']='mesh_checks_complete'
    write(out/'preflight.json',result)
    return result
