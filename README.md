# LA Crater Analyzer

Python GUI for reviewing MP4 scans of evenly spaced laser-ablation craters in water ice.

The application is designed for semi-manual crater review where video contrast, optical doubling, missing craters, or variable illumination make fully automatic analysis unreliable.

## Features

- Import MP4 crater-scan videos.
- Navigate by slider, exact frame number, and +/-1, +/-10, +/-100 frame steps.
- Adjust brightness, contrast, gamma, CLAHE, and sharpening for difficult frames.
- Review each crater as visible or missing.
- Measure inner crater diameter with two edge clicks; the center is derived from the diameter midpoint.
- Record rim presence, optional outer rim diameter, and notes.
- Show fitted circle overlays for diameter measurements.
- Use zoomed crater-area viewing around the current or predicted crater location.
- Learn crater spacing from derived centers and suggest later crater frames.
- Save progress to CSV at any point.
- Import a saved CSV to continue a review.
- Generate and browse statistical analysis figures from exported CSV files.

## Requirements

- Python 3.11 or newer
- Windows, macOS, or Linux

Python dependencies are listed in `requirements.txt`.

## Project Layout

- `crater_analyzer/` contains the GUI application and core crater/video models.
- `scripts/` contains setup helpers and standalone CSV analysis.
- `data/` is an ignored local workspace for exported CSV files and generated analysis outputs.
- `examples/` contains small tracked example outputs, if kept for documentation.
- `README.md`, `requirements.txt`, and `pyproject.toml` describe setup, dependencies, and package metadata.

The repository root is kept for source and configuration files. Measurement CSVs, videos, and analysis outputs should stay out of version control.

## Setup

Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Windows, you can also use:

```bat
scripts\setup_venv.bat
```

To force a specific Python interpreter:

```bat
scripts\setup_venv.bat "C:\Path\To\python.exe"
```

## Run

```powershell
.\.venv\Scripts\Activate.ps1
python -m crater_analyzer
```

Or without activating the environment:

```powershell
.\.venv\Scripts\python.exe -m crater_analyzer
```

## Review Workflow

1. Click **Open MP4** and choose the scan video.
2. Confirm the known total crater count. The default is 400; if you change it, click **Apply Total**.
3. Start at crater 1 and follow **Guided Review**.
4. For each visible crater, click two opposite inner crater edges. This measures the inner diameter and derives the center.
5. If a resolidification rim is visible, click **Rim Present** before or during the inner-diameter step, then measure the outer rim diameter when prompted.
6. Use **Mark Missing** only when the crater cannot be seen.
7. After three visible craters are measured, the app suggests later crater frames and keeps the suggested crater position fixed at the learned scan location.
8. Use **Export CSV / Save Progress** at any point.
9. Use **Import CSV** later to reload that table and continue the review.

## During Review

- **Session** holds crater count, current crater, prediction status, and automation toggles.
- **Guided Review** shows the active step as a highlighted block.
- The video overlay repeats the current guided action so you do not need to keep checking the right panel.
- Measuring the inner diameter automatically marks that crater visible, derives the center from the diameter midpoint, and assumes no rim.
- Use **Mark Missing** only when the crater cannot be seen.
- Use **Rim Present** only for craters where a resolidification rim is visible.
- Diameter steps advance automatically after the second edge click.
- After each completed crater, the app pauses briefly so the measurement overlay can be checked before advancing.
- Press **Esc** or **Cancel Current Measurement** to clear a half-finished two-click measurement.
- Use **Undo Last** or **Redo** in Guided Review if a click or classification was wrong.
- Enable **Unlock manual override tools** at the bottom of Guided Review only when editing out of order.
- Keyboard shortcuts are available outside the notes box: **M** marks missing, **R** toggles rim present, **U** undoes, and **Y** redoes.
- Editing marks the session as **Unsaved changes** until **Export CSV / Save Progress** is used.
- Changing **Known total** requires **Apply Total**, so typing in the field does not immediately add or remove crater records.
- **Assist** contains optional automatic detection. Automatic suggestions require confirmation before being applied.
- If a CSV references a source video path, **Import CSV** offers to reopen that MP4 so review can continue against the correct video.

Diameter measurements are made with two edge clicks. The GUI draws both the diameter bar and a fitted circle to make the crater boundary easier to judge.

## Analyze CSV

The top toolbar includes **Analyze Last CSV** next to the CSV import/export controls. This is the easiest way to analyze the current review:

1. Use **Export CSV / Save Progress** at least once during the session.
2. Click **Analyze Last CSV**.
3. If there are unsaved edits, choose whether to export the current progress before analysis.
4. The app writes outputs to `<csv name>_analysis`. For CSVs saved in `data/csv/`, GUI analysis outputs are placed in `data/analysis/`.
5. The analysis results browser opens automatically so generated figures and CSV summaries can be inspected inside the GUI.

If no CSV has been exported or imported in the current session, **Analyze Last CSV** prompts you to export one first.

The same analysis can also be run from the command line on any exported crater CSV:

```powershell
.\.venv\Scripts\python.exe scripts\analyze_crater_csv.py path\to\crater_measurements.csv
```

By default, the analysis uses a conversion factor of `1.3421 um/px`. Override it with:

```powershell
.\.venv\Scripts\python.exe scripts\analyze_crater_csv.py path\to\crater_measurements.csv --um-per-pixel 1.3421
```

The analysis excludes `unreviewed` rows. Missing reviewed craters are included in status/count figures but excluded from diameter distributions because they do not have measured diameters.

Generated outputs include:

- Gaussian-fitted inner diameter distribution
- Inner diameter development along scan
- Binned scan-development plot
- Diameter by video frame
- Visibility and rim classification along scan
- Frame-spacing diagnostics
- Summary statistics CSV
- Outlier table for inner diameters greater than 2 standard deviations from the mean

## Notes

Automatic tools are intentionally conservative. Optical doubling, variable contrast, and ice texture can make crater detection unreliable, so all measurements remain editable.
