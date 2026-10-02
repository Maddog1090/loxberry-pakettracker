"""Hermes (Deutschland).

Eine Tracking-API bietet Hermes nur Geschäftskunden mit Vertrag (HSI/myHermes
Business). Für Privatkunden werden daher die Hermes-Benachrichtigungsmails
ausgewertet (Paketankündigung, „heute in Zustellung“, Zustellung, PaketShop).
"""
from __future__ import annotations

import re

from ..registry import register
from .mailparse import MailCarrierProvider


@register
class HermesProvider(MailCarrierProvider):
    id = "hermes"
    name = "Hermes"
    detection_priority = 20
    email_domains = ("myhermes.de", "hermesworld.com", "hermes-europe.de", "hermes-logistik-gruppe.de")
    strong_patterns = (re.compile(r"H\d{19}"),)          # neues Format, z.B. H1000…
    tracking_patterns = (re.compile(r"\d{14}"), re.compile(r"\d{16}"))
    tracking_url_template = "https://www.myhermes.de/empfangen/sendungsverfolgung/sendungsinformation#{number}"
