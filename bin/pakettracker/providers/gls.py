"""GLS (Deutschland).

Die GLS-Track&Trace-API erfordert MyGLS-Zugangsdaten eines Versenders mit
Vertrag. Für Privatkunden werden die GLS-Benachrichtigungsmails ausgewertet.
"""
from __future__ import annotations

import re

from ..registry import register
from .mailparse import MailCarrierProvider


@register
class GlsProvider(MailCarrierProvider):
    id = "gls"
    name = "GLS"
    detection_priority = 40
    email_domains = ("gls-pakete.de", "gls-group.eu", "gls-group.com", "gls-germany.com", "gls-one.de")
    tracking_patterns = (
        re.compile(r"\d{11}"),                                  # Paketnummer ohne Prüfziffer
        re.compile(r"\d{12}"),                                  # Paketnummer mit Prüfziffer
        re.compile(r"(?=[A-Z0-9]{8}$)(?=.*[A-Z])(?=.*\d)[A-Z0-9]{8}"),  # Track-ID (Buchstaben + Ziffern)
    )
    tracking_url_template = "https://www.gls-pakete.de/sendungsverfolgung?trackingNumber={number}"
