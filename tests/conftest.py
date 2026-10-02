import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))

FIXTURES = Path(__file__).parent / "fixtures"

# Sicherheitsnetz: Kein Test darf die echte DHL-API erreichen. Tests, die HTTP
# brauchen, setzen API_URL explizit auf ihren lokalen Testserver.
from pakettracker.providers.dhl import DhlProvider  # noqa: E402

from pakettracker.providers.hermes import HermesProvider  # noqa: E402
from pakettracker.providers.ups import UpsProvider  # noqa: E402

DhlProvider.API_URL = "http://127.0.0.1:9/echte-dhl-api-in-tests-gesperrt"
UpsProvider.BASE_URL = "http://127.0.0.1:9/echte-ups-api-in-tests-gesperrt"
HermesProvider.API_URL = "http://127.0.0.1:9/echte-hermes-api-in-tests-gesperrt"


@pytest.fixture
def plugin_root(tmp_path, monkeypatch):
    """Isolierte Plugin-Verzeichnisse (config/, data/, log/) für einen Test."""
    monkeypatch.setenv("PAKETTRACKER_ROOT", str(tmp_path))
    from pakettracker import config
    from pakettracker.loxberry import get_paths

    paths = get_paths()
    config.init(paths)
    return paths
