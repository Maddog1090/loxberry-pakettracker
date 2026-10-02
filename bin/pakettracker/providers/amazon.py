"""Amazon.

Amazon bietet Endkunden keine Tracking-API (die Selling Partner API ist nur für
Verkäufer). Status und Termine kommen daher ausschließlich aus den Versand- und
Zustellmails von Amazon. Es gibt bewusst keine Anmeldung bei amazon.de.

Die Auswertung stützt sich auf mehrere unabhängige Merkmale, damit
Layoutänderungen nicht alles brechen:
- Bestellnummer (###-#######-#######)          → Referenz der Sendung
- Amazon-Logistics-Nummer (TBA…)               → Sendung bei „Amazon“
- beschriftete Sendungsnummer + Paketdienst-Hinweis (DHL, Hermes, DPD, GLS, UPS)
                                               → Sendung beim Paketdienst (DHL/UPS dann live)
- nur Bestellnummer                            → Platzhalter ORDER-<nr>, der durch die echte
                                                 Sendung ersetzt wird, sobald deren Nummer bekannt ist
"""
from __future__ import annotations

import re

from .. import registry
from ..models import Shipment, Status, now_iso
from ..registry import register
from ..schema import Field
from ..sources.mail import Mail
from .base import CONFIDENCE_STRONG, Provider, extract_eta, sender_matches, status_from_keywords
from .mailparse import labeled_numbers, mail_reference_date, short_description

_ORDER_ID = re.compile(r"\b(\d{3}-\d{7}-\d{7})\b")
_TBA = re.compile(r"\b(TBA\d{12})\b", re.I)
_PRODUCT = re.compile(r"[„\"“»]([^„\"“”«»]{3,120})[“”\"«]")
_CARRIER_HINTS = (
    ("dhl", re.compile(r"\b(?:DHL|Deutsche Post)\b", re.I)),
    ("hermes", re.compile(r"\bHermes\b", re.I)),
    ("dpd", re.compile(r"\bDPD\b")),
    ("gls", re.compile(r"\bGLS\b")),
    ("ups", re.compile(r"\bUPS\b")),
)
PLACEHOLDER_PREFIX = "ORDER-"


@register
class AmazonProvider(Provider):
    id = "amazon"
    name = "Amazon"
    live_tracking = False
    detection_priority = 60
    email_domains = ("amazon.de", "amazon.com")
    settings_schema = (
        Field("sender_domains", "Absender-Domains", default="amazon.de, amazon.com",
              help="Kommagetrennt. Nur Mails dieser Absender werden ausgewertet."),
    )
    strong_patterns = (re.compile(r"TBA\d{12}"),)
    tracking_url_template = ""  # Amazon-Tracking nur über das Kundenkonto

    def handles_sender(self, sender: str) -> bool:
        domains = [d.strip().lower() for d in str(self.settings.get("sender_domains") or "").split(",")]
        return sender_matches(sender, [d for d in domains if d] or list(self.email_domains))

    @staticmethod
    def _carrier_hint(text: str) -> str | None:
        for provider_id, regex in _CARRIER_HINTS:
            if regex.search(text):
                return provider_id
        return None

    def parse_email(self, mail: Mail) -> list[Shipment]:
        if not self.handles_sender(mail.sender):
            return []
        content = f"{mail.subject}\n{mail.text}"
        orders = list(dict.fromkeys(_ORDER_ID.findall(content)))
        reference = orders[0] if orders else ""
        status = status_from_keywords(mail.subject) or status_from_keywords(mail.text) or Status.ANNOUNCED
        product = _PRODUCT.search(mail.subject)
        if product:
            description = short_description(product.group(1), 60)
        elif reference:
            description = f"Amazon-Bestellung {reference}"
        else:
            description = short_description(mail.subject)

        def shipment(provider_id: str, number: str) -> Shipment:
            return Shipment(provider=provider_id, tracking_number=number, description=description, status=status,
                            status_text=short_description(mail.subject),
                            eta=extract_eta(content, mail_reference_date(mail)),
                            last_update=mail.date or now_iso(), reference=reference, origins=["email"])

        tbas = list(dict.fromkeys(n.upper() for n in _TBA.findall(content)))
        result = [shipment(self.id, n) for n in tbas]

        carrier = self._carrier_hint(content)
        order_digits = {o.replace("-", "") for o in orders}
        for number in labeled_numbers(content):
            if number in tbas or number in order_digits or number.startswith("TBA"):
                continue
            target = None
            if carrier:
                cls = registry.get(carrier)
                if cls is not None and cls.match_confidence(number) > 0:
                    target = carrier
            if target is None:
                cls = registry.detect(number)
                if cls is not None and cls.id != self.id and cls.match_confidence(number) >= CONFIDENCE_STRONG:
                    target = cls.id
            if target:
                result.append(shipment(target, number))

        if not result and reference:
            result.append(shipment(self.id, f"{PLACEHOLDER_PREFIX}{reference}"))
        return result
