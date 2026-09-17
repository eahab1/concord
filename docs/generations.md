# Generation campaigns and directivity charts

Run from the Concord repository with `uv sync --extra bem --extra dev` installed.

```sh
uv run --extra bem concord campaign configs/hf-analysis.yaml \
  --out runs/search-01 --generations 2 --population 4 \
  --min-frequency 1000 --max-frequency 2000 \
  --frequency-points 25 --frequency-spacing log
uv run concord view runs/search-01
```

The offline dashboard includes a frequency-range and sample-count form that prepares a command for a new run. Run that command in your terminal; the offline page cannot start processes. The dashboard updates every three seconds.

Frequency points include both endpoints (25 points means 24 intervals). Logarithmic spacing is the default; `--frequency-spacing linear` uses equal Hz intervals. Without `--frequency-points`, the requested range filters the explicit frequency list in the input YAML. The exact resolved list is saved in every candidate YAML and `campaign.json`. The same controls work with `concord analyze` for a single design. Increasing the maximum frequency can require finer meshes; failed mesh convergence excludes a candidate from ranking. More sample points increase solve time. The existing real qualification covers 1–2 kHz only.

To inspect generation zero before solving, add `--propose-only`. Continue with the same command and settings, remove `--propose-only`, and add `--resume`. `--generations` is the total number of generations to analyze, not an additional count; increase it on resume to continue further. After each completed generation the next population is proposed, including after the last requested generation. Thus two analyzed generations produce a third, unevaluated proposal set.

Each candidate is analyzed sequentially with a reference check and a three-level mesh ladder. Results are ranked only if real response data pass mesh convergence and match the candidate hash and frequency list. Ranking uses `pattern_mse_v1`: the target is `max(-30, -6*(2*abs(angle)/coverage)^2)` dB; response values are clipped to −30…+3 dB. Squared error divided by 36 is averaged equally across angles, frequencies and the two planes. This measures similarity to a smooth target pattern, not measured beamwidth. It remains defined when the simulated hemisphere lacks a −6 dB crossing. The older standalone `score` command retains its beamwidth objective; do not compare its numbers with campaign scores.

The best candidate is retained, and the top half of qualified candidates supply parents for seeded Gaussian mutations. Mutation width starts at 15% of each allowed range and decays with generation to a 2.5% floor. Candidates are validated against the schema; fixed/manual fields, m=8, and inactive LF parameters remain unchanged. This is an initial evolutionary search, not a guarantee of a global optimum.

The dashboard shows ranks, H/V error contributions, parent hashes, geometry and parameter details, score history, parameter trajectories, and a parameter heatmap normalized to allowed bounds. Candidate result viewers show horizontal and vertical directivity maps: log frequency on X, angle on Y, 3 dB color bands from −30 to +3 dB, normalized to on-axis. White lines show target half-angles. Display interpolation between samples is not extra solver data. Only simulated angles and frequencies are shown; the current solver provides ±90°, not full ±180° radiation.

Campaign state is checkpointed after each candidate. A process lock prevents simultaneous writers. Completed, failed and unqualified candidates are retained on resume; interrupted solves restart in a new analysis-attempt directory, keeping old diagnostics. If none qualify, breeding stops. Fix geometry/mesh settings in a new campaign rather than silently changing a scored run. Resume rejects changed baseline, frequency grid, backend, mesh settings, population, seed or objective. No automatic stopping criterion is claimed; score stability and mesh convergence are distinct.

Implementation: `src/concord/campaign.py` contains the runner and ranking, `src/concord/frequency.py` resolves sweeps, and `src/concord/data/campaign.html` is the independent offline dashboard. All settings, geometry, results and history remain editable files; no ChatGPT dependency.
