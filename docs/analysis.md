# Running HF acoustic analysis

The baseline has now been solved with a real three-dimensional CPU BEM calculation. This is an **ideal-source, infinite-rigid-baffle approximation at four frequencies from 1 to 2 kHz**, not a full-band DH450 or array prediction.

## Run the qualified workflow

From the Concord repository, install the analysis extra into the environment:

```sh
uv sync --extra bem --extra dev
uv run --extra bem concord analyze configs/hf-analysis.yaml --out runs/my-hf-analysis
uv run concord view runs/my-hf-analysis
```

With pip instead of uv:

```sh
python -m pip install -e '.[bem,dev]'
concord analyze configs/hf-analysis.yaml --out runs/my-hf-analysis
```

Use a new output directory for every run. `analyze` validates an independent reference, generates and solves three meshes, checks convergence, archives complex pressure and source loading, and attaches the finest result to the output viewer. The default CPU backend uses Bempp-cl's Numba assembly and SciPy's dense solve. It does not need a GPU, OpenCL or Windows.

The completed run on this machine is `runs/hf-analysis-02/viewer.html`. The earlier `hf-analysis-01` run is retained as a failed convergence diagnostic, not a usable ranking result. Run folders are ignored by Git; archive them separately if you need to move the results.

The default `--max-frequency 2000` selects only requested configuration frequencies at or below 2 kHz and saves that resolved configuration. Its hash intentionally differs from a 13-frequency full-band configuration. Raising this limit requires a finer mesh and another convergence check; a low-band pass is not evidence of high-frequency accuracy. CPU jobs above 5,000 quarter triangles are rejected to bound dense memory use.

For a new candidate campaign in the same band:

```sh
uv run concord propose configs/hf-analysis.yaml --count 8 --seed 42 --out runs/hf-search --open
uv run --extra bem concord analyze runs/hf-search/candidate-0000.yaml --out runs/candidate-0000-analysis
uv run concord attach-result runs/hf-search --candidate candidate-0000 --response runs/candidate-0000-analysis/response.json
```

The existing full-band candidates can be analyzed in separate output folders, but their 1–2 kHz responses cannot be attached to a campaign that still requests 1–16 kHz. The viewer checks the configuration hash and exact frequency grid. Do not bypass those checks by editing hashes.

## What is modeled

- The DH450 is represented by a uniform 1 m/s normal-velocity source on the 25.4 mm throat. No electrical voltage sensitivity, driver transfer function, diaphragm breakup, distortion or thermal limits are modeled.
- The round-to-line transformer and horn use the current Concord contour stations. Gmsh interpolates their cross-sections and joins adjacent stations with ruled surfaces. This remains an approximate transformer, not an equal-path manifold or an ATH OS-SE reproduction.
- The mouth is flush in an infinite, rigid planar baffle. No finite cabinet-edge diffraction, LF junction, crossover or multi-module coupling is included.
- The mouth is shifted to z=0. Wall/source/aperture tags are 1/2/12. Source normals point +Z; aperture normals point -Z, into the channel. Two exact reflection symmetries reduce the domain to x>=0, y>=0. The mouth aperture is a coupling interface, not a rigid cap.
- The CPU backend uses discontinuous constant (DP0) Galerkin elements, regular quadrature order 4 and singular order 6. It assembles the full reflected source boundary against one quadrant of test functions on a single welded grid, then sums symmetric unknowns. It solves the interior pressure and aperture velocity together and evaluates the exterior Rayleigh field at 10 m, every 2° from -90° to +90°, in the horizontal and vertical planes.

The implementation equations and phase convention are documented in `src/concord/cpu_bem.py`. For the e^-iωt convention, G=e^ikr/(4πr), and inward normals, the block equations are `(K-M/2)p - V_a q_a = V q_driver` and `M_a p - 2 V_aa q_a = 0`. The exterior field is `2 S_a q_a`. These are the interior BIE with an infinite-baffle Rayleigh coupling, not a prescribed aperture directivity approximation: the aperture distribution is solved.

## Qualification and first results

The independent reference is an 80 mm baffled piston approximated by a 3 mm-deep channel, tested at 800 and 2,000 Hz against analytic piston directivity and the exact on-axis Rayleigh pressure. The final reference errors were at most **0.212 dB** in normalized polar response, **8.65%** in on-axis magnitude, and **4.85°** in phase. These pass the predeclared 0.3 dB / 20% / 15° reference limits. The finite stub and its discretization explain why this is a bounded reference comparison rather than exact equality.

The baseline mesh ladder used 24, 16 and 10 mm target sizes and 2,036, 2,100 and 2,513 quarter-domain triangles. The throat contour is constrained to preserve its source area; the unconstrained first mesh ladder distorted this small boundary and failed, so its results were not promoted. The final two meshes changed the significant polar response by **0.287 dB**, complex field by **0.428%**, on-axis magnitude by **0.0292 dB**, and source loading by **0.427%**. The finest maximum edge is 19.2 mm, below wavelength/6 at 2 kHz.

Convergence is checked at the four sampled frequencies. Thresholds are 0.5 dB significant-polar change (the union of directions above -25 dB in either mesh), 5% complex-field change, 0.5 dB on-axis change, and 10% loading change. This checks mesh refinement on the fixed contour-station geometry; it does not establish convergence of the underlying shape approximation, angular sampling near sharp nulls, or a continuous frequency sweep.

| Frequency | Horizontal -6 dB width | Vertical -6 dB width |
| --- | --- | --- |
| 1,000 Hz | No crossing within ±90° | 134.1° |
| 1,250 Hz | No crossing within ±90° | 96.4° |
| 1,600 Hz | No crossing within ±90° | 73.6° |
| 2,000 Hz | 150.1° | 36.1° |

The present geometry has not achieved 90° × 10°. Missing -6 dB crossings are not assigned an invented width or score. The viewer displays the real curves and **Not ranked**. Mesh convergence means numerical stability under this model, not that the geometry meets the design objective.

## Artifacts and lower-level commands

Each analysis output contains `qualification.json`, `analysis-progress.json`, `response.json`, `viewer.html` and a resolved YAML. Each `level-N` contains a tagged `boundary.msh`, `mesh-report.json`, `bem-job.json` and `solution/fields.npz`. The NPZ stores complex pressure in Pa per 1 m/s throat velocity and average source loading in Pa/(m/s). Provenance records software versions, mesh/configuration hashes, source convention, field radius and solver diagnostics. Reference outputs are separate from baseline results.

For debugging a single mesh, without claiming convergence:

```sh
uv run --extra bem concord prepare-bem configs/hf-analysis.yaml --edge-mm 10 --out runs/hf-single
uv run --extra bem concord solve runs/hf-single/bem-job.json --backend bempp-cpu
```

This saves an unqualified `solution/response.json`. You can inspect it, but the viewer will not rank it. The old `build` command still emits an inspection mesh and a blocked concept job: use `prepare-bem` or `analyze` to construct the acoustic boundary.

## Optional Metal backend

```sh
uv sync --extra bem --extra metal --extra dev
uv run --extra bem --extra metal concord analyze configs/hf-analysis.yaml --backend hornlab-metal --out runs/hf-metal
```

The integration targets HornLab revision `2c2c712c7bafc2de7ab08a571d9f4211cf9624b5`. Swift command-line tools and Apple Silicon GPU access are required. The native helper compiled successfully here, but the agent runtime reported **Metal device unavailable**. Therefore the Metal adapter is connected but **not solve-validated here**; the completed baseline used `bempp-cpu`. No silent backend substitution occurs. A direct Terminal run with Metal access must pass its own reference and mesh ladder before its results are accepted. HornLab's P1 pressure / DP0 aperture formulation differs from the CPU DP0 formulation; do not mix refinement levels from different backends.

Boundary Lab's separate project adapter remains unimplemented. The tagged meshes are interoperable data, not native Boundary Lab projects.

## Source contracts

- [Bempp operator assembly](https://bempp.com/handbook/core/assembling_operators.html): documented Numba CPU assembly.
- [Bempp-cl source](https://github.com/bempp/bempp-cl): tested 0.4.2 API and DP0 spaces.
- [HornLab Metal BEM](https://github.com/m3gnus/hornlab-metal-bem/tree/2c2c712c7bafc2de7ab08a571d9f4211cf9624b5): coupled aperture convention and optional Metal API.
- [Gmsh documentation](https://gmsh.info/doc/texinfo/): OCC lofting, surface meshing and physical groups.
