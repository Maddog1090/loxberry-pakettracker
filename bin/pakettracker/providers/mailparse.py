"""Gemeinsame Auswertung von Versand-/Tracking-Mails.

Sendungsnummern werden an mehreren Stellen gesucht, damit Layoutänderungen der
Anbieter nicht sofort alles brechen:
  1. Tracking-Links (Query-Parameter, Pfadsegmente, #-Fragmente)
  2. beschriftete Felder („Sendungsnummer: …“, „Tracking-ID …“)
Kandidaten werden anschließend gegen die Nummernformate des Anbieters geprüft.
Mailinhalte werden nie geloggt.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Callable, Iterable

from ..models import Shipment, Status, now_iso
from ..sources.mail import Mail
from .base import Provider, extract_eta, status_from_keywords

_URL_PARAM = re.compile(
    r"[?&;](?:piececode|idc|tracknum|tracknumbers|trackingnumber|tracking_number|trackingid|tracking-id|"
    r"parcelnumber|parcelno|parcel_number|parcelid|match|shipmentnumber|shipmentid|sendungsnummer|"
    r"inquirynumber\d*|trknbr|tn|id)=([A-Za-z0-9%-]{6,60})", re.I)
_URL_PATH = re.compile(
    r"/(?:parcel|parcels|sendung|sendungen|shipment|shipments|track|tracking|status|trace)/"
    r"(?:[a-z]{2}_[A-Z]{2}/)?(?:parcel/)?([A-Za-z0-9]{8,40})(?=[/?#\s\"'<>]|$)", re.I)
_URL_FRAGMENT = re.compile(r"#([A-Za-z0-9]{10,40})\b")
_LABELED = re.compile(
    r"(?:sendungs-?\s?(?:nummer|nr\.?)|paket-?\s?(?:nummer|nr\.?)|paketschein-?nummer|"
    r"tracking-?\s?(?:nummer|id|number|no\.?|nr\.?)|trackingnummer|track\s?id|"
    r"parcel\s?(?:number|no\.?)|shipment\s?(?:number|id)|sendungsverfolgungsnummer|"
    r"identcode|referenznummer der sendung)"
    r"\s*(?:lautet|ist|is)?\s*[:#.]?\s*((?:[A-Za-z0-9](?:[ ]?[A-Za-z0-9]){5,45}))", re.I)


def candidate_numbers(text: str) -> list[str]:
    """Mögliche Sendungsnummern in Reihenfolge des Vorkommens (normalisiert, ohne Duplikate)."""
    found: list[str] = []

    def add(raw: str) -> None:
        number = re.sub(r"%20|[\s-]", "", raw).upper()
        if 6 <= len(number) <= 45 and number not in found:
            found.append(number)

    for regex in (_URL_PARAM, _URL_PATH, _URL_FRAGMENT):
        for m in regex.finditer(text):
            add(m.group(1))
    for m in _LABELED.finditer(text):
        value = m.group(1)
        add(value)                      # mit Leerzeichen gruppierte Nummer („0034 0434 …“)
        add(value.split(" ")[0])        # nur das erste Token
    return found


def labeled_numbers(text: str) -> list[str]:
    """Nur Nummern hinter einer Beschriftung („Sendungsnummer: …“) – ohne Link-Parameter."""
    found: list[str] = []
    for m in _LABELED.finditer(text):
        for raw in (m.group(1), m.group(1).split(" ")[0]):
            number = re.sub(r"\s", "", raw).upper()
            if 6 <= len(number) <= 45 and number not in found:
                found.append(number)
    return found


def numbers_for(provider: type[Provider] | Provider, text: str) -> list[str]:
    return [n for n in candidate_numbers(text) if provider.match_confidence(n) > 0]


def short_description(subject: str, limit: int = 80) -> str:
    """Betreff ohne Weiterleitungs-Präfixe, gekürzt – dient als Beschreibung für Loxone."""
    subject = re.sub(r"^\s*((?:re|aw|fw|fwd|wg)\s*:\s*)+", "", subject, flags=re.I).strip()
    return subject if len(subject) <= limit else subject[: limit - 1].rstrip() + "…"


def mail_reference_date(mail: Mail) -> date:
    try:
        return date.fromisoformat(mail.date[:10])
    except ValueError:
        return date.today()


def parse_carrier_email(provider: Provider, mail: Mail,
                        status_rules: Callable[[str], Status | None] | None = None,
                        numbers: Iterable[str] | None = None) -> list[Shipment]:
    """Standardauswertung einer Paketdienst-Mail (Absender muss bereits geprüft sein)."""
    content = f"{mail.subject}\n{mail.text}"
    found = list(numbers) if numbers is not None else numbers_for(provider, content)
    if not found:
        return []
    detect_status = status_rules or status_from_keywords
    status = detect_status(mail.subject) or detect_status(mail.text) or Status.ANNOUNCED
    eta = extract_eta(content, mail_reference_date(mail))
    if not eta and status == Status.OUT_FOR_DELIVERY:
        eta = mail_reference_date(mail).isoformat()  # „heute in Zustellung“
    description = short_description(mail.subject)
    return [
        Shipment(
            provider=provider.id,
            tracking_number=number,
            description=description,
            status=status,
            status_text=description,
            eta=eta,
            last_update=mail.date or now_iso(),
            origins=["email"],
        )
        for number in found
    ]


class MailCarrierProvider(Provider):
    """Anbieter ohne öffentliche Tracking-API für Privatkunden: Status kommt aus deren Mails."""

    live_tracking = False

    def parse_email(self, mail: Mail) -> list[Shipment]:
        if not self.handles_sender(mail.sender):
            return []
        return parse_carrier_email(self, mail)
