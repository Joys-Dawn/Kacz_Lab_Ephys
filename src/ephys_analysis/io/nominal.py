import pandas as pd
from pathlib import Path


def load_nominal_variables(path: str | Path) -> dict[str, dict[str, str]]:
    """Read nominal variables from an Excel file.

    Expects a sheet where the first column is Sample # and remaining
    columns are variable names (e.g., SEX, BEHAVIOR).

    Returns:
        {sample_id: {var_name: var_value, ...}}
    """
    df = pd.read_excel(str(path))
    # First column is the sample identifier
    sample_col = df.columns[0]
    var_cols = df.columns[1:]

    result = {}
    for _, row in df.iterrows():
        sample_id = str(row[sample_col]).strip()
        result[sample_id] = {
            col: str(row[col]).strip() for col in var_cols
        }
    return result
