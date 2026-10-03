"""Bereitet die Sendungsliste Loxone-gerecht auf (Zähler, feste Slots).

Relative Texte („kommt heute“) und der Stale-Zustand werden bei jedem Lauf aus dem
heutigen Kalendertag (Europe/Berlin) neu berechnet und nie aus einem alten Stand übernommen.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from ..models import STATUS_PRIORITY, Shipment, Status, local_date, local_today


def _sort_key(s: Shipment) -> tuple:
    return (STATUS_PRIORITY.index(s.status), s.eta or "9999-99-99", s.id)


def _status_text(s: Shipment, today: date) -> str:
    text = s.display_text(today)
    # Bestand der Text nur aus einer veralteten Tagesangabe, bleibt die Statusbezeichnung
    return text if text or not s.status_text else s.status.label


def _slot(index: int, s: Shipment | None, today: date | None = None) -> dict:
    if s is None:
        return {"slot": index, "used": 0, "provider": "", "tracking_number": "", "description": "",
                "status": "", "status_code": 0, "status_label": "", "status_text": "", "eta": "", "eta_window": "",
                "eta_text": ""}
    today = today or local_today()
    return {"slot": index, "used": 1, "provider": s.provider, "tracking_number": s.tracking_number,
            "description": s.description, "status": s.status.key, "status_code": int(s.status),
            "status_label": s.status.label, "status_text": _status_text(s, today), "eta": s.eta,
            "eta_window": s.eta_window, "eta_text": s.eta_text(today)}


def _shipment(s: Shipment, today: date, stale: bool) -> dict:
    data = s.to_dict()
    data["status_text"] = _status_text(s, today)
    data["status_text_raw"] = s.status_text  # Original, Grundlage für die Neuberechnung im nächsten Lauf
    data["eta_text"] = s.eta_text(today, stale)
    data["stale"] = stale
    return data


def build(shipments: list[Shipment], provider_ids: list[str], slots: int, mock_mode: bool,
          today: date | None = None, provider_info: dict[str, dict] | None = None,
          now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = today or local_today(now)
    stale_ids = {s.id for s in shipments if s.is_stale(today, now)}
    active = [s for s in shipments if not s.is_final and s.id not in stale_ids]
    delivered_today = [s for s in shipments
                       if s.status == Status.DELIVERED and local_date(s.delivered_at) == today]
    visible = sorted(active + delivered_today, key=_sort_key)

    summary = {"active": len(active)}
    for st in Status:
        if st not in (Status.UNKNOWN, Status.DELIVERED, Status.RETURNED):
            summary[st.key] = sum(1 for s in active if s.status == st)
    summary["delivered_today"] = len(delivered_today)
    # Verstrichene Termine (verspätete Live-Sendungen) sind keine „nächste Zustellung“
    etas = sorted(s.eta for s in active if s.eta and s.eta >= today.isoformat())
    summary["next_eta"] = etas[0] if etas else ""
    summary["arriving_today"] = sum(1 for s in active if s.eta == today.isoformat())
    summary["stale"] = len(stale_ids)

    return {
        "updated": now.isoformat(timespec="seconds"),
        "updated_epoch": int(now.timestamp()),
        "mock_mode": mock_mode,
        "summary": summary,
        "providers": {
            pid: {
                "active": sum(1 for s in active if s.provider == pid),
                "shipment_count": sum(1 for s in shipments if s.provider == pid),
                **(provider_info or {}).get(pid, {}),
            }
            for pid in provider_ids
        },
        "slots": [_slot(i + 1, visible[i] if i < len(visible) else None, today) for i in range(slots)],
        "shipments": [_shipment(s, today, s.id in stale_ids) for s in sorted(shipments, key=_sort_key)],
    }
