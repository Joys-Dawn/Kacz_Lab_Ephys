from dataclasses import replace
from hashlib import sha256

import numpy as np
import pytest

from ephys_analysis.core.abf_io import load_abf, get_sweep_data, reconstruct_currents
from ephys_analysis.core.pipeline import analyze_all, analyze_sample
from ephys_analysis.core.types import BaselineFlag, BaselineReview, OneSAPReview, QCStatus
from ephys_analysis.io.scanner import scan_project_folder
from ephys_analysis.protocols import (
    PROTO_AP_FINE, PROTO_AP_COARSE, PROTO_RI_IH, PROTO_1S_AP, PROTO_AHP_5,
    VOLTAGE_PROTOCOLS,
)
from ephys_analysis.protocols.ap import analyze_ap_fine, analyze_ap_coarse
from ephys_analysis.protocols.ahp import analyze_ahp, AHP_5
from ephys_analysis.protocols.one_s_ap import analyze_one_s_ap
from ephys_analysis.protocols.ri_ih import analyze_ri_ih
from ephys_analysis.protocols.rmp import analyze_rmp
from ephys_analysis.protocols.ramp import analyze_ramp


@pytest.fixture
def sample_info(sample_data_root):
    return next(info for info in scan_project_folder(sample_data_root).samples.values() if info.sample_id == "1666")


@pytest.mark.parametrize("offset", [-10.0, 7.25])
def test_offset_changes_only_voltage_in_all_requested_protocols(sample_info, offset):
    seen = set()
    for protocol, path in sample_info.protocols.items():
        before_hash = sha256(path.read_bytes()).digest()
        original = load_abf(path)
        corrected = load_abf(path, voltage_offset_mv=offset)
        expected = original.data.copy()
        if protocol in VOLTAGE_PROTOCOLS:
            seen.add(protocol)
            expected[0] += offset
        np.testing.assert_array_equal(corrected.data, expected)
        for sweep in range(original.sweepCount):
            response = get_sweep_data(original, sweep)
            if protocol in VOLTAGE_PROTOCOLS:
                response += offset
            np.testing.assert_array_equal(get_sweep_data(corrected, sweep), response)
        np.testing.assert_array_equal(load_abf(path).data, original.data)
        assert sha256(path.read_bytes()).digest() == before_hash
    assert seen == VOLTAGE_PROTOCOLS


@pytest.mark.parametrize("offset", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_voltage_offset_is_rejected(abf_rmp, offset):
    with pytest.raises(ValueError, match="finite"):
        load_abf(abf_rmp, voltage_offset_mv=offset)


@pytest.mark.parametrize("quick", [False, True])
@pytest.mark.parametrize("offset", [-10, 10])
def test_pipeline_uses_sample_offset_in_detailed_and_quick_analysis(sample_info, offset, quick):
    original = analyze_sample(sample_info, {})
    corrected = analyze_sample(replace(sample_info, voltage_offset_mv=offset), {}, skip_qc=quick)
    assert corrected.rmp.rmp_mv == pytest.approx(original.rmp.rmp_mv + offset, abs=1e-5)
    assert corrected.ap_fine.voltage_threshold_mv == pytest.approx(original.ap_fine.voltage_threshold_mv + offset)
    assert corrected.ap_fine.current_threshold_pa == original.ap_fine.current_threshold_pa
    assert corrected.qc_status == original.qc_status
    assert corrected.ap_fine == analyze_ap_fine(load_abf(sample_info.protocols[PROTO_AP_FINE], voltage_offset_mv=offset))
    assert corrected.ri_ih == analyze_ri_ih(load_abf(sample_info.protocols[PROTO_RI_IH], voltage_offset_mv=offset))
    assert corrected.ahp_5 == analyze_ahp(load_abf(sample_info.protocols[PROTO_AHP_5], voltage_offset_mv=offset), AHP_5)


def test_baseline_review_is_interleaved_per_sample_before_qc(sample_info, monkeypatch):
    from ephys_analysis.core import pipeline
    events = []
    samples = {("animal", sid): replace(sample_info, animal_id="animal", sample_id=sid) for sid in ("1", "2")}

    def flag(abf, protocol, file_path):
        if protocol == PROTO_AP_FINE:
            return BaselineFlag(protocol, file_path, -67, [-50] * abf.sweepCount, [1])

    def review(flags):
        sample_ids = {sid for sid, _ in flags}
        assert len(sample_ids) == 1
        events.append((sample_ids.pop(), "baseline"))
        return BaselineReview({flag.file_path: True for _, flag in flags})

    monkeypatch.setattr(pipeline, "analyze_baseline_qc", flag)
    results = analyze_all(
        samples, {}, baseline_reviewer=review,
        qc_reviewer=lambda sid, *args: events.append((sid, "qc")) or True,
    )
    assert events == [("1", "baseline"), ("1", "qc"), ("2", "baseline"), ("2", "qc")]
    assert all(result.qc_status == QCStatus.PASSED for result in results)


def test_baseline_flags_use_corrected_recording(sample_info, monkeypatch):
    from ephys_analysis.core import pipeline
    original_check = pipeline.analyze_baseline_qc
    checked = []

    def check(abf, protocol, file_path):
        original = get_sweep_data(load_abf(file_path), 0)
        expected = original - 10 if protocol in VOLTAGE_PROTOCOLS else original
        np.testing.assert_array_equal(get_sweep_data(abf, 0), expected)
        checked.append(protocol)
        return original_check(abf, protocol, file_path)

    monkeypatch.setattr(pipeline, "analyze_baseline_qc", check)
    corrected = replace(sample_info, voltage_offset_mv=-10)
    analyze_all({("animal", "1666"): corrected}, {}, baseline_reviewer=lambda flags: {
        flag.file_path: True for _, flag in flags
    })
    assert set(checked) == set(sample_info.protocols)


@pytest.mark.parametrize("analyzer", [analyze_ap_fine, analyze_ap_coarse])
def test_ap_exclusion_selects_next_original_sweep(abf_ap_fine_burst, analyzer):
    abf = load_abf(abf_ap_fine_burst)
    first = analyzer(abf)
    following = analyzer(abf, excluded_sweeps={first.sweep_num})
    assert following.sweep_num == first.sweep_num + 1
    assert following.current_threshold_pa > first.current_threshold_pa
    assert analyzer(abf, excluded_sweeps=set(range(1, abf.sweepCount + 1))) is None


def test_baseline_ap_exclusion_reaches_qc_and_preserves_other_protocols(sample_info, abf_ap_fine_burst, monkeypatch):
    from ephys_analysis.core import pipeline
    sample_info = replace(sample_info, protocols={**sample_info.protocols, PROTO_AP_FINE: abf_ap_fine_burst})
    original = analyze_sample(sample_info, {})
    path = str(sample_info.protocols[PROTO_AP_FINE])
    n = load_abf(path).sweepCount
    monkeypatch.setattr(pipeline, "analyze_baseline_qc", lambda abf, protocol, file_path: (
        BaselineFlag(protocol, file_path, -67, [-50] * n, [original.ap_fine.sweep_num])
        if protocol == PROTO_AP_FINE else None
    ))
    reviewed = []
    results = analyze_all(
        {(sample_info.animal_id, sample_info.sample_id): sample_info}, {},
        baseline_reviewer=lambda flags: BaselineReview({path: True}, {path: {original.ap_fine.sweep_num}}),
        qc_reviewer=lambda sid, source, ap, rmp: reviewed.append(ap.sweep_num) or True,
    )
    result = results[0]
    assert reviewed == [original.ap_fine.sweep_num + 1]
    assert result.ap_fine.sweep_num == reviewed[0]
    assert result.rmp == original.rmp
    assert result.ri_ih == original.ri_ih
    assert result.ramp == original.ramp
    assert result.ahp_5 == original.ahp_5
    assert result.qc_status == QCStatus.PASSED
    assert sample_info.excluded_sweeps == {}


def test_excluding_only_qualifying_fine_sweep_preserves_coarse_fallback(sample_info):
    original = analyze_sample(sample_info, {})
    path = str(sample_info.protocols[PROTO_AP_FINE])
    result = analyze_sample(replace(sample_info, excluded_sweeps={path: {original.ap_fine.sweep_num}}), {})
    assert result.ap_used_coarse_fallback is True
    assert result.ap_source_is_coarse is True
    assert result.ap_fine == analyze_ap_coarse(load_abf(sample_info.protocols[PROTO_AP_COARSE]))


def test_ahp_exclusion_averages_only_retained_sweeps(abf_ahp_5):
    abf = load_abf(abf_ahp_5)
    result = analyze_ahp(abf, AHP_5, excluded_sweeps={1})
    values = []
    for sweep in range(1, abf.sweepCount):
        y = get_sweep_data(abf, sweep)
        baseline = float(np.mean(y[:int(0.2 * abf.sampleRate)]))
        values.append(float(np.min(y[int(0.38 * abf.sampleRate):int(0.58 * abf.sampleRate)])) - baseline)
    assert result.peak_mv == np.mean(values)
    assert analyze_ahp(abf, AHP_5, set(range(1, abf.sweepCount + 1))) is None


def test_rin_exclusions_preserve_current_mapping_and_leave_unavailable_values_blank(abf_ri_ih):
    abf = load_abf(abf_ri_ih)
    currents = reconstruct_currents(abf)
    excluded = {i + 1 for i, current in enumerate(currents) if abs(current) <= 50}
    result = analyze_ri_ih(abf, excluded_sweeps=excluded)
    original = analyze_ri_ih(abf)
    assert result.input_resistance_mohm is None
    assert result.sag_amp_mv == original.sag_amp_mv
    assert result.sag_ratio_100pa == original.sag_ratio_100pa
    assert result.sag_ratio_200pa == original.sag_ratio_200pa
    assert not any(s.sweep_num in excluded for s in result.contaminated_sweeps)


def test_excluding_only_rmp_or_ramp_sweep_leaves_measurement_unavailable(abf_rmp, abf_ramp):
    assert analyze_rmp(load_abf(abf_rmp), excluded_sweeps={1}) is None
    assert analyze_ramp(load_abf(abf_ramp), excluded_sweeps={1}) is None


def test_excluded_one_s_sweeps_do_not_raise_review_flags(abf_1s_ap_high_firing):
    abf = load_abf(abf_1s_ap_high_firing)
    original = analyze_one_s_ap(abf)
    excluded = set(original.high_firing_sweeps + original.baseline_at_or_above_zero_sweeps)
    result = analyze_one_s_ap(abf, excluded_sweeps=excluded)
    assert result.requires_review is False
    assert [s.current_pa for s in result.sweeps] == [s.current_pa for s in original.sweeps]
    assert [s.spike_count for s in result.sweeps] == [s.spike_count for s in original.sweeps]
    assert result.max_ff_hz == max(s.firing_freq_hz for i, s in enumerate(original.sweeps, 1) if i not in excluded)


def test_one_s_review_cannot_reintroduce_baseline_exclusions(sample_info, monkeypatch):
    from ephys_analysis.core import pipeline
    from ephys_analysis.core.types import OneSAPResult, OneSAPSweep
    path = str(sample_info.protocols[PROTO_1S_AP])
    calls = []

    def analyze(*args, **kwargs):
        calls.append(kwargs.get("excluded_sweeps", set()))
        return OneSAPResult(sweeps=[OneSAPSweep(0, 0, 0), OneSAPSweep(100, 100, 100)], high_firing_sweeps=[2])

    monkeypatch.setattr(pipeline, "analyze_one_s_ap", analyze)
    result = analyze_sample(
        replace(sample_info, excluded_sweeps={path: {1}}), {},
        one_s_ap_reviewer=lambda *a: OneSAPReview(True, excluded_sweeps=set()),
    )
    assert calls == [{1}, {1}]
    assert result.qc_status == QCStatus.PASSED
