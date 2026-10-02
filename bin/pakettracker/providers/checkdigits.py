"""Prüfziffern öffentlich dokumentierter Nummernformate.

Nur Verfahren, die sicher bekannt sind. Eine gültige Prüfziffer erhöht die
Erkennungssicherheit; eine ungültige schließt einen Anbieter nie aus
(Tippfehler oder unbekannte Varianten sollen nicht zu „unbekannt“ führen).
"""
from __future__ import annotations


def ups_1z(number: str) -> bool:
    """UPS „1Z“-Nummer (18 Zeichen): Mod-10 über Zeichen 3–17, Buchstaben → (ord-63) % 10."""
    if len(number) != 18 or not number.startswith("1Z"):
        return False
    body, check = number[2:17], number[17]
    if not check.isdigit():
        return False
    total = 0
    for i, ch in enumerate(body):
        if ch.isdigit():
            value = int(ch)
        elif ch.isalpha():
            value = (ord(ch) - 63) % 10
        else:
            return False
        total += value * 2 if i % 2 else value
    return (10 - total % 10) % 10 == int(check)


def upu_s10(number: str) -> bool:
    """UPU S10 (z.B. RR123456789DE): 8 Ziffern + Mod-11-Prüfziffer, Gewichte 8 6 4 2 3 5 9 7."""
    if len(number) != 13 or not (number[:2].isalpha() and number[2:11].isdigit() and number[11:].isalpha()):
        return False
    total = sum(int(d) * w for d, w in zip(number[2:10], (8, 6, 4, 2, 3, 5, 9, 7)))
    check = 11 - total % 11
    check = {10: 0, 11: 5}.get(check, check)
    return check == int(number[10])


def gs1_mod10(number: str) -> bool:
    """GS1-Prüfziffer (z.B. SSCC/NVE): Gewichte 3/1 von rechts, letzte Stelle ist die Prüfziffer."""
    if not number.isdigit() or len(number) < 2:
        return False
    body, check = number[:-1], int(number[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check
