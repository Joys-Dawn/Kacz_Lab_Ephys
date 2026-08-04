import pandas as pd
from ephys_analysis.core.types import (
    SampleResult, QCStatus, RMPResult, APFineResult,
    RiIhResult, RampResult, AHPResult, OneSAPResult, OneSAPSweep,
    RiIhContaminatedSweep,
)
from ephys_analysis.io.excel_export import (
    export_passed, export_rejected, export_fully_compiled,
    export_trimming_analysis,
    export_ri_ih_contaminated_sweeps,
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

    def test_timestamp_is_in_passed_folder_and_filename(self, tmp_path):
        path = export_passed(
            [_make_passed_sample()],
            tmp_path,
            timestamp="20260714_153000",
        )

        assert path.parent.name == "PASSED Results_20260714_153000"
        assert path.name == "PASSED Results_20260714_153000.xlsx"

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

    def test_includes_notes_column(self, tmp_path):
        sample = _make_passed_sample()
        sample.notes = "2026_02_04_JCA_0009.abf: Reviewed firing pattern"

        path = export_passed([sample], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert df["NOTES"].iloc[0] == sample.notes

    def test_regular_cell_type_for_one_fine_ap_spike(self, tmp_path):
        sample = _make_passed_sample()

        path = export_passed([sample], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert df["Cell Type"].iloc[0] == "Regular"

    def test_burst_cell_type_for_multiple_fine_ap_spikes(self, tmp_path):
        sample = _make_passed_sample()
        sample.ap_fine.spike_num = 2

        path = export_passed([sample], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert df["Cell Type"].iloc[0] == "Burst"

    def test_interneuron_at_100_hz_overrides_fine_ap_type(self, tmp_path):
        sample = _make_passed_sample()
        sample.ap_fine.spike_num = 2
        sample.one_s_ap.max_ff_hz = 100.0

        path = export_passed([sample], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert df["Cell Type"].iloc[0] == "Interneuron"

    def test_below_100_hz_uses_fine_ap_type(self, tmp_path):
        sample = _make_passed_sample()
        sample.ap_fine.spike_num = 2
        sample.one_s_ap.max_ff_hz = 99.999

        assert sample.cell_type == "Burst"

    def test_no_spikes_leaves_cell_type_blank(self):
        sample = _make_passed_sample()
        sample.ap_fine.spike_num = 0
        sample.one_s_ap.max_ff_hz = 0.0

        assert sample.cell_type == ""

    def test_cell_type_is_in_every_standard_result_tab(self, tmp_path):
        sample = _make_passed_sample()

        path = export_passed([sample], tmp_path)
        workbook = pd.ExcelFile(str(path))

        for sheet_name in workbook.sheet_names:
            df = pd.read_excel(str(path), sheet_name=sheet_name)
            assert df["Cell Type"].iloc[0] == "Regular"

    def test_first_sweep_is_exported_one_based(self, tmp_path):
        sample = _make_passed_sample()
        assert sample.one_s_ap.first_sweep == 1

        path = export_passed([sample], tmp_path)
        df = pd.read_excel(str(path), sheet_name="1s Firing")

        assert df["First Sweep"].iloc[0] == 2

    def test_excludes_rejected_samples(self, tmp_path):
        """Per customer: PASSED composite contains only PASSED samples, not
        intermingled with rejected ones."""
        passed = _make_passed_sample(sample_id="1666")
        user_rejected = SampleResult(
            sample_id="1667", animal_id="64280",
            qc_status=QCStatus.USER_REJECTED_VTHRESH, file_path="path/to/x.abf",
            rmp=RMPResult(rmp_mv=-65.0),
        )
        auto_rejected = SampleResult(
            sample_id="1668", animal_id="64280",
            qc_status=QCStatus.RMP_GT_VTHRESH, file_path="path/to/y.abf",
            rmp=RMPResult(rmp_mv=-30.0),
        )

        path = export_passed([passed, user_rejected, auto_rejected], tmp_path)
        df = pd.read_excel(str(path), sheet_name="RMP")

        assert [str(x) for x in df["Sample #"]] == ["1666"]

    def test_does_not_carry_flag_column(self, tmp_path):
        """FLAG/File Path columns belong to the REJECTED composite only."""
        path = export_passed([_make_passed_sample()], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert "FLAG" not in df.columns

    def test_returns_none_when_no_passed_samples(self, tmp_path):
        user_rejected = SampleResult(
            sample_id="1667", animal_id="64280",
            qc_status=QCStatus.USER_REJECTED_VTHRESH, file_path="x.abf",
        )

        result = export_passed([user_rejected], tmp_path)

        assert result is None


def _make_rejected_sample(
    sample_id="1667", qc_status=QCStatus.USER_REJECTED_VTHRESH, file_path="path/to/file.abf",
) -> SampleResult:
    """A rejected sample that still has full analysis output (the pipeline
    runs every protocol regardless of QC status, so reject samples carry
    real metrics for the REJECTED composite)."""
    base = _make_passed_sample(sample_id)
    base.qc_status = qc_status
    base.file_path = file_path
    return base


class TestExportRejected:
    def test_empty_list_returns_none(self, tmp_path):
        result = export_rejected([], tmp_path)

        assert result is None

    def test_no_rejected_samples_returns_none(self, tmp_path):
        passed_sample = _make_passed_sample()

        result = export_rejected([passed_sample], tmp_path)

        assert result is None

    def test_writes_file_to_rejected_subdir(self, tmp_path):
        s = _make_rejected_sample()

        path = export_rejected([s], tmp_path)

        assert path is not None
        assert path.exists()
        assert path.parent.name.startswith("REJECTED Results_")

    def test_folder_and_file_include_same_timestamp(self, tmp_path):
        s = _make_rejected_sample()

        path = export_rejected([s], tmp_path, timestamp="20260714_153000")

        assert path.parent.name == "REJECTED Results_20260714_153000"
        assert path.name == "REJECTED Results_20260714_153000.xlsx"

    def test_has_same_tab_structure_as_passed(self, tmp_path):
        rejected = _make_rejected_sample()
        passed = _make_passed_sample()

        rejected_path = export_rejected([rejected], tmp_path)
        passed_path = export_passed([passed], tmp_path)

        rejected_tabs = set(pd.ExcelFile(str(rejected_path)).sheet_names)
        passed_tabs = set(pd.ExcelFile(str(passed_path)).sheet_names)
        assert rejected_tabs == passed_tabs

    def test_only_includes_rejected_samples(self, tmp_path):
        rejected = _make_rejected_sample(sample_id="1667")
        passed = _make_passed_sample(sample_id="1666")

        path = export_rejected([rejected, passed], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert len(df) == 1
        assert str(df["Sample #"].iloc[0]) == "1667"

    def test_user_rejected_sample_flagged_user(self, tmp_path):
        s = _make_rejected_sample(qc_status=QCStatus.USER_REJECTED_VTHRESH)

        path = export_rejected([s], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert df["FLAG"].iloc[0] == "USER"

    def test_one_s_ap_rejected_sample_flagged_user(self, tmp_path):
        s = _make_rejected_sample(qc_status=QCStatus.USER_REJECTED_1S_AP)

        path = export_rejected([s], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert df["FLAG"].iloc[0] == "USER"

    def test_rmp_gt_vthresh_sample_flagged_auto(self, tmp_path):
        s = _make_rejected_sample(qc_status=QCStatus.RMP_GT_VTHRESH)

        path = export_rejected([s], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert df["FLAG"].iloc[0] == "AUTO"

    def test_analysis_failure_is_labeled_with_error(self, tmp_path):
        s = SampleResult(
            sample_id="1669",
            animal_id="64280",
            qc_status=QCStatus.ANALYSIS_FAILED,
            file_path="path/to/unreadable.abf",
            analysis_error="cannot parse selected file",
        )

        path = export_rejected([s], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert df["FLAG"].iloc[0] == "FAILED TO ANALYZE"
        assert df["Analysis Error"].iloc[0] == "cannot parse selected file"

    def test_row_includes_file_path(self, tmp_path):
        s = _make_rejected_sample(file_path="path/to/bad.abf")

        path = export_rejected([s], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert df["File Path"].iloc[0] == "path/to/bad.abf"

    def test_combines_both_reject_categories(self, tmp_path):
        user_rejected = _make_rejected_sample(
            sample_id="1667", qc_status=QCStatus.USER_REJECTED_VTHRESH,
        )
        auto_rejected = _make_rejected_sample(
            sample_id="1668", qc_status=QCStatus.RMP_GT_VTHRESH,
        )

        path = export_rejected([user_rejected, auto_rejected], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert len(df) == 2
        flags = dict(zip([str(x) for x in df["Sample #"]], df["FLAG"]))
        assert flags["1667"] == "USER"
        assert flags["1668"] == "AUTO"

    def test_rows_sorted_by_sample_id(self, tmp_path):
        s1 = _make_rejected_sample(sample_id="2000")
        s2 = _make_rejected_sample(sample_id="1000")

        path = export_rejected([s1, s2], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert [str(x) for x in df["Sample #"]] == ["1000", "2000"]

    def test_metric_tab_carries_flag_and_file_path(self, tmp_path):
        s = _make_rejected_sample(file_path="path/to/bad.abf")

        path = export_rejected([s], tmp_path)
        df = pd.read_excel(str(path), sheet_name="RMP")

        assert "FLAG" in df.columns
        assert "File Path" in df.columns
        assert df["FLAG"].iloc[0] == "USER"
        assert df["File Path"].iloc[0] == "path/to/bad.abf"

    def test_rmp_metric_present_in_rmp_tab(self, tmp_path):
        s = _make_rejected_sample()

        path = export_rejected([s], tmp_path)
        df = pd.read_excel(str(path), sheet_name="RMP")

        assert df["Starting RMP (mV)"].iloc[0] == -65.0

    def test_skeleton_rejected_sample_appears_only_in_fully_compiled(self, tmp_path):
        """A rejected sample with no protocol results (legacy / very early
        failure) still produces a Fully Compiled row but skips per-protocol
        tabs whose builder returns None when data is missing.
        """
        s = SampleResult(
            sample_id="1667", animal_id="64280",
            qc_status=QCStatus.RMP_GT_VTHRESH, file_path="path/to/bad.abf",
        )

        path = export_rejected([s], tmp_path)
        xl = pd.ExcelFile(str(path))
        fc = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert "Fully Compiled" in xl.sheet_names
        assert "RMP" not in xl.sheet_names
        assert len(fc) == 1
        assert fc["FLAG"].iloc[0] == "AUTO"


class TestExportFullyCompiled:
    def test_merges_passed_and_rejected_samples_in_sample_order(self, tmp_path):
        passed = _make_passed_sample(sample_id="2000")
        rejected = _make_rejected_sample(sample_id="1000")

        path = export_fully_compiled(
            [passed, rejected], tmp_path, timestamp="20260714_153000"
        )
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert [str(value) for value in df["Sample #"]] == ["1000", "2000"]

    def test_merged_workbook_preserves_reject_flags(self, tmp_path):
        passed = _make_passed_sample(sample_id="1000")
        rejected = _make_rejected_sample(sample_id="2000")

        path = export_fully_compiled([passed, rejected], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        flags = dict(zip([str(value) for value in df["Sample #"]], df["FLAG"]))
        assert pd.isna(flags["1000"])
        assert flags["2000"] == "USER"

    def test_sample_numbers_are_sorted_numerically(self, tmp_path):
        sample_10 = _make_passed_sample(sample_id="10")
        sample_2 = _make_passed_sample(sample_id="2")

        path = export_fully_compiled([sample_10, sample_2], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert [str(value) for value in df["Sample #"]] == ["2", "10"]

    def test_uses_timestamped_folder_and_filename(self, tmp_path):
        path = export_fully_compiled(
            [_make_passed_sample()],
            tmp_path,
            timestamp="20260714_153000",
        )

        assert path.parent.name == "FULLY COMPILED Results_20260714_153000"
        assert path.name == "FULLY COMPILED Results_20260714_153000.xlsx"

    def test_returns_none_for_no_results(self, tmp_path):
        assert export_fully_compiled([], tmp_path) is None


class TestExportRiIhContaminatedSweeps:
    def test_returns_none_when_no_contamination(self, tmp_path):
        result = export_ri_ih_contaminated_sweeps([_make_passed_sample()], tmp_path)

        assert result is None

    def test_returns_none_for_samples_without_ri_ih(self, tmp_path):
        s = SampleResult(sample_id="1666", animal_id="64280")
        # s.ri_ih is None by default

        result = export_ri_ih_contaminated_sweeps([s], tmp_path)

        assert result is None

    def test_one_contaminated_sweep_produces_one_row(self, tmp_path):
        s = _make_passed_sample()
        s.ri_ih.contaminated_sweeps = [
            RiIhContaminatedSweep(
                sweep_num=3, current_pa=-100.0,
                ap_in_baseline=True, ap_in_steady_state=False,
            ),
        ]

        path = export_ri_ih_contaminated_sweeps([s], tmp_path)
        df = pd.read_excel(str(path))

        assert path.exists()
        assert len(df) == 1
        assert df["Sweep #"].iloc[0] == 3
        assert df["Current (pA)"].iloc[0] == -100.0
        assert bool(df["AP in Baseline"].iloc[0]) is True
        assert bool(df["AP in Steady State"].iloc[0]) is False

    def test_multiple_contaminated_sweeps_produce_one_row_each(self, tmp_path):
        s = _make_passed_sample()
        s.ri_ih.contaminated_sweeps = [
            RiIhContaminatedSweep(
                sweep_num=1, current_pa=-200.0,
                ap_in_baseline=True, ap_in_steady_state=False,
            ),
            RiIhContaminatedSweep(
                sweep_num=4, current_pa=50.0,
                ap_in_baseline=False, ap_in_steady_state=True,
            ),
        ]

        path = export_ri_ih_contaminated_sweeps([s], tmp_path)
        df = pd.read_excel(str(path))

        assert len(df) == 2


class TestFlaggedSweepValuesArePreserved:
    def test_per_sweep_ff_remains_numeric(self, tmp_path):
        sample = _make_passed_sample()
        sample.one_s_ap.sweeps.append(
            OneSAPSweep(
                current_pa=900.0,
                spike_count=120,
                firing_freq_hz=120.0,
                flagged_high_firing=True,
                raw_spike_count=120,
            )
        )

        path = export_passed([sample], tmp_path)
        df = pd.read_excel(str(path), sheet_name="1s Firing")

        assert df["FF 900pA"].iloc[0] == 120.0

    def test_per_sweep_isi_remains_numeric(self, tmp_path):
        sample = _make_passed_sample()
        sample.one_s_ap.sweeps.append(
            OneSAPSweep(
                current_pa=900.0,
                spike_count=120,
                firing_freq_hz=120.0,
                isi_ms=[8.0, 10.0],
                flagged_high_firing=True,
                raw_spike_count=120,
            )
        )

        path = export_passed([sample], tmp_path)
        df = pd.read_excel(str(path), sheet_name="1s Firing")

        assert df["ISI 900pA"].iloc[0] == 9.0

    def test_fully_compiled_per_sweep_ff_remains_numeric(self, tmp_path):
        sample = _make_passed_sample()
        sample.one_s_ap.sweeps.append(
            OneSAPSweep(
                current_pa=900.0,
                spike_count=120,
                firing_freq_hz=120.0,
                flagged_high_firing=True,
                raw_spike_count=120,
            )
        )

        path = export_passed([sample], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert df["FF 900pA"].iloc[0] == 120.0


class TestAPSourceColumn:
    """The pipeline can silently fall back to AP coarse when AP fine has no
    detectable spike. The "AP Source" column lets reviewers see which file
    the metrics came from without opening the ABFs themselves.
    """

    def test_fine_is_default(self, tmp_path):
        s = _make_passed_sample()

        path = export_passed([s], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Compiled AP Properties")

        assert df["AP Source"].iloc[0] == "fine"

    def test_coarse_when_flag_is_set(self, tmp_path):
        s = _make_passed_sample()
        s.ap_source_is_coarse = True

        path = export_passed([s], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Compiled AP Properties")

        assert df["AP Source"].iloc[0] == "coarse"

    def test_appears_in_current_threshold_tab(self, tmp_path):
        s = _make_passed_sample()
        s.ap_source_is_coarse = True

        path = export_passed([s], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Current Threshold")

        assert df["AP Source"].iloc[0] == "coarse"

    def test_appears_in_fully_compiled_tab(self, tmp_path):
        s = _make_passed_sample()
        s.ap_source_is_coarse = True

        path = export_passed([s], tmp_path)
        df = pd.read_excel(str(path), sheet_name="Fully Compiled")

        assert df["AP Source"].iloc[0] == "coarse"


class TestExportTrimmingAnalysis:
    def test_creates_file_with_qc_status(self, tmp_path):
        results = [_make_passed_sample()]

        path = export_trimming_analysis(results, tmp_path)
        df = pd.read_excel(str(path))

        assert path.exists()
        assert "QC Status" in df.columns
        assert df["QC Status"].iloc[0] == "PASSED"
