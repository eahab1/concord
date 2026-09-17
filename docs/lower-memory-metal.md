# Lower-memory Metal validation

`hornlab-metal-f32` is an explicit experimental backend. It uses single-precision pressure factorization; upstream retains double precision for the aperture Schur elimination. Frequencies are submitted individually to avoid simultaneous frequency factorizations. `hornlab-metal` remains the existing double-precision pressure path. Backend identity is archived and campaign resume rejects a backend change.

The installed HornLab revision's GMRES path does **not** apply to coupled infinite-baffle aperture solves. Requesting GMRES there would retain direct factorization. It is therefore not exposed as a Concord backend.

## Accuracy evidence

Real float32 solves passed the independent reference check and matched the float64 results on identical meshes at 500 Hz, 2 kHz, 5 kHz and 10 kHz. Maximum significant polar difference was 0.000124 dB. The additional 2.5 mm mesh at 10 kHz differed by 0.0000944 dB. Results and metrics are in `runs/metal-f32-validation-01`. These comparisons validate precision at those cases, not every candidate or high-frequency resonance.

## Local edge refinement

`prepare-bem` now accepts `--max-edge-mm`. Shared long edges are bisected conformingly; physical tags and triangle orientation are preserved. New vertices lie on existing planar facets, so the procedure improves discretization without improving the original CAD approximation. Geometry convergence remains a separate question.

For the baseline 2 mm mesh, a 2.8 mm maximum edge cap adds only 48 triangles: 29,326 quarter triangles and 14,901 pressure vertices, with maximum edge 2.7995 mm. This passes the current 20 kHz λ/6 check and is much smaller than uniform remeshing at 1.5 mm (51,653 triangles). It does not by itself prove acoustic convergence.

The preparation interface is:

```sh
uv run --extra bem concord prepare-bem CONFIG.yaml \
  --out runs/LOCAL-MESH --edge-mm 2 --max-edge-mm 2.8
```

The lower-memory solve interface is:

```sh
uv run --extra bem --extra metal concord solve \
  runs/LOCAL-MESH/bem-job.json --backend hornlab-metal-f32
```

These are interfaces, not approval to run the entire high-frequency campaign. A prepared job uses **all frequencies in its configuration**; use a single-frequency configuration for an initial resource test. Changing the CLI backend alone does not add local refinement to campaign mesh ladders. The campaign integration is deferred until this mesh strategy is acoustically validated.

## Resource checks

`preflight` reports individual pressure/aperture/cross-matrix sizes and a source-based Schur storage inventory. The inventory is not measured peak RAM; buffer lifetimes, helper concurrency and GPU allocations matter. A guarded single-frequency 20 kHz validation uses the locally capped baseline in `runs/metal-20k-local-01`, with a 22 GiB process-tree RSS limit and a ten-minute limit. See `resource-check.json` for the actual outcome. The monitor sums sampled process RSS, which can overcount shared pages and miss short peaks. It is a resource bound, not an acoustic test.

The first guarded 20 kHz solve completed successfully in 105.3 seconds, with sampled process-tree RSS peaking at 13.89 GiB. It used the float32 pressure backend with the 2 mm base mesh and 2.8 mm local edge cap. LAPACK reported success. This supersedes the earlier conclusion based on uniformly refined meshes: **a 20 kHz solve can fit in 32 GB with this mesh strategy**. Mesh convergence remains a separate check.

The reusable guard is checked into the repository:

```sh
uv run --extra bem --extra metal python scripts/guarded_metal_solve.py \
  runs/NEW-PREPARED-JOB --rss-limit-gib 22 --timeout-seconds 600
```

It saves a log and a resource report, terminates the entire solver process group if a limit is exceeded, and preserves diagnostic files. It refuses to overwrite an existing guarded attempt. Default backend is `hornlab-metal-f32`; `--backend hornlab-metal` selects the double-precision comparison path. It does not create the prepared job or establish acoustic convergence.

## Three-level 20 kHz result

All three locally capped meshes completed within the 22 GiB guard. Base target sizes were 2.5, 2.0 and 1.85 mm, each capped locally at 2.8 mm. The first comparison passed with 0.2043 dB significant polar change; the final comparison passed with 0.1057 dB, 0.2208% complex-field change, 0.00688 dB on-axis change and 0.0132% loading change. The finest solve took 176.4 seconds and peaked at 14.65 GiB sampled process-tree RSS. These measurements are for this baseline and a single frequency, not a bound for every optimized geometry.

The local cap is available in `analyze` and `campaign` as `--max-edge-mm` and is part of the campaign resume contract. A sparse full-band **baseline** check can now use:

```sh
uv run --extra bem --extra metal concord analyze configs/hf-fullband-check.yaml \
  --backend hornlab-metal-f32 --out runs/metal-fullband-sparse-01 \
  --max-frequency 20000 --edges-mm 2.5 2 1.85 --max-edge-mm 2.8
```

This requests seven actual frequencies. The run has now completed and passed at all seven samples; see [fullband-baseline-results.md](fullband-baseline-results.md). These discrete samples do not establish convergence at every intervening frequency. This baseline check should precede the full 81-frequency optimization campaign. The normal `analyze` and `campaign` commands do not impose the external guard's RSS limit; use the guarded prepared-job workflow if a hard sampled resource bound is needed. Do not reuse the old full-band campaign folder with changed backend or mesh settings.


The 20 kHz float32/float64 comparison also passed on the coarser locally capped mesh: maximum significant polar difference 0.0000914 dB, complex-field difference 0.000246%. The resulting **single-frequency** qualified viewer and evidence summary are in `runs/metal-20k-qualified-01`. This result does not qualify every frequency in the band or any mutated candidate. All 54 Python tests and the campaign viewer execution test pass.
