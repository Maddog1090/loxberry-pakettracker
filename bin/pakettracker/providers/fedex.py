"""FedEx – vorbereitet (standardmäßig aus).

FedEx bietet eine offizielle Track API (developer.fedex.com, OAuth). Bis zu
einer Anbindung werden FedEx-Benachrichtigungsmails ausgewertet.
"""
from __future__ import annotations

import re

from ..registry import register
from .mailparse import MailCarrierProvider


@register
class FedexProvider(MailCarrierProvider):
    id = "fedex"
    name = "FedEx"
    enabled_by_default = False
    detection_priority = 70
    email_domains = ("fedex.com",)
    tracking_patterns = (re.compile(r"\d{12}"), re.compile(r"\d{15}"), re.compile(r"\d{20}"),
                         re.compile(r"\d{22}"))
    strong_patterns = (re.compile(r"96\d{20}"),)  # FedEx Ground (22-stellig, Präfix 96)
    tracking_url_template = "https://www.fedex.com/fedextrack/?trknbr={number}"
