"""TNT – vorbereitet (standardmäßig aus).

TNT gehört zu FedEx; Sendungen werden über TNT-Benachrichtigungsmails erkannt.
"""
from __future__ import annotations

import re

from ..registry import register
from .mailparse import MailCarrierProvider


@register
class TntProvider(MailCarrierProvider):
    id = "tnt"
    name = "TNT"
    enabled_by_default = False
    detection_priority = 80
    email_domains = ("tnt.com",)
    tracking_patterns = (re.compile(r"\d{9}"),)
    strong_patterns = (re.compile(r"GE\d{9}WW"),)
    tracking_url_template = "https://www.tnt.com/express/de_de/site/shipping-tools/tracking.html?cons={number}"
