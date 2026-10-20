# Kacz Lab Ephys Analysis

A desktop GUI that turns a folder of Axon `.abf` recordings into compiled spreadsheets of electrophysiology parameters. It walks every sample in your project, runs each protocol's analysis (RMP, Ih/Ri, AP fine, Ramp, 1s AP firing, 5/25/50 AHP), shows a per-cell quality-control review of the voltage threshold, then writes the final results into Excel workbooks laid out the way your lab already compiles data.

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

Detailed and Quick Analysis are independent
ways to run the loaded project.

### 1. Open Project Folder

Click **Open Project Folder** and pick the project root. The app walks every animal / sample / `.abf` file, reads each file's protocol string, and builds a tree view grouped by Animal → Sample → Files. If any sample has more than one file for the same protocol, a **duplicate resolver dialog** opens so you can preview each file's traces and pick which to keep.

Selecting an ABF also opens its trace preview and its **File Notes** editor. The preview reads the recorded response units from the ABF, so spontaneous EPSCs display and scale in pA while current-clamp protocols display in mV. Notes are stored against that selected file and carried into every exported workbook under `NOTES`.

### 2. Load Nominal Variables (optional)

Click **Load Nominal Variables** and pick an Excel file that maps each Sample # to any user-defined variables (e.g. Sex, Behavior, Internal, Nucleus?). The first column must be the Sample #; every remaining column becomes a column in the final output. You can use any column names you want — they propagate through verbatim. Skip this step if you don't need extra annotations.

### 3. Run Analysis

Click **Run Analysis**. The pipeline runs per sample in the order dictated by the QC gate:

```
RMP → AP fine → (VThresh QC review) → Ri/Ih → Ramp → 1s AP → (flag review when needed) → 5/25/50 AHP
```

Detailed analysis starts by checking the first 200 ms baseline of every
applicable voltage recording. EPSCs, membrane tests, non-mV recordings, and
recordings shorter than 200 ms are excluded from this check. Flagged files are
shown in a scrollable review before protocol analysis continues. Every flagged
file can be previewed and must be explicitly accepted or rejected. Rejected
recordings are removed from that sample's protocol set before analysis; the
sample's other accepted recordings remain available.
Select All and the per-row checkboxes support bulk Accept Selected or Reject Selected.
Previews show every sweep, including previews opened from the duplicate resolver.

Every sample with RMP and AP threshold data then appears in VThresh QC. A
sample whose RMP is more depolarized than its voltage threshold is labeled
`REJECTED - RMP>Threshold`; the user can keep that automatic rejection or use
`Override Auto-Reject` to retain the sample.

During VThresh QC, the AP threshold picker stays visible while the adjacent protocol selector can display any other recording from that sample. Notes for the AP source can also be edited in the same dialog.
Back revisits earlier QC decisions without repeating protocol reviews. After analysis,
Undo QC can correct the final or an earlier decision; export again to save corrections.
Both QC plots offer XY, X-only, and Y-only zoom.

### 4. Quick Analysis

Select one or more analyzable ABF files in the project tree, then click
**Quick Analysis**. Only those files are processed. Quick Analysis does not run
baseline QC, automatic `RMP>VThresh` QC, VThresh review, or 1s flag review. It
does not depend on a previous detailed run. Selected EPSC, membrane-test, or
other files without implemented analysis metrics are reported and omitted
rather than generating empty results. Processing errors are reported as
`Failed to Analyze`, never as automatic QC rejections. When processing
finishes, the completion prompt can open the export workflow immediately or
be dismissed to export later from the toolbar.

### 5. Export Results

Click **Export Results** and pick an output folder. One timestamp is generated for the export and included in every folder and filename. The app writes six result workbooks plus the existing audit exports:

| Output | Contents |
|---|---|
| `ALL PASSED_<timestamp>/ALL PASSED_<timestamp>.xlsx` | PASSED samples only, with one tab per protocol plus a `Fully Compiled` master tab. |
| `ALL REJECTED_<timestamp>/ALL REJECTED_<timestamp>.xlsx` | Every user-rejected, auto-rejected, or failed analysis. Rows identify `USER`, `AUTO`, or `FAILED TO ANALYZE` and include the source path and processing error. |
| `ALL CELLS (COMPILED)_<timestamp>/ALL CELLS (COMPILED)_<timestamp>.xlsx` | The PASSED and REJECTED workbooks merged tab-for-tab and sorted by Sample #. Passed rows have blank reject metadata. |
| `REGULAR SPIKING PASSED_<timestamp>/REGULAR SPIKING PASSED_<timestamp>.xlsx` | Passed Regular cells, with the same protocol tabs. |
| `BURST SPIKING PASSED_<timestamp>/BURST SPIKING PASSED_<timestamp>.xlsx` | Passed Burst cells, with the same protocol tabs. |
| `INTERNEURONS PASSED_<timestamp>/INTERNEURONS PASSED_<timestamp>.xlsx` | Passed Interneurons, with the same protocol tabs. |
| `Ri-Ih Contaminated Sweeps_<timestamp>/Ri-Ih Contaminated Sweeps_<timestamp>.xlsx` | Ri/Ih sweeps with an AP in the baseline or steady-state measurement window. |
| `Trimming Analysis_<timestamp>/Trimming Analysis_<timestamp>.xlsx` | Flat Sample #, RMP, VThresh, and QC status summary. |

ALL PASSED and ALL REJECTED remain separate for cohort comparison, and ALL CELLS provides their direct union. Empty groups still receive a workbook with a header-only master tab. Per-sample metrics are computed for rejected samples too; review status decides workbook placement, not whether the numbers are calculated.

---

## How Each Parameter Is Calculated

All measurements use Clampfit's numerical conventions so values match what the lab would compute by hand.

### Baseline QC (detailed analysis only)

For each applicable mV recording, the baseline is the mean of the first
200 ms of every sweep. EPSCs and membrane-test files are excluded. The target
is `-67 mV` for all applicable protocols except 5- and 25-spike AHP, which use
`-60 mV`. A file is flagged when either:

- Any sweep baseline is more than 10 mV above or below its target (not applied to RMP files).
- At least three pairs of adjacent sweeps differ by 4 mV or more.

Baseline flags never reject a recording automatically. Detailed analysis waits
for an explicit Accept or Reject decision for every flagged file, then excludes
the rejected recordings before protocol analysis begins.

### RMP

The reported RMP is the average of three 200 ms voltage means: the first 200 ms, a 200 ms window centered in the recording, and the final 200 ms.

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

Any Ri/Ih sweep whose baseline or steady-state window contains a spike (voltage peak ≥ 15 mV above 0 mV) is excluded from Ri and sag calculations and written to the timestamped `Ri-Ih Contaminated Sweeps_<timestamp>` workbook for inspection.
In detailed analysis, more than five contaminated sweeps prompt a Keep Recording
or Remove Recording review. Keeping still excludes contaminated sweeps; removing
affects only Ri/Ih, not the sample, and preserves the contamination audit.
If too few clean sweeps remain, uncomputable Rin/Sag measurements are blank.

### Voltage Threshold (AP fine)

Forward-difference dV/dt — `dvdt[i] = (V[i+1] − V[i]) / dt` — is computed within the 0.2975–0.3015 s window. The voltage threshold is `V[i+1]` at the first sample where dV/dt exceeds 28 mV/ms. This matches Clampfit's `diff()` operator. The sweep must also have a peak > 0 mV in the AP window (0.29–0.31 s) to qualify, guarding against subthreshold depolarizations that cross the dV/dt criterion without firing a full AP.

### AP Properties (peak amplitude, half-width, rise/decay slopes)

All measured within the AP window (t = 0.29–0.31 s) on the first-firing sweep:

- **Peak Amplitude (mV)** = max voltage − baseline (0–0.2 s mean).
- **Half-Width (ms)** = width at half-max amplitude.
- **Max Rise Slope (mV/ms)** = `max(dV/dt)` across the AP window.
- **Max Decay Slope (mV/ms)** = `min(dV/dt)` restricted to samples where `V > 0` mV. Without this restriction, shallow-peak APs pick up the steepest slope at the zero-crossing transition and report ~1 mV/ms too negative.

### Current Threshold (Ithresh)

Reported as three columns: `R1S1 Mean`, `R2S1 Mean`, and `Ithresh = R2S1 − R1S1`, using the measured stimulus signal (channel 1). Both cursor endpoints are included:

- **R1S1** = mean stimulus from 0–0.2 s.
- **R2S1** = mean stimulus from 0.29695–0.29885 s.

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

**Review flags**:
- **Sudden AP drop**: the current sweep has exactly 1 AP after the preceding sweep had at least 5 APs.
- **Stimulus baseline**: the mean voltage over the first 200 ms inside the 1-second stimulus step is at or above 0 mV.
- **High firing**: a sweep has at least 100 APs. The review dialog shows both the 1s AP and Ri/Ih recordings when Ri/Ih is available.

Flags do not automatically remove sweep values. The user can exclude individual
sweeps or remove only the 1s AP recording. Excluded sweeps are blank in exports
and do not contribute to summary measurements or classification; original sweep
numbers are preserved. This review never rejects the entire sample.
Detailed analysis presents these flags even when the sample was already rejected
by the earlier RMP threshold review; the earlier rejection status remains in
effect.

**Summary columns**:
- **First Sweep** — 1-based sweep number of the first sweep with at least one counted AP.
- **First FF** — spike count divided by stimulus-step duration on First Sweep.
- **Max FF** — highest firing frequency across retained sweeps.
- **Ithresh** — measured AP stimulus current from the AP threshold protocol.
- **Ithresh FF** — firing frequency of the first 1s AP sweep whose nominal current is at or above Ithresh. Blank only when no nominal current reaches Ithresh.
- **Rheobase SU FF** — firing frequency of the first sweep whose nominal current strictly exceeds rheobase.

These summaries use retained sweeps. For each retained sweep with at least three
spikes, the `1s Firing` tab reports the first ISI, last ISI (both in ms), and their
first/last ratio. Sweeps with fewer than three spikes keep their other measurements
but have blank ISI columns.

### Cell Type

`Cell Type` is included with the shared sample columns in every result tab. A
sample is classified as `Interneuron` when its 1s AP maximum firing frequency
is at least 100 Hz. Otherwise, the AP threshold sweep is classified as
`Regular` when it contains one spike or `Burst` when it contains more than one
spike. Interneuron classification takes precedence, so classifications are
mutually exclusive. Half-width is not used for Cell Type classification.

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
| Spontaneous EPSC preview | `1. Spontaneous EPSCs` |
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
