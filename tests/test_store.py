"""Duplikate: gleiche Sendung aus mehreren Quellen, Platzhalter, manuelle Anbieterwahl."""
import logging

from pakettracker.models import Shipment, Status
from pakettracker.store import ShipmentStore

log = logging.getLogger("test")
ENABLED = ["dhl", "amazon", "gls", "ups"]


def mail_shipment(provider, number, status=Status.IN_TRANSIT, ts="2026-10-01T10:00:00+00:00", **kw):
    return Shipment(provider, number, status=status, last_update=ts, origins=["email"], **kw)


def test_same_id_merges():
    store = ShipmentStore([], ENABLED, log)
    store.add(mail_shipment("dhl", "N1", Status.ANNOUNCED, "2026-10-01T08:00:00+00:00"))
    store.add(mail_shipment("dhl", "N1", Status.IN_TRANSIT, "2026-10-01T09:00:00+00:00"))
    store.add(mail_shipment("dhl", "N1", Status.ANNOUNCED, "2026-10-01T08:00:00+00:00"))  # alte Mail erneut
    [s] = store.values()
    assert s.status == Status.IN_TRANSIT


def test_same_number_from_other_provider_is_same_shipment():
    store = ShipmentStore([], ENABLED, log)
    store.add(mail_shipment("dhl", "123456789012"))
    store.add(mail_shipment("gls", "123456789012", Status.DELIVERED, "2026-10-02T10:00:00+00:00"))
    [s] = store.values()
    assert s.provider == "dhl" and s.status == Status.DELIVERED


def test_manual_provider_choice_wins():
    store = ShipmentStore([], ENABLED, log)
    store.add(mail_shipment("dhl", "123456789012"))
    merged = store.add(Shipment("gls", "123456789012", description="Fahrradteile", origins=["manual"]))
    [s] = store.values()
    assert merged is s and s.id == "gls:123456789012"
    assert set(s.origins) == {"email", "manual"} and s.status == Status.IN_TRANSIT


def test_placeholder_replaced_by_real_shipment():
    store = ShipmentStore([], ENABLED, log)
    store.add(mail_shipment("amazon", "ORDER-302-1", Status.ANNOUNCED, "2026-09-29T10:00:00+00:00",
                            reference="302-1", description="Buch XY", eta="2026-10-09"))
    store.add(mail_shipment("amazon", "TBA000000000003", Status.IN_TRANSIT, reference="302-1"))
    [s] = store.values()
    assert s.tracking_number == "TBA000000000003"
    assert (s.status, s.description, s.eta) == (Status.IN_TRANSIT, "Buch XY", "2026-10-09")


def test_late_placeholder_merges_into_real_shipment():
    store = ShipmentStore([], ENABLED, log)
    store.add(mail_shipment("dhl", "00340434000000000003", reference="302-2"))
    store.add(mail_shipment("amazon", "ORDER-302-2", Status.ANNOUNCED, "2026-09-29T10:00:00+00:00", reference="302-2"))
    [s] = store.values()
    assert s.provider == "dhl" and s.status == Status.IN_TRANSIT


def test_disabled_carrier_rehomed_to_reporting_provider():
    store = ShipmentStore([], ["amazon"], log)
    s = store.add(mail_shipment("dhl", "00340434000000000003"), reported_by="amazon")
    assert s.id == "amazon:00340434000000000003"
    assert store.add(mail_shipment("hermes", "H1")) is None
