# Kacz Lab Ephys Analysis

A desktop GUI that turns a folder of Axon `.abf` recordings into a compiled spreadsheet of electrophysiology parameters. It walks every sample in your project, runs each protocol's analysis (RMP, Ih/Ri, AP fine, Ramp, 1s AP firing, 5/25/50 AHP), shows a per-cell quality-control review of the voltage threshold, then writes the final results into an Excel workbook laid out the way your lab already compiles data.

## Installation

Download the latest release from the [Releases page](https://github.com/Joys-Dawn/Kacz_Lab_Ephys/releases):

- **Windows**: `Kacz_Lab_Ephys-windows.zip`

Extract the zip and run `Kacz_Lab_Ephys.exe` inside. No Python installation required.

## Expected Data Directory Structure

The application expects `.abf` files organized in a three-level hierarchy:

```
project_folder/
    animal_id_1/
        sample_1/
            2026_01_16_JCA_0000.abf
            2026_01_16_JCA_0001.abf
            ...
        sample_2/
            ...
    animal_id_2/
        ...
```

- **Animal ID folder** — any name (e.g., `55 - 64280`).
- **Sample # folder** — any name (e.g., `1666`).
- **`.abf` filenames** must follow the pattern `YYYY_MM_DD_INITIALS_NNNN.abf` (the collection date and experimenter initials are extracted from the filename automatically).

Each sample folder typically contains one `.abf` per protocol. Protocol identity is read from each file's `abf.protocol` string — file order does not matter. Extra `.abf` files are fine; the app will flag duplicates of the same protocol and let you pick which to use.

## Application Workflow

The GUI has four actions in the toolbar, used in order:

### 1. Open Project Folder

Click **Open Project Folder** and pick the project root. The app walks every animal / sample / `.abf` file, reads each file's protocol string, and builds a tree view grouped by Animal → Sample → Files. If any sample has more than one file for the same protocol, a **duplicate resolver dialog** opens so you can preview each file's traces and pick which to keep.

### 2. Load Nominal Variables (optional)

Click **Load Nominal Variables** and pick an Excel file that maps each Sample # to any user-defined variables (e.g. Sex, Behavior, Internal, Nucleus?). The first column must be the Sample #; every remaining column becomes a column in the final output. You can use any column names you want — they propagate through verbatim. Skip this step if you don't need extra annotations.

### 3. Run Analysis

Click **Run Analysis**. The pipeline runs per sample in the order dictated by the QC gate:

```
RMP → AP fine → (VThresh QC review) → Ri/Ih → Ramp → 1s AP → 5/25/50 AHP
```

For each sample, after RMP and AP fine are computed, a **QC review dialog** opens showing:
- **Left**: the phase plot (dV/dt vs mV) for the first-firing sweep, with the computed voltage threshold marked as a vertical red line and the 28 mV/ms criterion as a horizontal orange line.
- **Right**: the response trace (mV vs time) for that sweep, with the voltage threshold drawn as a horizontal red line.

You can **Accept** (continue with remaining protocols), **Reject** (put this cell in a separate rejected folder and skip the rest), or **Cancel** (stop the whole batch).

Samples whose RMP is more depolarized than their voltage threshold are automatically excluded (the `RMP > VThresh` cutoff) — no dialog, straight to the rejected folder.

### 4. Export Results

Click **Export Results** and pick an output folder. The app writes six things:

| Output | Contents |
|---|---|
| `PASSED/results.xlsx` | Main workbook — one tab per protocol plus a `Fully Compiled` master tab with one row per sample. |
| `User Rejected VThresh/results.xlsx` | Samples you rejected at the QC review dialog. |
| `RMP gt VThresh/results.xlsx` | Samples auto-excluded by the QC cutoff. |
| `1s AP Rejected Sweeps/results.xlsx` | 1s AP sweeps that fired more than 50 spikes (zeroed in PASSED, preserved here for review). |
| `Ri-Ih Contaminated Sweeps/results.xlsx` | Ri/Ih sweeps that had an AP in their baseline (0–0.2 s) or steady-state (1.0–1.2 s) window — excluded from the Ri regression and sag calculations, preserved here for review. |
| `trimming_analysis.xlsx` | Flat summary: Sample #, RMP, VThresh, QC pass/fail — useful for at-a-glance cohort health checks. |

The `Fully Compiled` tab includes every sample — passed and excluded. Excluded samples get an `Excluded? = Yes` flag and a `Reason` column (`RMP > VThresh` or `User Rejected VThresh`) with their metric cells left blank.

---

## How Each Parameter Is Calculated

All measurements use Clampfit's numerical conventions so values match what the lab would compute by hand.

### RMP

Mean voltage over the first 200 ms of the 15 s gap-free recording.

### Input Resistance (Ri, MOhm)

Linear regression of response steady-state mV against measured-stimulus steady-state pA across Ri/Ih sweeps with `|nominal current| ≤ 50 pA`. The slope × 1000 is the input resistance in megohms. The measured stimulus (channel 1) is used for the x-axis, not the nominal list — this matches Clampfit's manual cursor workflow exactly.

**Windows per sweep** (response signal):
- Baseline: mean, 0–0.2 s
- Peak: antipeak (most negative) in 0.3–0.5 s
- Steady state: mean, 1.0–1.2 s

### Sag Amplitude and Sag Ratio

- **Sag Amplitude (mV)** = peak − baseline, averaged across the two most-negative-current sweeps (−200 pA from the Ri/Ih stimulus list).
- **Sag Ratio** = (steady state − baseline) / (peak − baseline), reported separately for the −200 pA sweeps and the −100 pA sweeps (averaged across the two repeats of each).

### Contaminated Sweep Detection

Any Ri/Ih sweep whose baseline or steady-state window contains a spike (voltage peak ≥ 15 mV above 0 mV) is excluded from Ri and sag calculations and written to `Ri-Ih Contaminated Sweeps/results.xlsx` for inspection.

### Voltage Threshold (AP fine)

Forward-difference dV/dt — `dvdt[i] = (V[i+1] − V[i]) / dt` — is computed within the 0.2975–0.3015 s window. The voltage threshold is `V[i+1]` at the first sample where dV/dt exceeds 28 mV/ms. This matches Clampfit's `diff()` operator. The sweep must also have a peak > 0 mV in the AP window (0.29–0.31 s) to qualify, guarding against subthreshold depolarizations that cross the dV/dt criterion without firing a full AP.

### AP Properties (peak amplitude, half-width, rise/decay slopes)

All measured within the AP window (t = 0.29–0.31 s) on the first-firing sweep:

- **Peak Amplitude (mV)** = max voltage − baseline (0–0.2 s mean).
- **Half-Width (ms)** = width at half-max amplitude.
- **Max Rise Slope (mV/ms)** = `max(dV/dt)` across the AP window.
- **Max Decay Slope (mV/ms)** = `min(dV/dt)` restricted to samples where `V > 0` mV. Without this restriction, shallow-peak APs pick up the steepest slope at the zero-crossing transition and report ~1 mV/ms too negative.

### Current Threshold (Ithresh)

Reported as three columns: `R1S1 Mean`, `R2S1 Mean`, and `Ithresh = R2S1 − R1S1`, using the measured stimulus signal (channel 1):

- **R1S1** = mean stimulus over 0–0.2 s (baseline).
- **R2S1** = mean stimulus over the AP window (0.29–0.31 s), restricted to samples ≥ 95% of the window's stimulus peak. This isolates the "flat top" of the command pulse and excludes the ramp-up/ramp-down edges. Matches Clampfit's manual-cursor convention.

The measured stimulus is used rather than the nominal value because the realised command pulse differs from the programmed amplitude by 5–20 pA.

### Spike Count at Threshold Sweep

Count of voltage peaks above 0 mV within the AP window on the first-firing sweep (`scipy.signal.find_peaks` with 2 ms minimum distance). Used to identify burst-spiking cells.

### Rheobase

Measured stimulus peak-to-peak from t = 0 s up to the first spike on the ramp sweep. First spike is detected using the same forward-diff dV/dt > 28 mV/ms criterion used for the AP fine threshold. Measured (not nominal) is required here because pClamp-injected perturbations on the ramp contribute physiologically to triggering the spike, and the reported rheobase captures them.

### 1s AP Firing Frequency

For each sweep of the 1s AP protocol, spikes are counted using `scipy.signal.find_peaks` with:
- `height = 0 mV` (protocol's spec threshold).
- `distance = 2 ms` (refractory dedupe).
- `prominence = 15 mV` — rejects the small oscillations of depolarization block (where voltage sits above 0 mV with ~5–15 mV wiggles while the cell is inactivated). Genuine APs have prominence ≫ 20 mV.

**Firing Frequency (Hz)** per sweep = spike count / step duration (1 s by default).

**Hyper-firing rejection**: sweeps with > 50 raw spikes are zeroed in the PASSED output (so summary metrics exclude them) and written to `1s AP Rejected Sweeps/results.xlsx` for the user to judge whether the cell is genuinely hyper-firing or an analysis artefact.

**Summary columns**:
- **First FF** — firing frequency of the first sweep that produced spikes.
- **Max FF** — highest firing frequency across all sweeps.
- **Ithresh FF** — firing frequency of the 1s AP sweep whose nominal current is closest to the measured Ithresh (from AP fine), within half a step size. Blank if no sweep qualifies — reporting 0 would falsely imply "no firing at Ithresh".
- **Rheobase SU FF** — firing frequency of the first sweep whose current exceeds rheobase.

### AHP (5 / 25 / 50 spike)

Each AHP protocol fires a train of 5, 25, or 50 brief current pulses, then records the afterhyperpolarization. Three metrics are reported for each train length, averaged across the protocol's two sweeps:

| Metric | Window after final pulse |
|---|---|
| Peak (mV) | antipeak within a 200 ms window starting ~2 ms after the final pulse |
| 200ms (mV) | mean over a 20 ms window starting 200 ms after the final pulse |
| sAHP (mV) | mean over a 20 ms window starting 1000 ms after the final pulse |

All three values are baseline-subtracted (baseline = mean over 0–0.2 s).

---

## Protocol Identification

Each `.abf` file is identified by its `abf.protocol` string, not by filename. The app looks for these protocol strings:

| Protocol | Expected `abf.protocol` |
|---|---|
| RMP | `2. Resting Membrane Potential` |
| Ri/Ih | `4. Ih and Input Resistance` |
| AP coarse (fallback) | `5a. Single AP coarse` |
| AP fine | `5b. Single AP fine` |
| Ramp | `6. Ramp 6s` |
| 5 AHP | `7. 5 Spike AHP` |
| 25 AHP | `8. 25 Spike AHP` |
| 1s AP | `9. 1s AP Firing` |
| 50 AHP | `11. 50 Spike AHP` |

If an AP fine file is missing, the app falls back to AP coarse for the threshold sweep detection.

## License

Proprietary. All rights reserved.
