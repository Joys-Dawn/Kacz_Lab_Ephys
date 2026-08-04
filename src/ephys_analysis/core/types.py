from dataclasses import dataclass, field
from enum import Enum


# Physiological constant: dV/dt threshold for AP detection (mV/ms)
DVDT_CRITERION_MV_MS = 28.0
INTERNEURON_FREQUENCY_THRESHOLD_HZ = 100.0


class QCStatus(Enum):
    PASSED = "PASSED"
    USER_REJECTED_VTHRESH = "User Rejected VThresh"
    USER_REJECTED_1S_AP = "User Rejected 1s AP"
    RMP_GT_VTHRESH = "RMP>VThresh"
    ANALYSIS_FAILED = "Failed to Analyze"


class AnalysisCancelled(Exception):
    """Raised when the user cancels analysis via a review dialog."""
    pass


@dataclass
class QCReview:
    """User's verdict from the QC review dialog.

    accepted: True if the user clicked Accept, False if Reject.
    override_vthresh_mv: If the user clicked a different sample on the AP
        plot to override the auto-detected threshold, this is the new value.
        None means "no override — keep the auto-detected value." Only meaningful
        when accepted is True.
    notes: Updated note for the reviewed AP source, or None to leave it unchanged.
    override_auto_reject: Explicitly retain an automatic RMP>VThresh rejection.
    """
    accepted: bool
    override_vthresh_mv: float | None = None
    notes: str | None = None
    override_auto_reject: bool = False


@dataclass
class BaselineFlag:
    """Baseline-QC details for one applicable voltage recording."""
    protocol: str
    file_path: str
    target_mv: float
    baseline_means_mv: list[float] = field(default_factory=list)
    out_of_range_sweeps: list[int] = field(default_factory=list)
    changed_sweep_pairs: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class BaselineReview:
    """User decisions for baseline-flagged recordings, keyed by ABF path."""
    decisions: dict[str, bool] = field(default_factory=dict)


@dataclass
class OneSAPReview:
    """User verdict for a flagged 1-second AP recording."""
    accepted: bool
    notes: str | None = None


@dataclass
class RMPResult:
    rmp_mv: float


@dataclass
class RiIhContaminatedSweep:
    """A Ri/Ih sweep that has an AP in its baseline or steady-state window.

    Per protocol docx: such sweeps must be excluded from Ri/Sag calculations.
    """
    sweep_num: int  # 1-indexed
    current_pa: float
    ap_in_baseline: bool
    ap_in_steady_state: bool


@dataclass
class RiIhResult:
    input_resistance_mohm: float
    sag_amp_mv: float
    sag_ratio_200pa: float
    sag_ratio_100pa: float
    contaminated_sweeps: list[RiIhContaminatedSweep] = field(default_factory=list)


@dataclass
class APFineResult:
    peak_amp_mv: float
    half_width_ms: float
    max_rise_slope_mv_ms: float
    max_decay_slope_mv_ms: float
    sweep_num: int
    current_threshold_pa: float  # measured cursor mean − baseline mean (R2S1 − R1S1)
    stim_baseline_pa: float  # R1S1: measured stim mean from 0–0.2 s
    stim_step_pa: float  # R2S1: measured stim mean from 0.29695–0.29885 s
    voltage_threshold_mv: float
    spike_num: int


@dataclass
class RampResult:
    rheobase_pa: float


@dataclass
class AHPResult:
    peak_mv: float
    ms200_mv: float
    ms1000_mv: float


@dataclass
class OneSAPSweep:
    current_pa: float
    spike_count: int
    firing_freq_hz: float
    isi_ms: list[float] = field(default_factory=list)
    raw_spike_count: int = 0
    stimulus_baseline_mv: float | None = None
    sudden_drop: bool = False
    flagged_high_firing: bool = False


@dataclass
class OneSAPResult:
    sweeps: list[OneSAPSweep] = field(default_factory=list)
    first_ff_hz: float = 0.0
    max_ff_hz: float = 0.0
    ithresh_pa: float = 0.0
    # None when no nominal 1s AP current reaches the measured Ithresh
    ithresh_ff_hz: float | None = None
    rheobase_su_ff_hz: float = 0.0
    first_sweep: int = -1
    sudden_drop_sweeps: list[int] = field(default_factory=list)
    baseline_at_or_above_zero_sweeps: list[int] = field(default_factory=list)
    high_firing_sweeps: list[int] = field(default_factory=list)

    @property
    def requires_review(self) -> bool:
        return bool(
            self.sudden_drop_sweeps
            or self.baseline_at_or_above_zero_sweeps
            or self.high_firing_sweeps
        )


@dataclass
class SampleResult:
    sample_id: str
    animal_id: str
    # Auto-extracted from filename/folder
    collection_date: str = ""
    experimenter: str = ""
    # User-entered nominal variables. Per spec: "name and add, or subtract
    # nominal variables at will" — the columns here come directly from the
    # user's nominal-variables Excel, not a hardcoded schema.
    nominal_vars: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    analysis_error: str = ""
    # Protocol results
    qc_status: QCStatus = QCStatus.PASSED
    rmp: RMPResult | None = None
    ap_fine: APFineResult | None = None
    ri_ih: RiIhResult | None = None
    ramp: RampResult | None = None
    one_s_ap: OneSAPResult | None = None
    ahp_5: AHPResult | None = None
    ahp_25: AHPResult | None = None
    ahp_50: AHPResult | None = None
    # For rejected recordings
    file_path: str = ""
    reject_sweep_num: int | None = None
    # True whenever the AP metrics came from analyze_ap_coarse (either because
    # the sample only has a coarse file, or because fine returned None and we
    # fell back). Drives the "AP Source" column in the export.
    ap_source_is_coarse: bool = False
    # True only for the surprise case: AP fine file was present but its
    # analyzer returned None and we fell back to coarse. Drives the post-
    # analysis status-bar popup so the user can re-check the duplicate-
    # resolver pick. Coarse-only samples (no fine recorded at all) do not
    # set this — they are expected.
    ap_used_coarse_fallback: bool = False

    @property
    def cell_type(self) -> str:
        """Mutually exclusive Cell Type annotation for spreadsheet output."""
        if (
            self.one_s_ap
            and self.one_s_ap.max_ff_hz >= INTERNEURON_FREQUENCY_THRESHOLD_HZ
        ):
            return "Interneuron"
        if self.ap_fine:
            if self.ap_fine.spike_num == 1:
                return "Regular"
            if self.ap_fine.spike_num > 1:
                return "Burst"
        return ""

    def to_common_dict(self) -> dict:
        """Common prefix columns for every output row.

        Fixed identity columns (Date, Experimenter, Animal ID, Sample #)
        followed by whatever nominal variables the user loaded, preserving
        their Excel column order.
        """
        return {
            "Collection Date": self.collection_date,
            "Experimenter": self.experimenter,
            "Animal ID": self.animal_id,
            "Sample #": self.sample_id,
            **self.nominal_vars,
            "Cell Type": self.cell_type,
            "NOTES": self.notes,
        }
