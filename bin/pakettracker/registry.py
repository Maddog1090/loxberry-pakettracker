"""Provider-Registry und automatische Anbietererkennung.

Jedes Modul in `pakettracker/providers/` wird automatisch importiert. Ein neuer
Anbieter braucht daher nur eine Datei mit einer `@register`-dekorierten Klasse.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from .providers.base import Provider

log = logging.getLogger(__name__)

_REGISTRY: dict[str, type[Provider]] = {}
_discovered = False
_HELPER_MODULES = {"base", "apibase", "mailparse", "checkdigits"}


def register(cls: type[Provider]) -> type[Provider]:
    if cls.id in _REGISTRY and _REGISTRY[cls.id] is not cls:
        raise ValueError(f"Provider-ID doppelt vergeben: {cls.id}")
    _REGISTRY[cls.id] = cls
    return cls


def _discover() -> None:
    global _discovered
    if _discovered:
        return
    _discovered = True
    from . import providers

    for mod in pkgutil.iter_modules(providers.__path__):
        if mod.name.startswith("_") or mod.name in _HELPER_MODULES:
            continue
        try:
            importlib.import_module(f"{providers.__name__}.{mod.name}")
        except Exception:  # ein defekter Provider soll die anderen nicht blockieren
            log.exception("Provider-Modul %s konnte nicht geladen werden", mod.name)


def provider_classes() -> list[type[Provider]]:
    _discover()
    return sorted(_REGISTRY.values(), key=lambda c: c.name.lower())


def get(provider_id: str) -> type[Provider] | None:
    _discover()
    return _REGISTRY.get(provider_id)


@dataclass(frozen=True)
class Candidate:
    provider: type[Provider]
    confidence: int


def candidates(tracking_number: str, enabled: Iterable[str] | None = None) -> list[Candidate]:
    """Alle passenden Anbieter, beste zuerst (Sicherheit, dann Verbreitung)."""
    allowed = set(enabled) if enabled is not None else None
    found = [Candidate(cls, cls.match_confidence(tracking_number)) for cls in provider_classes()
             if allowed is None or cls.id in allowed]
    found = [c for c in found if c.confidence > 0]
    return sorted(found, key=lambda c: (-c.confidence, c.provider.detection_priority, c.provider.id))


def is_ambiguous(found: list[Candidate]) -> bool:
    return len(found) > 1 and found[0].confidence == found[1].confidence


def detect(tracking_number: str, enabled: Iterable[str] | None = None) -> type[Provider] | None:
    """Wahrscheinlichster Anbieter oder None. Bei Gleichstand entscheidet die Verbreitung –
    die Weboberfläche weist dann auf die Mehrdeutigkeit hin."""
    found = candidates(tracking_number, enabled)
    return found[0].provider if found else None
