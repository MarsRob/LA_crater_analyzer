# LA Crater Analyzer

Dark-theme Python GUI for reviewing MP4 scans of evenly spaced laser-ablation craters in water ice.

The app supports:

- MP4 import and frame navigation.
- Contrast, brightness, gamma, sharpening, and CLAHE display adjustments for difficult videos.
- Exact frame entry plus +/-1, +/-10, and +/-100 frame stepping for finding the scan start after stationary video sections.
- A regular spacing model learned from the first three visible crater centers and refined as more craters are reviewed.
- A fixed scan-position model that predicts later craters at the same image location once calibration is active.
- A zoomed crater-area view for measuring around the current center or predicted location.
- Manual crater visibility, missing-crater, rim-presence, inner-diameter, and outer-diameter annotation.
- Optional, confirmation-based image-processing assistance for finding likely crater centers.
- CSV export of the collected crater table at any point during review.
- CSV import to resume a previous review session.

## Setup

This project expects Python 3.11 or newer. On this machine, the setup scripts will
auto-detect the Spyder/Anaconda runtime Python at
`%LOCALAPPDATA%\spyder-6\envs\spyder-runtime\python.exe` when available.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

You can also run `scripts\setup_venv.bat`. The batch script avoids PowerShell execution-policy issues.
To force a specific interpreter, pass it as the first argument:

```bat
scripts\setup_venv.bat "C:\Users\prh754\AppData\Local\spyder-6\envs\spyder-runtime\python.exe"
```

If `python` opens the Microsoft Store instead of showing a Python version, install Python from
<https://www.python.org/downloads/windows/> and enable "Add python.exe to PATH" during installation.

## Run

```powershell
.\.venv\Scripts\Activate.ps1
python -m crater_analyzer
```

## Analyze CSV

```powershell
.\.venv\Scripts\python.exe scripts\analyze_crater_csv.py 260415_craters_3501.csv
```

The analysis excludes `unreviewed` rows. Missing reviewed craters are included in status/count figures but excluded from diameter distributions because they do not have measured diameters.

## Basic Workflow

1. Click **Open MP4** and choose the scan video.
2. Enter the known total crater count.
3. Start at crater 1 and use the **Guided Review** panel.
4. For the first three visible craters, navigate manually and mark presence, center, rim, and diameter.
5. After three visible centers are recorded, the app suggests the next crater frame and keeps the suggested crater position fixed at the learned scan location.
6. Continue crater-by-crater, marking missing craters where needed.
7. Use **Export CSV / Save Progress** at any point to save the current table.
8. Use **Import CSV** later to reload that table and continue the review.

## During Review

- **Session** holds the crater count, current crater, prediction status, and automation toggles.
- **Guided Review** tells you the next required action.
- **Measurement Tools** are locked to the guided step by default. Use **Arm Center**, **Arm Inner Circle**, or **Arm Outer Circle** before clicking the image.
- Enable **Unlock tools for manual override** only when you need to edit out of order.
- **Assist** contains optional automatic detection. Automatic suggestions require confirmation before they are applied.
- If a CSV references a source video path, **Import CSV** offers to reopen that MP4 so the review can continue against the correct video.

Diameter measurements are made with two edge clicks. The GUI draws both the diameter bar and a circle fitted to those two points so the crater boundary is easier to judge.

The automatic tools are intentionally conservative. Optical doubling, variable contrast, and ice texture can make fully automatic crater analysis unreliable, so the GUI keeps all measurements editable.
