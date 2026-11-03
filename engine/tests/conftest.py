import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def openmeteo_raw() -> str:
    return read_fixture("openmeteo_lyon_2023.json")


@pytest.fixture(scope="session")
def nasapower_raw() -> str:
    return read_fixture("nasapower_lyon_2023.json")


@pytest.fixture(scope="session")
def pvgis_csv_raw() -> str:
    return read_fixture("pvgis_tmy_lyon.csv")


@pytest.fixture(scope="session")
def pvgis_json_raw() -> str:
    return read_fixture("pvgis_tmy_lyon.json")
