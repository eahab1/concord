"""Conforming edge bisection of a piecewise-planar acoustic boundary.

Shared edges are split together, including at physical-tag interfaces. New
vertices stay on the existing planar facets: this is discretization refinement,
not a new CAD approximation or evidence of geometry convergence.
"""
import numpy as np


def limit_edges(vertices, triangles, tags, maximum_m, max_rounds=12):
    if not np.isfinite(maximum_m) or maximum_m<=0:
        raise ValueError('Maximum edge length must be positive and finite')
    v=np.asarray(vertices,float).copy();t=np.asarray(triangles,int).copy();tags=np.asarray(tags,int).copy()
    for iteration in range(max_rounds+1):
        edges=np.sort(np.concatenate([t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]),axis=1)
        edges=np.unique(edges,axis=0)
        marked=edges[np.linalg.norm(v[edges[:,0]]-v[edges[:,1]],axis=1)>maximum_m*(1+1e-12)]
        if not len(marked):return v,t,tags,iteration
        if iteration==max_rounds:raise ValueError('Edge refinement failed to converge')
        mids={tuple(e):len(v)+i for i,e in enumerate(marked)}
        v=np.concatenate([v,(v[marked[:,0]]+v[marked[:,1]])/2])
        faces=[];groups=[]
        for face,tag in zip(t,tags):
            a,b,c=map(int,face)
            ab=mids.get(tuple(sorted((a,b))));bc=mids.get(tuple(sorted((b,c))));ca=mids.get(tuple(sorted((c,a))))
            count=sum(x is not None for x in (ab,bc,ca))
            if count==0:new=[(a,b,c)]
            elif count==3:new=[(a,ab,ca),(ab,b,bc),(ca,bc,c),(ab,bc,ca)]
            elif count==1:
                if ab is not None:new=[(a,ab,c),(ab,b,c)]
                elif bc is not None:new=[(b,bc,a),(bc,c,a)]
                else:new=[(c,ca,b),(ca,a,b)]
            else:
                # Rotate to put the two marked edges at AB and BC.
                if ab is None:a,b,c=b,c,a;ab,bc=bc,ca
                elif bc is None:a,b,c=c,a,b;ab,bc=ca,ab
                new=[(ab,b,bc),(a,ab,c),(ab,bc,c)]
            faces.extend(new);groups.extend([tag]*len(new))
        t=np.array(faces,int);tags=np.array(groups,int)
