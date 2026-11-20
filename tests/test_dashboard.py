"""Smoke test: the Streamlit dashboard script runs end-to-end without raising."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.integration

APP = str(Path(__file__).resolve().parents[1] / "src" / "ui" / "app.py")


def test_dashboard_renders_without_exceptions():
    at = AppTest.from_file(APP, default_timeout=60).run()

    assert not at.exception, [e.value for e in at.exception]
    # Default view is Oulu: the headline metrics must be populated.
    labels = [m.label for m in at.metric]
    assert "Normalized Risk Score" in labels
    assert "Total Crashes in Radius" in labels


def test_dashboard_switches_to_finnish():
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.radio[0].set_value("Suomi").run()

    assert not at.exception, [e.value for e in at.exception]
    assert "Riskitaso" in [m.label for m in at.metric]
