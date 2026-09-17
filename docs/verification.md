# Verification record

## HF BEM integration

34 Python tests passed after adding boundary-contract, source-area, hash validation, response normalization and unrankable-result coverage. A real CPU reference solve and three-level baseline ladder completed separately; see [analysis results](analysis.md). The native Metal helper compiled, but its runtime smoke check reported no accessible Metal device. No Metal solve is claimed. The viewer unit harness also passed using the real four-frequency analysis output; dependency consistency and the uv lock check passed.

## HF-only approximation

30 Python tests and the JavaScript viewer smoke test passed. The baseline now contains 3,136 triangles, only wall/HF tags, and one connected surface. Tests verify frozen LF candidate values, HF-only source mapping, and explicit opt-in to the earlier full concept. The baseline and eight proposal viewers were regenerated. No acoustic solve was run; the earlier scaffold counts below are historical.

## Design explorer addition

2026-09-17: **28 Python tests passed**, including the native Gmsh test. The added tests cover progressive preview publication, original configuration hashes, full-resolution build previews, result persistence, and rejection of mismatched or synthetic responses.

The offline JavaScript unit harness passed geometry drawing, candidate selection, parameter tables, baseline overlay, fixed views, keyboard rotation, zoom, refresh preserving selection, and result-chart rendering. It validates canvas coordinates while using an in-memory test response; no synthetic results are saved in the example output. Reproduce with Node.js:

```sh
node tests/viewer-smoke.cjs examples/proposals
```

A distribution wheel was built successfully and checked for the HTML template. The examples include a full baseline mesh viewer and eight lower-resolution proposal previews. They contain no acoustic results.

Browser visual inspection was not completed: the automated browser blocked direct local file URLs, and the local sandbox did not permit binding a preview server. The JavaScript check is a DOM/canvas unit harness, not a real browser screenshot or browser compatibility test.

## Original scaffold verification

2026-09-17, local macOS arm64, CPython 3.12, Gmsh 4.15.2.

- Editable package installation succeeded.
- `python -m pytest -q`: **25 passed**. Native Gmsh integration test ran (not skipped).
- Baseline configuration validation, JSON Schema generation and concept build succeeded.
- Eight feasible candidate configurations generated with seed 42.
- Native Gmsh read the exported baseline mesh, refined all triangles fourfold, and retained physical tags 1–4 and the HF source name.
- Tests verify every user-supplied ATH baseline parameter, hard driver/m constraints, rejection of invalid config, mesh units and source groups, reproducibility, stale-result rejection and known -6 dB crossing behavior.

Baseline: 6,336 triangles. Configuration SHA-256:
`57b3065db74c67e2ab00801a8a8974090e6c3583eb64c719ed5e650de128f594`.

No HornLab or Boundary Lab simulation was run. Acoustic coverage, SPL, impedance, mechanical fit, continuous LF junctions, array coupling and HF phase equalization are not verified by this record. See the generated mesh report for topology and resolution limitations.

The system `python3` launcher on the build machine lacked developer tools, so verification used a separate bundled CPython runtime and isolated virtual environment. Users can reproduce the workflow with a regular Python 3.11+ installation following the README.

To reproduce the tested dependency set in a fresh environment:

```sh
python -m pip install -r requirements-tested.txt
python -m pip install --no-build-isolation -e .
python -m pytest -q
```
