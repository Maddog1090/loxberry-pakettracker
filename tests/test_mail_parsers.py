"""E-Mail-Parser je Anbieter, robuste Nummernsuche, fehlerhafte Mails."""
import logging

import pytest

from pakettracker import registry
from pakettracker.models import Status
from pakettracker.providers.mailparse import candidate_numbers
from pakettracker.sources.mail import EmlDirectorySource, Mail, from_bytes

from conftest import FIXTURES

log = logging.getLogger("test")


@pytest.fixture
def mails():
    return {m.subject: m for m in EmlDirectorySource(str(FIXTURES), 36500, log).fetch()}


def parse(provider_id, mail, **settings):
    cls = registry.get(provider_id)
    defaults = {"enabled": True, "sender_domains": "amazon.de, amazon.com"}
    return cls({**defaults, **settings}, mock=False, log=log).parse_email(mail)


def test_hermes(mails):
    [s] = parse("hermes", mails["Ihre Hermes Sendung wird heute zugestellt"])
    assert (s.tracking_number, s.status, s.eta) == ("H1000000000000000001", Status.OUT_FOR_DELIVERY, "2026-10-02")


def test_dpd_grouped_number_and_predict_date(mails):
    [s] = parse("dpd", mails["Ihr DPD Paket kommt am 06.10.2026"])
    assert (s.tracking_number, s.status, s.eta) == ("01234567890123", Status.ANNOUNCED, "2026-10-06")


def test_gls_pickup_latin1(mails):
    [s] = parse("gls", mails["Ihr GLS Paket liegt im PaketShop zur Abholung bereit"])
    assert (s.tracking_number, s.status) == ("12345678901", Status.PICKUP_READY)


def test_ups_number_only_in_link(mails):
    [s] = parse("ups", mails["UPS Update: Paketzustellung voraussichtlich am Montag"])
    assert (s.tracking_number, s.status, s.eta) == ("1Z999AA10123456784", Status.IN_TRANSIT, "2026-10-05")


def test_amazon_routes_carrier_number_to_carrier(mails):
    [s] = parse("amazon", mails["Versandt: „USB-C Kabel 2m“"])
    assert (s.provider, s.tracking_number) == ("dhl", "00340434000000000003")
    assert (s.reference, s.description, s.eta) == ("302-0000000-0000002", "USB-C Kabel 2m", "2026-10-03")


def test_amazon_order_without_tracking_creates_placeholder(mails):
    [s] = parse("amazon", mails["Ihre Amazon.de Bestellung von „Buch XY“"])
    assert s.tracking_number == "ORDER-302-0000000-0000003"
    assert (s.status, s.eta, s.description) == (Status.ANNOUNCED, "2026-10-09", "Buch XY")


def test_amazon_custom_sender_domains(mails):
    mail = mails["Versandt: Ihre Amazon.de-Bestellung"]
    assert parse("amazon", mail, sender_domains="amazon.com") == []
    assert parse("amazon", mail, sender_domains="amazon.de")


def test_other_senders_ignored_by_all(mails):
    mail = mails["Ihr Paket kommt heute! (Werbung)"]
    for cls in registry.provider_classes():
        assert parse(cls.id, mail) == []


def test_broken_mime_does_not_crash(mails):
    mail = mails["Ihr DHL Paket kommt bald"]
    assert mail.date == ""
    [s] = parse("dhl", mail)
    assert s.tracking_number == "00340434000000000005"


@pytest.mark.parametrize("raw", [
    b"",
    b"\x00\xff\xfe garbage",
    b"From: noreply@dhl.de\nSubject: =?unknown?Q?x?=\n\n",
    b"From: noreply@dhl.de\nContent-Type: text/html; charset=utf-8\n\n<html><body><a href='x'>",
])
def test_garbage_mails(raw):
    mail = from_bytes(raw)
    for cls in registry.provider_classes():
        assert isinstance(parse(cls.id, mail), list)


@pytest.mark.parametrize("text, expected", [
    ("https://x/verfolgen.html?piececode=00340434000000000001&lang=de", "00340434000000000001"),
    ("https://tracking.dpd.de/status/de_DE/parcel/01234567890123", "01234567890123"),
    ("https://www.myhermes.de/x/sendungsinformation#H1000000000000000001", "H1000000000000000001"),
    ("Sendungs-Nr.: JJD 0000 0000 0000 0000 01", "JJD000000000000000001"),
    ("Tracking number 1Z999AA10123456784", "1Z999AA10123456784"),
    ("Ihre Paketnummer lautet 12345678901.", "12345678901"),
])
def test_candidate_numbers_layout_variants(text, expected):
    assert expected in candidate_numbers(text)


def test_mail_without_number_yields_nothing():
    mail = Mail(sender="noreply@dhl.de", subject="Neuigkeiten von DHL", date="2026-10-02T10:00:00+02:00",
                text="Jetzt neu: Paketkasten bestellen!")
    assert parse("dhl", mail) == []
