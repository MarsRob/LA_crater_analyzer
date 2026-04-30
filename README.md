# LA Crater Analyzer

Python GUI for reviewing MP4 scans of evenly spaced laser-ablation craters in water ice.

The application is designed for semi-manual crater review where video contrast, optical doubling, missing craters, or variable illumination make fully automatic analysis unreliable.

## Features

- Import MP4 crater-scan videos.
- Navigate by slider, exact frame number, and +/-1, +/-10, +/-100 frame steps.
- Adjust brightness, contrast, gamma, CLAHE, and sharpening for difficult frames.
- Review each crater as visible or missing.
- Record crater center, rim presence, inner diameter, outer rim diameter, and notes.
- Show fitted circle overlays for diameter measurements.
- Use zoomed crater-area viewing around the current or predicted crater location.
- Learn crater spacing from reviewed centers and suggest later crater frames.
- Save progress to CSV at any point.
- Import a saved CSV to continue a review.
- Generate statistical analysis figures from exported CSV files.

## Requirements

- Python 3.11 or newer
- Windows, macOS, or Linux

Python dependencies are listed in `requirements.txt`.

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
2. Enter the known total crater count.
3. Start at crater 1 and use **Guided Review**.
4. For the first three visible craters, navigate manually and mark presence, center, rim state, and diameter.
5. After three visible centers are recorded, the app suggests later crater frames and keeps the suggested crater position fixed at the learned scan location.
6. Continue crater-by-crater, marking missing craters where needed.
7. Use **Export CSV / Save Progress** at any point.
8. Use **Import CSV** later to reload that table and continue the review.

## During Review

- **Session** holds crater count, current crater, prediction status, and automation toggles.
- **Guided Review** tells you the next required action.
- **Measurement Tools** are locked to the guided step by default.
- Use **Arm Center**, **Arm Inner Circle**, or **Arm Outer Circle** before clicking the image.
- Enable **Unlock tools for manual override** only when editing out of order.
- **Assist** contains optional automatic detection. Automatic suggestions require confirmation before being applied.
- If a CSV references a source video path, **Import CSV** offers to reopen that MP4 so review can continue against the correct video.

Diameter measurements are made with two edge clicks. The GUI draws both the diameter bar and a fitted circle to make the crater boundary easier to judge.

## Analyze CSV

Run the analysis script on an exported crater CSV:

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
