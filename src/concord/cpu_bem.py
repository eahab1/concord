"""DP0 Galerkin interior BEM + Rayleigh aperture coupling, assembled by Bempp.

e^-iwt convention, G=e^ikr/(4*pi*r), normals into the channel.
Unknowns are pressure p on all faces and inward Neumann q_a at the aperture:
  (K - M/2) p - V[:,a] q_a = V q_driver
  M[a,:] p - 2 V[a,a] q_a = 0
Source q_driver=i*rho*omega*v, with v=1 m/s into the channel.
Exterior p=2*S_aperture*q_a. Symmetry is formed by explicit fourfold reflection
and restriction to one quadrant; singular quadrature uses one welded grid.
"""
import os
os.environ.setdefault("NUMBA_NUM_THREADS","4")


def solve(path,frequencies,*,speed=343.,density=1.21,angle_step=2.,distance=10.):
    import time
    import numpy as np
    import bempp_cl.api as api
    from scipy.linalg import solve as dense_solve
    from .acoustic_mesh import read_mesh,reflect_quarter,check_boundary

    v,t,tags = read_mesh(path)
    check_boundary(v,t,tags)
    n = len(t)
    if n>5000:
        raise ValueError("CPU solve exceeds 5000 quarter triangles; use a lower band or Metal")
    fv,ft,domains = reflect_quarter(v,t,tags)
    grid = api.Grid(fv.T,ft.T,domain_indices=domains)
    full = api.function_space(grid,"DP",0)
    test = api.function_space(grid,"DP",0,segments=[1,2,12])
    if test.global_dof_count!=n:
        raise ValueError("Unexpected Bempp quadrant DOF map")
    columns = full.local2global[:,0].reshape(4,n)
    rows = test.local2global[:n,0]
    def reduced(matrix):
        return sum(matrix[rows][:,column] for column in columns)
    identity = reduced(api.operators.boundary.sparse.identity(full,test,test).weak_form().to_dense())
    params = api.DefaultParameters()
    params.quadrature.regular = 4
    params.quadrature.singular = 6
    aperture = np.flatnonzero(tags==12)
    angles = np.linspace(-90,90,round(180/angle_step)+1)
    rad = np.deg2rad(angles)
    points = np.array([np.column_stack((distance*np.sin(rad),np.zeros(len(rad)),distance*np.cos(rad))),
                       np.column_stack((np.zeros(len(rad)),distance*np.sin(rad),distance*np.cos(rad)))])
    # Three-point triangle integration for distant Rayleigh field; boundary
    # coupling uses Bempp's singular/regular Galerkin quadrature above.
    face = fv[ft[np.flatnonzero(domains%20==12)]]
    area = np.linalg.norm(np.cross(face[:,1]-face[:,0],face[:,2]-face[:,0]),axis=1)/2
    bary = np.array([[2/3,1/6,1/6],[1/6,2/3,1/6],[1/6,1/6,2/3]])
    quadrature = np.einsum('ij,tjk->tik',bary,face)
    distances = np.linalg.norm(points.reshape(-1,3)[:,None,None,:]-quadrature[None,:,:,:],axis=-1)
    source_nodes = v[t[tags==2]]
    source_areas = np.linalg.norm(np.cross(source_nodes[:,1]-source_nodes[:,0],source_nodes[:,2]-source_nodes[:,0]),axis=1)/2
    pressure,loading,diagnostics = [],[],[]
    for f in frequencies:
        start=time.monotonic()
        print(f"CPU BEM: {f:g} Hz, {n} quarter triangles",flush=True)
        k = 2*np.pi*f/speed
        slp = reduced(api.operators.boundary.helmholtz.single_layer(full,test,test,k,parameters=params,
                      device_interface="numba").weak_form().to_dense())
        dlp = reduced(api.operators.boundary.helmholtz.double_layer(full,test,test,k,parameters=params,
                      device_interface="numba").weak_form().to_dense())
        system = np.block([[dlp-.5*identity,-slp[:,aperture]],
                           [identity[aperture,:],-2*slp[np.ix_(aperture,aperture)]]])
        driver = 1j*2*np.pi*f*density*(tags==2)
        rhs = np.r_[slp@driver,np.zeros(len(aperture))]
        solution = dense_solve(system,rhs)
        residual = float(np.linalg.norm(system@solution-rhs)/np.linalg.norm(rhs))
        if not np.all(np.isfinite(solution)) or residual>1e-7:
            raise ValueError("BEM linear solve failed residual/finite check")
        qa = np.tile(solution[n:],4)
        rayleigh = np.mean(np.exp(1j*k*distances)/(4*np.pi*distances),axis=-1)*area
        field = (2*rayleigh@qa).reshape(2,len(angles))
        pressure.append(field)
        loading.append(np.average(solution[:n][tags==2],weights=source_areas))
        diagnostics.append({"frequency_hz":float(f),"relative_residual":residual,
                            "seconds":time.monotonic()-start,"quarter_triangles":n})
    return {"pressure":np.array(pressure),"loading":np.array(loading),"angles":angles,
            "frequencies":np.array(frequencies),"diagnostics":diagnostics,
            "backend":"bempp-cl-numba-dp0","phase_convention":"exp(-i*omega*t)",
            "normal_velocity_m_s":1.0,"observation_distance_m":distance}
