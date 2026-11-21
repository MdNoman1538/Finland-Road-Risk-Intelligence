"""Unit tests for the Finnish → English taxonomy layer (no database needed)."""

import pytest

from src.i18n import (
    translate_accident_type,
    translate_lighting,
    translate_severity,
    translate_surface,
    translate_vehicle,
)


@pytest.mark.parametrize(
    ("finnish", "english"),
    [
        ("Kuolemaan johtanut", "Fatal Crash"),
        ("Vakavaan loukkaantumiseen johtanut", "Severe Injury Crash"),
        ("Loukkaantumiseen johtanut", "Injury Crash"),
        ("Ei henkilövahinkoja", "Property Damage Only (No Injuries)"),
    ],
)
def test_severity_translates_all_canonical_values(finnish, english):
    assert translate_severity(finnish, "en") == english


@pytest.mark.parametrize(
    "fn",
    [translate_severity, translate_surface, translate_lighting, translate_vehicle, translate_accident_type],
)
def test_finnish_output_returns_canonical_value_unchanged(fn):
    assert fn("jäinen", "fi") == "jäinen"


@pytest.mark.parametrize(
    "fn",
    [translate_severity, translate_surface, translate_lighting, translate_vehicle, translate_accident_type],
)
def test_empty_value_is_passed_through(fn):
    assert fn("", "en") == ""


def test_surface_and_lighting_are_case_and_whitespace_insensitive():
    assert translate_surface("  JÄINEN ", "en") == "Icy"
    assert translate_lighting("Päivänvalo", "en") == "Daylight"


def test_both_dark_unlit_spellings_map_to_the_same_label():
    # The two schema eras spell this category differently.
    assert translate_lighting("pimeä (valaisematon)", "en") == translate_lighting("pimeä, valaisematon", "en")


def test_unknown_values_fall_back_to_the_original_text():
    assert translate_surface("something new", "en") == "something new"
    assert translate_severity("Uusi luokka", "en") == "Uusi luokka"


def test_accident_type_keeps_finnish_original_in_parentheses_and_normalises_spacing():
    result = translate_accident_type("  Kohtaaminen   suoralla. ", "en")
    assert result == "Head-on collision on straight road (Kohtaaminen suoralla.)"


def test_unknown_vehicle_is_capitalised():
    assert translate_vehicle("avaruusalus", "en") == "Avaruusalus"
