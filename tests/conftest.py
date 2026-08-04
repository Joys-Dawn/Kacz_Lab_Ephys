import pytest
from pathlib import Path

SAMPLE_DATA = Path(__file__).parent.parent / "sample_data"
SAMPLE_1666 = SAMPLE_DATA / "55 - 64280" / "1666"
SAMPLE_1669 = SAMPLE_DATA / "55 - 64280" / "1669"
SAMPLE_1533 = SAMPLE_DATA / "63550" / "1533"
SAMPLE_1542 = SAMPLE_DATA / "63559" / "1542"
SAMPLE_1566 = SAMPLE_DATA / "63555" / "1566"


@pytest.fixture
def sample_data_root():
    return SAMPLE_DATA


@pytest.fixture
def abf_rmp():
    return SAMPLE_1666 / "2026_02_04_JCA_0001.abf"


@pytest.fixture
def abf_epsc():
    return SAMPLE_1666 / "2026_02_04_JCA_0000.abf"


@pytest.fixture
def abf_ri_ih():
    return SAMPLE_1666 / "2026_02_04_JCA_0003.abf"


@pytest.fixture
def abf_ap_coarse():
    return SAMPLE_1666 / "2026_02_04_JCA_0004.abf"


@pytest.fixture
def abf_ap_fine():
    return SAMPLE_1666 / "2026_02_04_JCA_0005.abf"


@pytest.fixture
def abf_ap_fine_negative_pulse():
    return SAMPLE_1542 / "2025_12_10_0007.abf"


@pytest.fixture
def abf_ramp():
    return SAMPLE_1666 / "2026_02_04_JCA_0006.abf"


@pytest.fixture
def abf_ahp_5():
    return SAMPLE_1666 / "2026_02_04_JCA_0007.abf"


@pytest.fixture
def abf_ahp_25():
    return SAMPLE_1666 / "2026_02_04_JCA_0008.abf"


@pytest.fixture
def abf_1s_ap():
    return SAMPLE_1666 / "2026_02_04_JCA_0009.abf"


@pytest.fixture
def abf_1s_ap_sudden_drop():
    return SAMPLE_1533 / "63550_0019.abf"


@pytest.fixture
def abf_1s_ap_baseline_zero():
    return SAMPLE_1669 / "2026_02_04_DMG_0020.abf"


@pytest.fixture
def abf_1s_ap_high_firing():
    return SAMPLE_1566 / "2025_12_17_0012.abf"


@pytest.fixture
def abf_ri_ih_high_firing():
    return SAMPLE_1566 / "2025_12_17_0006.abf"


@pytest.fixture
def abf_ahp_50():
    return SAMPLE_1666 / "2026_02_04_JCA_0010.abf"
