"""Bereitet die Sendungsliste Loxone-gerecht auf (Zähler, feste Slots)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from ..models import STATUS_PRIORITY, Shipment, Status, parse_ts


def _local_date(ts: str) -> date | None:
    dt = parse_ts(ts)
    return dt.astimezone().date() if dt else None


def _sort_key(s: Shipment) -> tuple:
    return (STATUS_PRIORITY.index(s.status), s.eta or "9999-99-99", s.id)


def _slot(index: int, s: Shipment | None) -> dict:
    if s is None:
        return {"slot": index, "used": 0, "provider": "", "tracking_number": "", "description": "",
                "status": "", "status_code": 0, "status_label": "", "status_text": "", "eta": ""}
    return {"slot": index, "used": 1, "provider": s.provider, "tracking_number": s.tracking_number,
            "description": s.description, "status": s.status.key, "status_code": int(s.status),
            "status_label": s.status.label, "status_text": s.status_text, "eta": s.eta}


def build(shipments: list[Shipment], provider_ids: list[str], slots: int, mock_mode: bool,
          today: date | None = None, provider_info: dict[str, dict] | None = None) -> dict:
    today = today or date.today()
    active = [s for s in shipments if not s.is_final]
    delivered_today = [s for s in shipments
                       if s.status == Status.DELIVERED and _local_date(s.delivered_at) == today]
    visible = sorted(active + delivered_today, key=_sort_key)

    summary = {"active": len(active)}
    for st in Status:
        if st not in (Status.UNKNOWN, Status.DELIVERED, Status.RETURNED):
            summary[st.key] = sum(1 for s in active if s.status == st)
    summary["delivered_today"] = len(delivered_today)
    etas = sorted(s.eta for s in active if s.eta)
    summary["next_eta"] = etas[0] if etas else ""
    summary["arriving_today"] = sum(1 for s in active if s.eta == today.isoformat())

    now = datetime.now(timezone.utc)
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
        "slots": [_slot(i + 1, visible[i] if i < len(visible) else None) for i in range(slots)],
        "shipments": [s.to_dict() for s in sorted(shipments, key=_sort_key)],
    }
