import pandas as pd
from ephys_analysis.core.types import (
    SampleResult, QCStatus, RMPResult, APFineResult,
    RiIhResult, RampResult, AHPResult, OneSAPResult, OneSAPSweep,
)
from ephys_analysis.io.excel_export import (
    export_passed, export_rejected_vthresh,
    export_hyperfiring_sweeps, export_trimming_analysis,
)


def _make_passed_sample(sample_id="1666") -> SampleResult:
    return SampleResult(
        sample_id=sample_id,
        animal_id="64280",
        qc_status=QCStatus.PASSED,
        collection_date="2026_02_04",
        experimenter="JCA",
        nominal_vars={
            "Sex": "Male",
            "Behavior": "CFM",
            "Internal": "Biocytin",
            "Nucleus?": "PL11-B2",
        },
        rmp=RMPResult(rmp_mv=-65.0),
        ap_fine=APFineResult(
            peak_amp_mv=80.0, half_width_ms=1.2,
            max_rise_slope_mv_ms=300.0, max_decay_slope_mv_ms=-100.0,
            sweep_num=2, current_threshold_pa=500.0,
            stim_baseline_pa=-50.0, stim_step_pa=450.0,
            voltage_threshold_mv=-45.0, spike_num=1,
        ),
        ri_ih=RiIhResult(
            input_resistance_mohm=150.0, sag_amp_mv=-10.0,
            sag_ratio_200pa=0.8, sag_ratio_100pa=0.9,
        ),
        ramp=RampResult(rheobase_pa=200.0),
        ahp_5=AHPResult(peak_mv=-5.0, ms200_mv=-2.0, ms1000_mv=-0.5),
        ahp_25=AHPResult(peak_mv=-8.0, ms200_mv=-3.0, ms1000_mv=-1.0),
        ahp_50=AHPResult(peak_mv=-10.0, ms200_mv=-4.0, ms1000_mv=-1.5),
        one_s_ap=OneSAPResult(
            sweeps=[
                OneSAPSweep(current_pa=0.0, spike_count=0, firing_freq_hz=0.0),
                OneSAPSweep(current_pa=50.0, spike_count=3, firing_freq_hz=3.0, isi_ms=[300.0, 350.0]),
            ],
            first_ff_hz=3.0, max_ff_hz=3.0,
            ithresh_pa=500.0, ithresh_ff_hz=3.0,
            rheobase_su_ff_hz=3.0, first_sweep=1,
        ),
    )


class TestExportPassed:
    def test_creates_file(self, tmp_path):
        results = [_make_passed_sample()]

        path = export_passed(results, tmp_path)

        assert path.exists()

    def test_has_one_tab_per_protocol(self, tmp_path):
        results = [_make_passed_sample()]

        path = export_passed(results, tmp_path)
        xl = pd.ExcelFile(str(path))

        expected_tabs = {"Fully Compiled", "RMP", "Rheobase", "Sag", "Rin",
                         "Current Threshold", "Compiled AP Properties",
                         "1s Firing", "5 AHP", "25 AHP", "50 AHP"}
        assert set(xl.sheet_names) == expected_tabs

    def test_rows_sorted_by_sample_id(self, tmp_path):
        s1 = _make_passed_sample("1666")
        s2 = _make_passed_sample("1000")
        results = [s1, s2]

        path = export_passed(results, tmp_path)
        df = pd.read_excel(str(path), sheet_name="RMP")

        assert [str(x) for x in df["Sample #"]] == ["1000", "1666"]

    def test_includes_variable_columns(self, tmp_path):
        results = [_make_passed_sample()]

        path = export_passed(results, tmp_path)
        df = pd.read_excel(str(path), sheet_name="RMP")

        # Identity columns always present
        assert "Collection Date" in df.columns
        assert "Experimenter" in df.columns
        assert "Animal ID" in df.columns
        assert "Sample #" in df.columns
        # Nominal columns come from the loaded fixture
        assert "Sex" in df.columns
        assert "Behavior" in df.columns
        assert "Nucleus?" in df.columns


class TestExportRejectedVThresh:
    def test_creates_file_with_correct_columns(self, tmp_path):
        s = SampleResult(
            sample_id="1667", animal_id="64280",
            qc_status=QCStatus.USER_REJECTED_VTHRESH,
            file_path="path/to/file.abf", reject_sweep_num=2,
        )

        path = export_rejected_vthresh([s], tmp_path)
        df = pd.read_excel(str(path))

        assert path.exists()
        assert len(df) == 1
        assert df["Sweep #"].iloc[0] == 2


class TestExportHyperfiringSweeps:
    def test_no_rejected_sweeps_returns_none(self, tmp_path):
        result = export_hyperfiring_sweeps([_make_passed_sample()], tmp_path)

        assert result is None

    def test_rejected_sweep_exported(self, tmp_path):
        s = _make_passed_sample()
        s.one_s_ap.sweeps.append(
            OneSAPSweep(
                current_pa=750.0, spike_count=0, firing_freq_hz=0.0,
                rejected=True, raw_spike_count=312,
            )
        )

        path = export_hyperfiring_sweeps([s], tmp_path)
        df = pd.read_excel(str(path))

        assert path.exists()
        assert len(df) == 1
        assert df["Raw Spike Count"].iloc[0] == 312
        assert df["Current (pA)"].iloc[0] == 750.0


class TestExportTrimmingAnalysis:
    def test_creates_file_with_qc_status(self, tmp_path):
        results = [_make_passed_sample()]

        path = export_trimming_analysis(results, tmp_path)
        df = pd.read_excel(str(path))

        assert path.exists()
        assert "QC Status" in df.columns
        assert df["QC Status"].iloc[0] == "PASSED"
