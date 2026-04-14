import pytest
from ephys_analysis.core.pipeline import analyze_sample, analyze_all
from ephys_analysis.core.types import QCStatus
from ephys_analysis.io.scanner import scan_project_folder


@pytest.fixture
def scan_result(sample_data_root):
    return scan_project_folder(sample_data_root)


@pytest.fixture
def sample_1666_info(scan_result):
    for (animal_id, sample_id), info in scan_result.samples.items():
        if sample_id == "1666":
            return info
    pytest.fail("Sample 1666 not found in scan result")


class TestAnalyzeSample:
    def test_returns_all_protocol_results_when_auto_accepted(self, sample_1666_info):
        result = analyze_sample(sample_1666_info, nominal_data={})

        assert result.sample_id == "1666"
        assert result.qc_status == QCStatus.PASSED
        assert result.rmp is not None
        assert result.ap_fine is not None
        assert result.ri_ih is not None
        assert result.ramp is not None
        assert result.one_s_ap is not None
        assert result.ahp_5 is not None
        assert result.ahp_25 is not None
        assert result.ahp_50 is not None

    def test_rejected_sample_skips_remaining_protocols(self, sample_1666_info):
        result = analyze_sample(
            sample_1666_info,
            nominal_data={},
            qc_reviewer=lambda sid, path, ap: False,
        )

        assert result.qc_status == QCStatus.USER_REJECTED_VTHRESH
        assert result.ri_ih is None
        assert result.ramp is None
        assert result.one_s_ap is None

    def test_nominal_data_populates_result_fields(self, sample_1666_info):
        nominal = {"1666": {"Behavior": "CFM", "Sex": "M", "Nucleus?": "PL11-B2"}}
        result = analyze_sample(sample_1666_info, nominal_data=nominal)

        assert result.nominal_vars == {"Behavior": "CFM", "Sex": "M", "Nucleus?": "PL11-B2"}
        # The common dict spreads nominal_vars after the identity columns
        common = result.to_common_dict()
        assert list(common.keys()) == [
            "Collection Date", "Experimenter", "Animal ID", "Sample #",
            "Behavior", "Sex", "Nucleus?",
        ]


class TestAnalyzeAll:
    def test_processes_all_samples(self, scan_result):
        results = analyze_all(scan_result.samples, nominal_data={})

        assert len(results) == len(scan_result.samples)

    def test_bad_sample_does_not_abort_batch(self, scan_result):
        """Inject a corrupted sample info and verify others still complete."""
        from ephys_analysis.io.scanner import SampleInfo
        from pathlib import Path

        bad_info = SampleInfo(
            animal_id="bad", sample_id="0000",
            protocols={"fake": Path("nonexistent.abf")},
        )
        samples = dict(scan_result.samples)
        samples[("bad", "0000")] = bad_info

        results = analyze_all(samples, nominal_data={})

        assert len(results) == len(samples)
        good_results = [r for r in results if r.sample_id != "0000"]
        assert all(r.rmp is not None for r in good_results)
