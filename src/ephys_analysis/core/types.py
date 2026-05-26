from dataclasses import dataclass, field
from enum import Enum


# Physiological constant: dV/dt threshold for AP detection (mV/ms)
DVDT_CRITERION_MV_MS = 28.0


class QCStatus(Enum):
    PASSED = "PASSED"
    USER_REJECTED_VTHRESH = "User Rejected VThresh"
    RMP_GT_VTHRESH = "RMP>VThresh"


class AnalysisCancelled(Exception):
    """Raised when the user cancels analysis via the QC dialog."""
    pass


@dataclass
class QCReview:
    """User's verdict from the QC review dialog.

    accepted: True if the user clicked Accept, False if Reject.
    override_vthresh_mv: If the user clicked a different sample on the AP
        plot to override the auto-detected threshold, this is the new value.
        None means "no override — keep the auto-detected value." Only meaningful
        when accepted is True.
    """
    accepted: bool
    override_vthresh_mv: float | None = None


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
    current_threshold_pa: float  # measured plateau mean − baseline mean (R2S1 − R1S1)
    stim_baseline_pa: float  # R1S1: measured stim baseline (0–0.2 s mean)
    stim_step_pa: float  # R2S1: measured stim plateau mean (top 5% of peak in AP window)
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
    # spike_count / firing_freq_hz are None when the sweep was rejected for
    # hyper-firing (raw count > 50). None — not zero — so cross-cell averages
    # over the per-sweep FF columns exclude rejected sweeps via NaN rather
    # than dragging the mean toward zero. raw_spike_count is always populated.
    spike_count: int | None
    firing_freq_hz: float | None
    isi_ms: list[float] = field(default_factory=list)
    rejected: bool = False
    raw_spike_count: int = 0


@dataclass
class OneSAPResult:
    sweeps: list[OneSAPSweep] = field(default_factory=list)
    first_ff_hz: float = 0.0
    max_ff_hz: float = 0.0
    ithresh_pa: float = 0.0
    # None when AP fine's Ithresh (measured pA) does not land on any 1s AP sweep step
    ithresh_ff_hz: float | None = None
    rheobase_su_ff_hz: float = 0.0
    first_sweep: int = -1


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
        }
