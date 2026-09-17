# Fast generation search

Use `campaign --mode fast` to screen every candidate on one mesh, then run the complete mesh ladder only for the best `--finalists` candidates (default 1). Existing `campaign` commands still default to full validation of every candidate.

Start a fresh campaign from the seven-frequency HF configuration:

```sh
uv run --extra bem --extra metal concord campaign configs/hf-fullband-check.yaml \
  --out runs/search-fast-01 --mode fast --generations 2 --population 4 \
  --backend hornlab-metal-f32 --max-frequency 20000 \
  --edges-mm 2.5 2 1.85 --max-edge-mm 2.8 --finalists 1
```

This samples **500, 1000, 2000, 5000, 10000, 15000 and 20000 Hz**. It does not restrict the search to 1–2 kHz. Add `--propose-only` to prepare designs without solving; repeat the same command with `--resume` and without `--propose-only` to evaluate them. Keep numerical settings unchanged when resuming. Increase `--generations` to extend a completed run. Start a new directory when changing frequencies, meshes, backend, design, finalist count, cache directory, or solver code.

For a custom sweep, add `--min-frequency 500 --frequency-points 15 --frequency-spacing log`. More frequencies take more time. Keep sparse samples during exploration; use a denser sweep and mesh checks on selected designs afterward. Do not compare rankings from different frequency grids as if they measured the same objective.

## What changes

- Screening uses the first `--edges-mm` value and the same local edge cap. It checks the reference solver and wavelength resolution, but does **not** establish mesh convergence.
- Screening scores and ranks are explicitly provisional. Full-validation scores and ranks are stored separately. Both use the existing equal-weight H/V pattern objective; lower is better.
- The best screening candidates receive the full mesh ladder on the same frequency grid. A generation needs at least one mesh-converged finalist before breeding continues. Known validation failures are excluded from breeding; remaining provisional candidates may be parents in this explicit fast mode.
- The best eligible screening candidate is carried forward unchanged. Its results, including validation when available, can be reused from the cache.
- Superformula m remains locked at 8 and LF variables remain frozen in HF-only mode.

The previous baseline needed 44.1 minutes for three meshes at seven frequencies. Its first mesh took approximately five minutes. Thus four candidates plus one fully validated finalist might take roughly an hour instead of roughly three hours if costs resemble the baseline. This is an estimate, not a benchmark of mutated candidates; the finalist currently repeats the screening mesh as part of its full ladder. This change reduces the number of solves rather than accelerating an individual factorization.

## Outputs and resume

`summary.txt` is the human-readable campaign report. `campaign.json` contains parameters, lineage, separate scores/ranks, qualification status, response paths, cache-hit flags and elapsed stage times. Each candidate keeps its geometry viewer; each completed screening/validation stage has its existing response viewer. The screening viewer correctly remains unqualified for its legacy score. Campaign pattern scores are in the summary/JSON.

The **fast campaign HTML dashboard is deferred** to the next viewer update; fast mode deliberately does not publish the older dashboard, whose labels assume every ranked result is mesh-converged.

Ctrl+C checkpoints the campaign. Resume preserves interrupted attempt folders and starts a fresh attempt for an unfinished stage. Completed stages are retained and their response hashes checked. Failed stages remain diagnostic records; start a new campaign after fixing the cause. A blocked generation reports the finalist failures in the summary.

## Cache

By default, sibling campaigns share `runs/.concord-cache`; override with `--cache-dir PATH`. Cache keys include the complete resolved design, exact frequency grid, stage, meshes, local edge cap, backend, relevant source/runtime/package identity and solver environment fingerprint. Reference checks have their own cache entries. Every payload file is hashed and verified before reuse. Corrupt entries are quarantined and recomputed. Synthetic responses and failed reference checks cannot enter the cache. A failed/interrupted computation never commits a cache entry. Unconverged completed validation evidence may be cached, but remains unqualified and cannot receive a validated score.

Cached outputs are copied into each campaign so campaigns remain inspectable independently. Raw provenance inside cached files describes the original solve. Remove the shared cache only when no campaign is using it; this removes reuse benefits, not the copied evidence in existing campaigns.

## Verification and limits

Automated tests cover unchanged-elite reuse, independent score qualifications, resume, interruption, numerical setting mismatches, corrupted cache recovery, failed reference checks, synthetic response rejection and validation failure blocking. A real Metal test at 1 and 2 kHz completed screening in 1.24 s and reused its cached output in 0.006 s; the reference cache also hit. These tiny-mesh timings verify integration and must not be extrapolated to 20 kHz. A real two-candidate Metal campaign at 1 and 2 kHz also completed: both candidates were screened, the leader passed the three-mesh convergence check, and the next generation was proposed. Resuming that completed campaign reused its checkpoints without invoking the solver. All 61 Python tests pass.

Frequency-dependent meshes, changes to the Metal factorization kernel, and adaptive frequency sampling are not implemented here. The full-band screening mesh still resolves 20 kHz. The model remains an ideal HF source in an infinite baffle. This runner is sequential, but has no automatic RSS guard; candidate mesh sizes may differ from the baseline's measured 18.92 GiB peak during validation.

## Live terminal status

Metal solves print an elapsed-time update every ten seconds while a frequency (or float64 batch) is running, followed by its completion time and the completed frequency count. This heartbeat confirms that the Python runner is still waiting for the solver; it cannot distinguish a slow native solve from a stalled native solve. The installed coupled solver does not expose a within-frequency completion percentage, so no percentage or ETA is invented. Status is terminal-only for now.

Already-running Python processes keep the old code. Let the current run finish; newly started runs use the indicator automatically. As with other source updates, the fast campaign solver fingerprint changes, so older campaign checkpoints require their original code for resume; new-code campaigns should use a new output directory.

## Improve generations first; validate later

Set `--finalists 0` in fast mode to advance generations using provisional single-mesh scores without running the fine-mesh ladder. The solver reference and wavelength-resolution checks remain enabled. An unchanged elite is cached across generations. A generation with no eligible screening results still blocks. Every screening score remains provisional; this mode never claims mesh convergence.

The next search uses `configs/hf-generation-search.yaml`, saved from candidate 0001 of `search-fast-01` (screening objective 7.73732). It retains seven samples from 500 Hz to 20 kHz and superformula m=8. The original four candidate results remain in `search-fast-01`; its incomplete validation has been stopped. A new campaign rechecks the starting design under the current code before exploring offspring. Fine-mesh validation can later be run with `concord analyze` on a selected candidate's `resolved.yaml`.

```sh
uv run --extra bem --extra metal concord campaign configs/hf-generation-search.yaml \
  --out runs/search-generations-screen-01 --mode fast --generations 2 --population 4 \
  --backend hornlab-metal-f32 --max-frequency 20000 \
  --edges-mm 2.5 2 1.85 --max-edge-mm 2.8 --finalists 0
```

Only the first edge size (2.5 mm) is used in this mode. Smaller values in the supplied ladder are reserved for validation and are not solved. This removes validation overhead, not the cost of individual screening solves. Launching this run does not require changing the results browser; it will discover the new folder automatically.
