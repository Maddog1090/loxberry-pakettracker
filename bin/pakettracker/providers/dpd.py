"""DPD (Deutschland).

Die DPD-Webservices (inkl. Sendungsstatus) stehen nur Geschäftskunden mit
DPD-Vertrag zur Verfügung. Für Privatkunden werden die DPD-Benachrichtigungen
(Predict-Zeitfenster, Zustellung, Pickup-Paketshop) per E-Mail ausgewertet.
"""
from __future__ import annotations

import re

from ..registry import register
from .mailparse import MailCarrierProvider


@register
class DpdProvider(MailCarrierProvider):
    id = "dpd"
    name = "DPD"
    detection_priority = 30
    email_domains = ("dpd.de", "dpd.com", "dpdgroup.com")
    # 14-stellige Paketnummer, optional mit angehängtem Prüfzeichen
    tracking_patterns = (re.compile(r"\d{14}"), re.compile(r"\d{14}[0-9A-Z]"))
    tracking_url_template = "https://tracking.dpd.de/status/de_DE/parcel/{number}"
