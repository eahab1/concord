# Concord seven-frequency baseline validation

Result: **mesh_converged**. This is numerical mesh-convergence evidence for the baseline at seven sampled frequencies, not proof that the design meets its coverage targets or a continuous-band qualification.

Elapsed: 44.1 minutes. Peak sampled process-tree RSS: 18.92 GiB. The 22 GiB guard was not triggered. RSS sampling can miss short peaks or count shared pages more than once.

Backend: `hornlab-metal-f32`; frequencies solved sequentially. Three base mesh sizes: 2.5, 2.0, 1.85 mm, each with a local 2.8 mm maximum-edge cap. The independent reference check passed.

| Frequency | Polar change (dB) | Complex-field change | On-axis change (dB) | Loading change | Pass |
|---:|---:|---:|---:|---:|:---:|
| 500 Hz | 0.00079 | 0.0342% | 0.00214 | 0.0133% | Yes |
| 1000 Hz | 0.00191 | 0.0208% | 0.00203 | 0.0252% | Yes |
| 2000 Hz | 0.07497 | 0.0659% | 0.00142 | 0.0537% | Yes |
| 5000 Hz | 0.02510 | 0.1400% | 0.00555 | 0.0562% | Yes |
| 10000 Hz | 0.17252 | 0.3121% | 0.00172 | 0.1203% | Yes |
| 15000 Hz | 0.15311 | 0.4746% | 0.04441 | 0.0426% | Yes |
| 20000 Hz | 0.10572 | 0.2208% | 0.00688 | 0.0132% | Yes |

Changes compare the two finest meshes. Limits are 0.5 dB polar, 5% complex field, 0.5 dB on axis and 10% loading. The finest mesh also passes the wavelength-resolution check at 20 kHz.

The model uses an ideal HF throat source in an infinite rigid baffle. LF drivers, measured DH450 behavior, crossover and array interactions are not simulated. Superformula m remains locked at 8. Local refinement preserves the existing faceted geometry; this check does not establish CAD/geometry or angular-sampling convergence.

The viewer may say “Not ranked” because the standalone beamwidth score requires both −6 dB crossings, which are absent at some sampled frequencies within ±90°. That does not mean mesh convergence failed. The campaign runner uses its separately documented pattern objective.

The 81-point optimization campaign has not been started. These seven-frequency baseline results are the completed scope of this run.

Reproduce in a new output directory:

```sh
uv run --extra bem --extra metal concord analyze configs/hf-fullband-check.yaml \
  --backend hornlab-metal-f32 --out runs/metal-fullband-sparse-02 \
  --max-frequency 20000 --edges-mm 2.5 2 1.85 --max-edge-mm 2.8
```

The normal analysis command has no external RSS guard; this recorded run used a separate monitor. See the repository’s guarded prepared-job script for bounded individual solves.
