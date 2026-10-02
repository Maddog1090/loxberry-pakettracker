import logging
from datetime import date

import pytest

from pakettracker import registry
from pakettracker.models import Status
from pakettracker.providers.amazon import AmazonProvider
from pakettracker.providers.base import extract_eta, sender_matches, status_from_keywords
from pakettracker.providers.dhl import DhlProvider
from pakettracker.sources.mail import EmlDirectorySource

from conftest import FIXTURES

log = logging.getLogger("test")


@pytest.fixture
def mails():
    source = EmlDirectorySource(str(FIXTURES), lookback_days=36500, log=log)
    return {m.subject: m for m in source.fetch()}


@pytest.mark.parametrize("number, provider", [
    ("00340434000000000001", "dhl"),
    ("123456789012", "dhl"),
    ("JJD000000000000000001", "dhl"),
    ("tba000000000001", "amazon"),
    ("XYZ", None),
])
def test_detect(number, provider):
    cls = registry.detect(number)
    assert (cls.id if cls else None) == provider


@pytest.mark.parametrize("text, expected", [
    ("Ihr Paket wird heute zugestellt", Status.OUT_FOR_DELIVERY),
    ("Zugestellt: Ihr Paket", Status.DELIVERED),
    ("Versandt: Ihre Bestellung", Status.IN_TRANSIT),
    ("Ihr Paket liegt zur Abholung bereit", Status.PICKUP_READY),
    ("Hallo", None),
])
def test_status_keywords(text, expected):
    assert status_from_keywords(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Zustellung voraussichtlich: Samstag, 3. Oktober", "2026-10-03"),
    ("wird voraussichtlich am 05.10.2026 zugestellt", "2026-10-05"),
    ("Ihr Paket kommt heute", "2026-10-02"),
    ("Lieferung voraussichtlich 2. Januar", "2027-01-02"),  # Jahreswechsel
    ("Kein Termin", ""),
])
def test_extract_eta(text, expected):
    assert extract_eta(text, date(2026, 10, 2)) == expected


def test_sender_matches():
    assert sender_matches('"Amazon.de" <versandbestaetigung@amazon.de>', ["amazon.de"])
    assert sender_matches("noreply@mail.dhl.de", ["dhl.de"])
    assert not sender_matches("fake@amazon.de.example.com", ["amazon.de"])


def test_dhl_email(mails):
    provider = DhlProvider({}, mock=False, log=log)
    [shipment] = provider.parse_email(mails["Ihr DHL Paket kommt am Montag"])
    assert shipment.tracking_number == "00340434000000000001"
    assert shipment.status == Status.ANNOUNCED
    assert shipment.eta == "2026-10-05"


def test_unknown_sender_ignored(mails):
    provider = DhlProvider({}, mock=False, log=log)
    assert provider.parse_email(mails["Ihr Paket kommt heute! (Werbung)"]) == []


def test_amazon_emails(mails):
    provider = AmazonProvider({"sender_domains": "amazon.de"}, mock=False, log=log)
    [shipped] = provider.parse_email(mails["Versandt: Ihre Amazon.de-Bestellung"])
    [delivered] = provider.parse_email(mails["Zugestellt: Ihr Paket"])
    assert shipped.tracking_number == delivered.tracking_number == "TBA000000000001"
    assert (shipped.status, shipped.eta) == (Status.IN_TRANSIT, "2026-10-03")
    shipped.merge(delivered)
    assert shipped.status == Status.DELIVERED
    assert shipped.delivered_at.startswith("2026-10-03")


def test_dhl_api_mapping():
    data = {
        "status": {"timestamp": "2026-10-02T09:00:00+02:00", "statusCode": "transit",
                   "description": "Die Sendung wurde in das Zustellfahrzeug geladen."},
        "estimatedTimeOfDelivery": "2026-10-02T14:00:00+02:00",
        "events": [{"timestamp": "2026-10-02T09:00:00+02:00", "description": "Zustellfahrzeug",
                    "location": {"address": {"addressLocality": "Musterstadt"}}}],
    }
    shipment = DhlProvider.map_api_shipment(data, "00340434000000000001")
    assert shipment.status == Status.OUT_FOR_DELIVERY
    assert shipment.eta == "2026-10-02"
    assert shipment.events[0].location == "Musterstadt"
