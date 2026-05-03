from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def all_indices_payload() -> dict[str, Any]:
    return json.loads((FIXTURES / "nse_allindices.json").read_text(encoding="utf-8"))
