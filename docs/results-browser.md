# Live results library

This separate standard-library Python program reads the `runs` directory. It does not import the solver, change results, or affect campaign resume fingerprints.

From the Concord repository, in a separate terminal:

```sh
python3 scripts/results_browser.py --follow-latest --open
```

Open http://127.0.0.1:8765/?follow=1 if it does not open automatically. Stop the browser server with Ctrl+C in its own terminal; the acoustic solver runs independently. Keep that terminal open while using the browser. No additional packages are needed.

Options:

- `--root /path/to/results` scans a different results tree (defaults to this repository's `runs`).
- `--port 8766` uses a different local port.
- `--follow-latest` adds `?follow=1` to the launch URL, enabling automatic selection.
- `--open` opens that URL in your default browser.

The browser refreshes every five seconds. **Follow latest completed solve** selects the newest readable, non-synthetic `response.json`, including individual mesh-level results during validation. A completed result appears within the next refresh; an unfinished frequency has no new response to show. Following is global across the scanned tree. Clicking another row disables following; checking the toggle resumes it and enables automatic refreshing. Turn auto-refresh off to pause updates.

The catalogue includes campaigns, proposals, meshes, raw response stages, convergence validation, reference checks, precision comparisons and resource tests. Search and filter by run, type or recorded status. Selecting a response shows horizontal and vertical frequency-angle heatmaps, generation scores/parameters when available, existing viewer links, raw metadata and saved files. Heatmaps show sampled data with a logarithmic frequency axis; color tiles do not imply additional solved frequencies. Scores remain separate for screening and validation and should only be compared across matching settings.

Statuses are **last recorded file contents**, not a process monitor. An interrupted run may still say running. Concept mesh counts are explicitly labeled; they are not the BEM triangle counts. Converged record counts can include related outputs and are not counts of unique designs. Reference checks and resource tests do not establish acoustic design quality.

JSON is cached by size and modification time; meshes and binary fields are not loaded during indexing. Partial JSON writes show an unreadable-metadata notice and are retried on later scans. Hidden folders, `cache`, symlinks and common dependency folders are excluded. File links are confined to the selected results root and the server binds only to localhost. Existing HTML viewers are served as authored; the results directory should contain trusted local outputs.

The browser is independently editable in `scripts/results_browser.py` and `scripts/results_browser.html`. It needs no ChatGPT session to run. Reload the page after HTML changes; restart only this browser server after Python changes.

## Compact visual view

The narrow results list leaves most space for the selected shape and H/V plots. The embedded concept preview supports drag/arrow-key rotation, wheel zoom, and 3D/Front/Side buttons. Mesh-level response records use the nearest saved ancestor concept preview, labeled with its source; this is the design preview, not the solved BEM mesh. Reports, parameters, and files remain available in collapsed sections.

Use the **Plot display** dropdown above the charts to choose **As sampled** or **Interpolated**. Interpolation is bilinear in log frequency and angle, using the saved normalized dB values. It is a display approximation, does not create acoustic evidence between samples, and never changes scores or result files. The choice persists in this browser. Single-frequency records interpolate only along angle. Automatic refresh retains the plot mode and shape orientation.
