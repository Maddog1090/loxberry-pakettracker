"""Automatische Anbietererkennung, manuelle Auswahl und unbekannte Nummern."""
import logging

import pytest

from pakettracker import registry
from pakettracker.providers import checkdigits
from pakettracker.sources import manual

log = logging.getLogger("test")
ALL_ACTIVE = ["dhl", "amazon", "hermes", "dpd", "gls", "ups"]


@pytest.mark.parametrize("number, provider", [
    ("1Z999AA10123456784", "ups"),          # Prüfziffer gültig
    ("1z999aa10123456784", "ups"),          # Kleinbuchstaben
    ("H1000000000000000001", "hermes"),
    ("TBA000000000001", "amazon"),
    ("RR473124829DE", "dhl"),               # UPU S10 mit gültiger Prüfziffer
    ("JJD000000000000000001", "dhl"),
    ("00340434000000000001", "dhl"),
    ("0034 0434 0000 0000 0001", "dhl"),    # mit Leerzeichen
    ("ZFX12ABC", "gls"),                    # GLS Track-ID
    ("12345678901", "gls"),                 # 11 Ziffern nur GLS
])
def test_unambiguous_numbers(number, provider):
    found = registry.candidates(number, ALL_ACTIVE)
    assert found[0].provider.id == provider
    assert not registry.is_ambiguous(found)


@pytest.mark.parametrize("number, best, others", [
    ("123456789012", "dhl", {"gls"}),         # 12 Ziffern: DHL oder GLS
    ("01234567890123", "hermes", {"dpd"}),    # 14 Ziffern: Hermes oder DPD
])
def test_ambiguous_numbers_report_alternatives(number, best, others):
    found = registry.candidates(number, ALL_ACTIVE)
    assert registry.is_ambiguous(found)
    assert found[0].provider.id == best
    assert {c.provider.id for c in found[1:]} == others


def test_strong_beats_weak():
    # 22 Ziffern mit Präfix 96 wäre FedEx – aber nur, wenn FedEx aktiv ist
    assert registry.detect("9612345678901234567890", ALL_ACTIVE) is None
    assert registry.detect("9612345678901234567890", ALL_ACTIVE + ["fedex"]).id == "fedex"


def test_invalid_check_digit_is_only_weak():
    assert registry.get("ups").match_confidence("1Z999AA10123456785") == 1
    assert registry.get("dhl").match_confidence("RR473124828DE") == 1


@pytest.mark.parametrize("number", ["XYZ", "", "!!!!!!", "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ABCDEFGHIJ"])
def test_unknown_numbers(number):
    assert registry.detect(number, ALL_ACTIVE) is None
    assert manual.to_shipment({"tracking_number": number or "-", "provider": "auto"}, log, ALL_ACTIVE) is None


def test_disabled_providers_not_detected():
    assert registry.detect("1Z999AA10123456784", ["dhl"]) is None


def test_manual_choice_beats_detection():
    shipment = manual.to_shipment({"tracking_number": "1Z999AA10123456784", "provider": "dhl"}, log, ALL_ACTIVE)
    assert shipment.provider == "dhl" and shipment.origins == ["manual"]


def test_legacy_auto_entries_still_resolved():
    shipment = manual.to_shipment({"tracking_number": "00340434000000000001", "provider": "auto"}, log)
    assert shipment.provider == "dhl"


def test_check_digits():
    assert checkdigits.ups_1z("1Z023E2X0214323462")      # Beispiel aus der UPS-Spezifikation
    assert checkdigits.upu_s10("AA473124829GB")          # Beispiel aus UPU S10
    assert not checkdigits.upu_s10("AA473124828GB")
    assert checkdigits.gs1_mod10("4006381333931")         # EAN-13
