# Concord line-array design workbench

An independently editable Python repository for the initial Concord line-array design. Run it locally on macOS; no ChatGPT, cloud account, or Windows runtime is required for the scaffold.

**Status: HF-only CPU BEM baseline analyzed and mesh-checked at 1, 1.25, 1.6 and 2 kHz. Geometry, viewer and analysis commands work locally. This is an ideal-source infinite-baffle approximation, not a validated full-band loudspeaker or manufacturing model.**

The architecture is two B&C 6NDL38 LF drivers per vertical module, flanking morphing LF passages, and a B&C DH450 feeding a central vertical HF spine. V0 assumes one DH450 per module. The coverage objectives are 90° horizontal (editable through 110°) and about 10° vertical. They are optimization targets, not predictions from mouth size. Superformula **m = 8** is locked in validation and geometry and excluded from the optimizer. With unequal superformula a/b and exponents, m=8 alone does not guarantee eightfold rotational symmetry.

## Current stage: HF-only approximation

`manual.hf_only: true` is the default. Only the DH450 throat, round-to-line transformer and main horn are generated, as one connected surface with rigid-wall tag 1 and HF-source tag 2. The disconnected LF lofts are omitted from geometry, exports, previews and the BEM source plan. LF optimized variables are frozen during candidate generation and hidden from the viewer's active parameter comparison.

The two 6NDL38 driver requirements and LF dimensions remain saved for later integration. Inlet packaging checks still reserve their space. Set `manual.hf_only: false` only to inspect the earlier disconnected three-source concept; it is not a completed LF junction design. Existing configs without this field now default to HF-only, so their resolved hashes change and old result files must not be reused.

The baseline and eight example proposals have been refreshed. Reload an already-open viewer to load the new interface. The example candidates retain their previous HF values, with LF variables reset to the baseline. The inspection mesh remains a preview. `analyze` constructs a separate coupled-baffle boundary; this does not imply achieved coverage.

## Run acoustic analysis

```sh
uv sync --extra bem --extra dev
uv run --extra bem concord analyze configs/hf-analysis.yaml --out runs/my-hf-analysis
uv run concord view runs/my-hf-analysis
```

The completed local result is `runs/hf-analysis-02/viewer.html`. See [analysis instructions and results](docs/analysis.md) for the boundary model, qualification limits, candidate workflow and optional Metal backend. The final refinement changed significant polar response by 0.287 dB at the sampled 1–2 kHz frequencies. Coverage targets have **not** been met; the 2 kHz result is approximately 150° horizontal × 36° vertical.

## Install on macOS

Install Python 3.11+ from [python.org](https://www.python.org/downloads/macos/) or your package manager. In Terminal, change into this repository and run:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,mesh]'
python -m pytest -q
```

See [verification record](docs/verification.md) and `requirements-tested.txt` for the exact dependency versions used to test this repository.

`.[mesh]` adds native Gmsh refinement and inspection. The base package exports tagged Gmsh MSH 2.2 ASCII without Gmsh installed. Apple Silicon is required for the optional full-3D HornLab Metal backend, which is not installed by these commands. See [integration notes](docs/integration.md) for its separate toolchain and qualification requirements. A missing system Python or `xcode-select` error means install a real Python distribution; this scaffold does not require Xcode to build geometry.

## First run

```sh
concord validate configs/baseline.yaml
concord build configs/baseline.yaml --out runs/v0
concord export-ath --out runs/concord-v2-original.ath
concord propose configs/baseline.yaml --count 8 --seed 42 --out runs/candidates
concord refine runs/v0/concept.msh --out runs/v0-refined.msh
```

Open `runs/v0/concept.msh` with the Gmsh desktop application, or `concept.obj` in a mesh viewer. `inspect.geo` is a portable Gmsh view entry point. Use a new output directory for each build: existing runs are never overwritten. The checked-in `examples/baseline-run` contains a generated baseline for immediate inspection.

Each build writes:

| File | Purpose |
| --- | --- |
| `resolved.yaml` | Complete effective configuration, including defaults |
| `concept.msh` | Metre-scale triangular mesh, rigid/source physical tags |
| `concept.obj` | Grouped inspection mesh, also in metres |
| `mesh-report.json` | Edge/degeneracy/winding checks, resolution and BEM blockers |
| `bem-job.json` | Explicit source, frequency, coordinate and observation contract |
| `manifest.json` | Configuration/mesh hashes, package version and runtime |

## Visualize proposed designs

Every `build` and `propose` output includes **`viewer.html`**. Double-click it, or run:

```sh
concord propose configs/baseline.yaml --count 8 --seed 42 --out runs/search-01 --open
concord view runs/search-01
```

The offline viewer includes rotatable 3D geometry, front/side/top views, zoom, wireframe, a baseline overlay, parameter differences and a YAML download for each candidate. The checked-in `examples/proposals/viewer.html` contains eight proposals ready to inspect. `examples/baseline-run/viewer.html` shows the single-design output.

The candidate list refreshes every three seconds while preview files are being written. Keep the whole output folder together: `viewer.html`, `viewer-data.js`, `viewer-state.json`, `previews/` and YAML files. No CDN, browser extension, network service or additional Python dependency is required. If your browser blocks local script files, serve the output folder locally with `python -m http.server --bind 127.0.0.1 --directory runs/search-01` and visit `http://127.0.0.1:8000/viewer.html`.

Proposal previews use the same geometry generator at up to 32 angular × 8 length segments to keep larger searches manageable. `build` previews use the full exported mesh. Inspect the resolution label above the geometry; preview meshes are not BEM meshes. The baseline overlay has a shared coordinate frame and scale. Inputs and acoustic targets remain unchanged by the viewer.

Scores stay empty until mesh-converged results with both -6 dB crossings are attached; unrankable real results still display their polar curves. After proposal generation finishes:

```sh
concord attach-result runs/search-01 --candidate candidate-0000 --response path/to/response.json
```

The command verifies the candidate hash, frequency grid, result shape and score eligibility, then saves a copy under `results/`. The viewer updates objective and best-so-far charts, plus horizontal/vertical off-axis response curves with a frequency selector. `--candidate baseline` also works, including in single-build folders. Result provenance is supplied by the external backend; schema validation is not independent proof of simulation accuracy. Declared synthetic results are rejected. Run `analyze` to generate qualified numerical results; the viewer itself is read-only.

Implementation: `src/concord/viewer.py` publishes the output; `src/concord/data/viewer.html` is the editable HTML/CSS/JavaScript interface. It uses Canvas 2D to project and depth-sort triangles, with no external 3D library. Intersecting concept surfaces can show approximate occlusion; use Gmsh for detailed mesh inspection.

## Change the design without ChatGPT

Copy `configs/baseline.yaml`, edit values and run `validate` followed by `build` using the new file. Set `manual.coverage.horizontal_target_deg: 110` to change the scoring target. That does not automatically redesign the horn. Change `optimized.lf_slot_width_mm`, for example, to change the slot geometry. All optimized values can also be edited manually within bounds.

The three ownership groups are explicit:

| Group | What belongs here | Behavior |
| --- | --- | --- |
| `fixed` | Driver identities, two LF drivers, architecture, 25.4 mm throat and m=8 | Literal constraints; rejected if changed |
| `manual` | Coverage, segmentation, environment, transformer/transition depth, proxy inlet geometry, array/crossover intent | User-controlled; never sampled by optimizer |
| `optimized` | Mouth dimensions, horn length, HF aperture, LF slot shape/location, morph rate, superformula a/b/n1/n2/n3 | Bounded candidate variables |

`schema/design.schema.json` supports YAML editor completion; the first line of the baseline config links it. `src/concord/config.py` is the authoritative schema and bounds. To add a variable, define it there, connect it to the relevant geometry/objective, and run `concord schema --out schema`. Unknown fields, duplicate YAML keys, nonfinite values, invalid clearances and inconsistent array lengths are rejected. Defaults permit concise configs; the resolved run always records what was used. The cross-field checks run in Python and cannot all be expressed in editor JSON Schema.

The numerical baseline is preserved separately in `src/concord/data/concord_v2.ath`, with every supplied ATH value retained, including the 353 × 353 mm mouth, Term/OS parameters, mesh settings and enclosure block. Its numeric `Morph.FixedPart = 0.3455704293` is authoritative; the original approximate “40%” comment is not used. `export-ath` copies that reference unchanged. Candidate generation cannot edit it.

## Geometry rationale and current limits

The baseline concept starts at a 380 × 250 mm mouth and 140 mm horn length. A simple round-to-line loft runs from the 25.4 mm HF throat to a 14 × 238 mm spine; a subsequent superformula loft expands to the mouth. In the optional full concept mode, two circular LF inlet proxies morph into tall flanking slots. These make the layout, variable ownership and export flow tangible.

The concept is **not an implementation of ATH OS-SE**, and does not claim to reproduce the original Concord acoustic surface. The retained `Term.*`, `OS.k`, guide distance/width, corner treatment and enclosure are reference inputs for a future canonical geometry backend. The preview uses its documented loft law, including `t ** morph_rate`; it does not claim ATH-equivalent morph semantics. LF slot endpoints are not yet cut into or sewn to the horn wall. No continuous lip, cabinet exterior, chamber physics or path-equalized HF manifold is generated. The report therefore always marks this geometry `bem_ready: false`.

Driver proxy inlet dimensions are editable assumptions, not manufacturer measurements. Basket clearance, actual radiating area, excursion/compression, driver mounting angles and acoustic loading need a separate mechanical/acoustic model. Array count, gaps, splay and LR6 crossover intent are saved metadata; array placement, mutual coupling and crossover transfer functions remain integration work.

For BEM, a wavelength/6 edge limit at 16 kHz and 343 m/s is approximately 3.57 mm. The coarse concept mesh deliberately does not meet that limit. Uniform Gmsh refinement checks interoperability; it does not fix topology, smooth facets into a canonical horn, or prove convergence. Dense BEM cost makes adaptive meshing and a measured convergence study essential before optimization.

## Optimization and external results

`propose` is reproducible bounded random search, with cross-field validation and rejection sampling. It only changes active `optimized` variables; `lf_*` variables remain frozen in HF-only mode. It does not call a solver or select an acoustic winner. Build candidates individually, integrate a qualified BEM backend, and normalize real results to `schema/response.schema.json` before scoring:

```sh
concord build runs/candidates/candidate-0000.yaml --out runs/candidate-0000
concord score runs/candidates/candidate-0000.yaml path/to/response.json
```

The result must carry the candidate configuration hash printed by `validate` or stored in its manifest, the exact requested frequencies, and horizontal/vertical dB arrays normalized to boresight. Scoring uses interpolated first -6 dB crossings on each side of boresight, coverage error, horizontal beamwidth variation and off-axis peak penalty. Missing crossings, malformed arrays, stale hashes and declared synthetic data are rejected. Lower scores are better. This initial objective still needs explicit sidelobe, frequency-response ripple, LF/HF crossover matching, loading and robustness terms before engineering selection.

`build` jobs remain blocked inspection jobs. Use `prepare-bem` followed by `solve --backend bempp-cpu` for a single mesh, or `analyze` for reference validation and mesh convergence. See [analysis instructions](docs/analysis.md). Boundary Lab remains unconnected; Metal is implemented but could not access a GPU in the agent runtime.

## Repository map and next implementation steps

`src/concord/` holds configuration, geometry, mesh, BEM, optimization and CLI modules. `tests/` covers hard constraints, preserved ATH values, mesh topology/units/tags, deterministic sampling, scoring and native Gmsh round-trip refinement. `docs/integration.md` defines the backend contract and qualification gates.

1. Implement and compare the canonical OS-SE/ATH reference backend against known Concord geometry.
2. Build the path-equalized HF transformer and continuous LF-to-waveguide junctions; add cabinet surfaces and real driver mounting geometry.
3. Validate manifold topology, intersection clearance, source normals and mesh convergence; integrate one external BEM backend.
4. Combine complex source transfer functions with an acoustic crossover, then assemble/simulate multiple modules and optimize coverage and loading.

The local source is the complete editable workbench. No proprietary generator or conversation state is required. Git can track your changes (`git status`, `git diff`); keep run folders outside version control or archive the resolved configurations and manifests alongside measured results.
# concord

Generation-by-generation runs, frequency sweeps, ranking, directivity maps and parameter history are documented in [docs/generations.md](docs/generations.md). Start with `concord campaign ... --propose-only` to inspect proposals, then resume to analyze them.

For the 32 GB M4 mesh feasibility checks and actual higher-frequency validation results, see [docs/fullband-validation.md](docs/fullband-validation.md).

The experimental single-precision Metal backend and local edge refinement are documented in [docs/lower-memory-metal.md](docs/lower-memory-metal.md).

The seven-frequency 500 Hz–20 kHz baseline check passed on the 32 GB M4. See [the measured results](docs/fullband-baseline-results.md) for convergence metrics, resource use and scope.

For faster generation searches, see [fast-search.md](docs/fast-search.md): `campaign --mode fast` screens every candidate, validates only finalists, and caches unchanged results. Screening ranks remain provisional; the default campaign mode still validates every candidate.

Browse all saved runs without interrupting the solver: `python3 scripts/results_browser.py --follow-latest --open`. The [live results library](docs/results-browser.md) refreshes every five seconds and can automatically display each newly completed solve.
