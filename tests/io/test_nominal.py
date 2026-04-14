import pandas as pd
import pytest
from ephys_analysis.io.nominal import load_nominal_variables


@pytest.fixture
def nominal_xlsx(tmp_path):
    """Create a small test nominal variables Excel file."""
    df = pd.DataFrame({
        "Sample #": [1666, 1667, 1668, 1669],
        "Sex": ["Male", "Female", "Male", "Female"],
        "Region": ["PL", "IL", "PL", "IL"],
    })
    path = tmp_path / "nominal.xlsx"
    df.to_excel(path, index=False)
    return path


class TestLoadNominalVariables:
    def test_returns_all_samples(self, nominal_xlsx):
        result = load_nominal_variables(nominal_xlsx)

        assert len(result) == 4

    def test_sample_ids_are_strings(self, nominal_xlsx):
        result = load_nominal_variables(nominal_xlsx)

        assert "1666" in result

    def test_maps_correct_values(self, nominal_xlsx):
        result = load_nominal_variables(nominal_xlsx)

        assert result["1666"]["Sex"] == "Male"
        assert result["1666"]["Region"] == "PL"
        assert result["1667"]["Sex"] == "Female"
