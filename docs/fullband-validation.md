# High-frequency validation on the 32 GB M4

Update: the uniform-mesh memory limitation below has a promising alternative. See [lower-memory-metal.md](lower-memory-metal.md) for single-precision and local-refinement validation; a 20 kHz solve has now completed within the resource limit.

Metal passed the independent reference and three-level baseline check at 1, 1.25, 1.6 and 2 kHz (`runs/metal-validation-01`). This does not qualify the full 500 Hz–20 kHz band.

On the identical baseline geometry and identical finest mesh, CPU and Metal differ by 1.98% in complex field norm, 0.089 dB on axis, and up to 0.993 dB in significant normalized polar response. The largest polar difference is at 2 kHz, vertical 30°, where CPU predicts −20.14 dB and Metal −19.14 dB. At 1, 1.25 and 1.6 kHz, maximum significant polar differences are 0.033, 0.075 and 0.136 dB. The CPU DP0 and Metal P1 formulations differ; localization is evidence, not proof of the cause. Cross-backend agreement at 2 kHz remains imperfect.

## Mesh feasibility before solving

Meshing now permits target sizes down to 0.5 mm and scales the minimum-size setting below the old 1 mm floor. Requested Gmsh size is not a guaranteed maximum triangle edge. Inspect the actual edge report.

```sh
uv run --extra bem concord preflight configs/hf-fullband-check.yaml \
  --out runs/fullband-preflight-02 --max-frequency 20000 \
  --edges-mm 2 1.5 1.25
```

This generates meshes only; it does not allocate BEM matrices. Already generated results are in `runs/fullband-preflight-01/preflight.json`.

| Requested size | Quarter triangles | Largest edge | 20 kHz λ/6 check | One pressure matrix |
|---|---:|---:|---|---:|
| 2 mm | 29,278 | 3.622 mm | Fail | 3.30 GiB |
| 1.5 mm | 51,653 | 2.683 mm | Pass | 10.18 GiB |
| 1.25 mm | 74,166 | 2.165 mm | Pass | 20.91 GiB |

The limit is 2.858 mm at 343 m/s and 20 kHz. A passing edge check is necessary under our current policy, but does not prove acoustic convergence or geometric fidelity. These are individual complex128 pressure matrix sizes, **not peak RAM**. Aperture coupling, factorization, operator copies, GPU buffers and the OS need additional memory. The finest dense solve is not a suitable unattended run on 32 GB.

## Bounded acoustic validation

`configs/hf-10k-check.yaml` requests 500 Hz, 2 kHz, 5 kHz and 10 kHz. It uses the same baseline geometry and ideal source. A three-level test uses 6, 4 and 3 mm targets:

```sh
uv run --extra bem --extra metal concord analyze configs/hf-10k-check.yaml \
  --backend hornlab-metal --out runs/metal-10k-validation-02 \
  --max-frequency 10000 --edges-mm 6 4 3
```

The first such run is stored in `runs/metal-10k-validation-01`. Check qualification before ranking. New analyses include per-frequency comparisons in `qualification.json` so a low-frequency success cannot be mistaken for validation at 10 kHz.

`configs/hf-fullband-check.yaml` defines the eventual sparse seven-frequency sweep (500, 1000, 2000, 5000, 10000, 15000 and 20000 Hz), but should not be launched with the coarse default meshes or treated as approved for this machine. A practical 20 kHz campaign still needs a lower-memory solver strategy or more memory, plus demonstrated convergence. Increasing the number of sampled frequencies does not improve mesh resolution. Current checks also do not establish angular-sampling or geometry-station convergence at 20 kHz.

Do not resume the existing full-band proposal campaign with different backend or mesh settings. Create a fresh campaign after choosing and validating them.

## Completed four-frequency Metal check

The actual 6/4/3 mm run completed and passed its reference check. It was correctly left `reference_validated`, not `mesh_converged`. For the last two meshes:

| Frequency | Maximum significant polar change | Result |
|---|---:|---|
| 500 Hz | 0.00082 dB | Pass |
| 2 kHz | 0.458 dB | Pass |
| 5 kHz | 0.180 dB | Pass |
| 10 kHz | 0.972 dB | Fail |

All other per-frequency metrics passed, including 1.46% complex-field change at 10 kHz. A near-one-dB polar discrepancy still exceeds the 0.5 dB criterion; thresholds have not been relaxed. These are four sampled frequencies, not a continuous-band guarantee. The result viewer contains real fields and remains unranked.

## Additional 10 kHz refinement passed

A real Metal solve at 10 kHz with a 2.5 mm target is archived in `runs/metal-10k-refinement-01`. It has 19,494 quarter triangles, 9,938 pressure vertices and a maximum edge of 4.472 mm (below the 5.717 mm 10 kHz limit). Compared with the 3 mm level:

- Significant polar change: 0.37483 dB (limit 0.5 dB).
- Complex field change: 0.97747% (limit 5%).
- On-axis change: 0.01295 dB (limit 0.5 dB).
- Loading change: 0.21610% (limit 10%).

All four metrics pass. The earlier four-frequency run is preserved as failed for its original 6/4/3 mm ladder; the additional single-frequency evidence is separate in `comparison.json`. The four-frequency result was not retroactively relabeled, and the finer level was tested only at 10 kHz. This is useful convergence evidence at the sampled frequency, not approval of 500 Hz–20 kHz optimization. The next full-band work should validate a lower-memory solve path (including its accuracy), or use sufficient additional RAM. Do not simply switch precision or relax resolution thresholds to make the existing campaign run.

Verification: 47 Python tests pass, including sub-2 mm meshing, matrix-size estimates and per-frequency failure reporting. Actual Metal reference and frequency solves were executed on this Mac outside the agent sandbox. No 20 kHz BEM solve was attempted.
