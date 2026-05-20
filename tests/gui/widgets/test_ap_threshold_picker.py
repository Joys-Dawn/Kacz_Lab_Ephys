import numpy as np

from ephys_analysis.gui.widgets.ap_threshold_picker import APThresholdPicker
from ephys_analysis.core.types import DVDT_CRITERION_MV_MS


def _synthetic_ap(n: int = 80):
    """Linear V from -70 to +30 and dV/dt that crosses the criterion mid-window."""
    t_ms = np.arange(n) * 0.05  # 50 µs per sample
    v = np.linspace(-70.0, 30.0, n)
    # dV/dt: ramp from 0 to 100 mV/ms — crosses 28 around the same fraction.
    dvdt = np.linspace(0.0, 100.0, n)
    return t_ms, v, dvdt


class TestPlotAp:
    def test_auto_idx_marker_is_at_auto_sample(self, qtbot):
        w = APThresholdPicker()
        qtbot.addWidget(w)
        t_ms, v, dvdt = _synthetic_ap()
        # Pick a real crossing as the auto sample.
        auto = int(np.where(dvdt > DVDT_CRITERION_MV_MS)[0][0])

        w.plot_ap(t_ms, v, dvdt, auto_idx=auto)

        assert w.auto_idx == auto

    def test_default_selection_equals_auto(self, qtbot):
        w = APThresholdPicker()
        qtbot.addWidget(w)
        t_ms, v, dvdt = _synthetic_ap()

        w.plot_ap(t_ms, v, dvdt, auto_idx=40)

        assert w.selected_idx == 40

    def test_selected_voltage_matches_array(self, qtbot):
        w = APThresholdPicker()
        qtbot.addWidget(w)
        t_ms, v, dvdt = _synthetic_ap()

        w.plot_ap(t_ms, v, dvdt, auto_idx=40)

        assert w.selected_voltage_mv() == float(v[40])

    def test_selected_dvdt_matches_array(self, qtbot):
        w = APThresholdPicker()
        qtbot.addWidget(w)
        t_ms, v, dvdt = _synthetic_ap()

        w.plot_ap(t_ms, v, dvdt, auto_idx=40)

        assert w.selected_dvdt_mv_ms() == float(dvdt[40])


class TestSelectIndex:
    def test_moves_selected_idx(self, qtbot):
        w = APThresholdPicker()
        qtbot.addWidget(w)
        t_ms, v, dvdt = _synthetic_ap()
        w.plot_ap(t_ms, v, dvdt, auto_idx=40)

        w.select_index(55)

        assert w.selected_idx == 55

    def test_emits_threshold_picked_signal(self, qtbot):
        w = APThresholdPicker()
        qtbot.addWidget(w)
        t_ms, v, dvdt = _synthetic_ap()
        w.plot_ap(t_ms, v, dvdt, auto_idx=40)

        with qtbot.waitSignal(w.threshold_picked, timeout=200) as blocker:
            w.select_index(55)

        assert blocker.args == [55]

    def test_out_of_range_index_is_ignored(self, qtbot):
        w = APThresholdPicker()
        qtbot.addWidget(w)
        t_ms, v, dvdt = _synthetic_ap(n=80)
        w.plot_ap(t_ms, v, dvdt, auto_idx=40)

        w.select_index(999)

        assert w.selected_idx == 40


class TestTwinxPickEventFix:
    """The dV/dt twinx axis must not block pick events on the V line.

    matplotlib's twinx() puts the new axis in front of the original, which
    intercepts pick events. Regression: clicks on V-line markers stopped
    triggering threshold_picked. Fix: lift self.ax above _ax_dvdt and hide
    the patch so dV/dt stays visible underneath.
    """

    def test_picker_axis_is_above_dvdt_axis(self, qtbot):
        w = APThresholdPicker()
        qtbot.addWidget(w)
        t_ms, v, dvdt = _synthetic_ap()
        w.plot_ap(t_ms, v, dvdt, auto_idx=40)

        assert w.ax.get_zorder() > w._ax_dvdt.get_zorder()

    def test_picker_axis_patch_is_transparent(self, qtbot):
        w = APThresholdPicker()
        qtbot.addWidget(w)
        t_ms, v, dvdt = _synthetic_ap()
        w.plot_ap(t_ms, v, dvdt, auto_idx=40)

        assert w.ax.patch.get_visible() is False
