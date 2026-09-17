# BEM and canonical geometry integration boundary

## Verified upstream contracts

References checked 2026-09-17; third-party APIs can change. Pin a tested upstream revision when implementing an adapter.

- [Gmsh reference](https://gmsh.info/doc/texinfo/): the interchange is MSH 2.2 ASCII, linear triangles with physical tags. This repository exports all triangle groups and stores coordinates in metres.
- [HornLab Metal BEM](https://github.com/m3gnus/hornlab-metal-bem): documented inputs include tagged Gmsh triangle meshes; its default units are metres, rigid-wall convention is tag 1, and source tags must match velocity-source configuration. Full-3D native Metal requires Apple Silicon/macOS and its native build uses Swift/Xcode command-line tools.
- [HornLab waveguide mesher public API](https://github.com/m3gnus/hornlab-waveguide-mesher/blob/main/docs/public-api.md) and [configuration schema](https://github.com/m3gnus/hornlab-waveguide-mesher/blob/main/docs/config-schema.md): consult supported geometry/import fields before passing the archived ATH baseline. Do not silently drop unsupported fields or equate ATH import with support for this custom slot assembly.

“Compatible output” here means the documented mesh container, units and tag conventions. Native Gmsh reading/refinement is tested. HornLab ingestion/solving and Boundary Lab project import are not yet tested or implemented. Do not treat the custom `bem-job.json` as either product's own project format.

## HF-only stage

The default `manual.hf_only: true` exports only tags 1 and 2 and requests only the DH450 source. LF tags 3 and 4 below describe the deferred full concept and are absent from HF-only meshes. Saved LF driver/slot settings are future requirements. The model remains blocked for solving until the HF manifold and boundary qualification are completed.

## Coordinate and tag conventions

Right-handed local frame: x horizontal, y vertical, +z forward. Concept HF spine is at z=0, mouth at z=horn length and HF inlet behind z=0. Geometry inputs are mm, output is m. Full mesh, no mirror reduction; do not set quarter/half symmetry flags.

| Physical tag | Name | Intended role |
| --- | --- | --- |
| 1 | rigid_wall | Sound-hard boundary, zero normal velocity |
| 2 | hf_source | DH450 throat excitation |
| 3 | lf_left_source | Left 6NDL38 proxy inlet |
| 4 | lf_right_source | Right 6NDL38 proxy inlet |

The loft triangles face outward from their duct volume; the inlet caps face backward. These are visualization conventions only. A future joined exterior/body boundary needs the solver's domain-specific winding convention. Do not globally flip normals without checking rigid surfaces and each source. The central HF axis is +z even though the simple inlet caps point -z; configure the actual solver observation frame explicitly when appropriate. An adapter must not infer frame orientation from these provisional source normals.

There is no physical mouth cap/tag in the current open concept. A finite exterior cabinet and a coupled infinite-baffle formulation need different boundary constructions. Choose and test one formulation before creating a mouth cap or naming any group `mouth_aperture`.

## Adapter interface

Implement `BEMBackend.solve(job) -> Response` in `src/concord/bem.py`. The existing HornLab/Boundary Lab classes deliberately raise `NotImplementedError`. The adapter must:

1. Resolve mesh paths relative to the job file, verify configuration and mesh hashes, and reject concept-stage jobs.
2. Load a qualified, joined boundary; verify units, physical groups, source areas, normals, intersections and supported open/closed boundary conditions.
3. Set every acoustic parameter explicitly from the job. Do not rely on upstream default frequencies, source tag, symmetry or observation frame.
4. Solve each radiator separately at unit normal velocity, retaining complex pressure and loading. The job describes the intended plan, not native HornLab keyword names.
5. Store raw complex fields with actual source conventions, source areas, solver version/revision, convergence settings and mesh hash. Combine with driver transfer functions and crossover phase before deriving full-module polar magnitude. Unit normal velocity is not electrical sensitivity or equal volume velocity.
6. Export a `Response` for the same resolved design hash. Use degrees, requested frequencies, and `20*log10(abs(p(theta))/abs(p(0)))`, rejecting a zero on-axis reference. `horizontal_db` and `vertical_db` both have shape `[frequency][angle]`. Include angle 0 and sufficient range to capture both -6 dB crossings; refine the initial 5° grid for a ~10° vertical beam.

The typed response is intentionally a compact scoring interchange, not a replacement for a complete results archive. `synthetic` must be false for real results. Tests use analytic fixtures internally; no fixture is presented as a Concord simulation.

For Boundary Lab, initially import a qualified mesh manually and map the physical groups and coordinate frame. Implement an automated project exporter only against a verified schema/version. For HornLab, wrap its documented public API in the adapter once qualified fixtures pass; no speculative API calls are shipped here.

## Qualification before enabling solves

- Compare a known piston or canonical waveguide against a reference solution.
- Confirm physically correct normal velocities, units, source areas and radiation axis.
- Close or deliberately declare every boundary; sew junctions and test intersections.
- Run at least three mesh resolutions and quantify complex-pressure/directivity/loading change.
- Qualify one source, all three sources with phase, and finally array coupling separately.
- Keep the configuration hash and solver/mesh provenance attached to every candidate result.

The current edge audit cannot detect self-intersections and does not establish physical solvability. A successful Gmsh import proves file compatibility only. The permanent m=8 constraint should remain in every future backend, import adapter and optimizer path.
