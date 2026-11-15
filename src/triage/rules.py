"""Règles déterministes de sécurité sur les constantes vitales.

Seuils repris des critères chiffrés du référentiel FRENCH (lignes dyspnée, hypotension,
tachycardie, bradycardie, hypertension, fièvre, hypothermie, altération de la conscience).
Ils servent de plancher : le niveau final n'est jamais moins grave que celui qu'ils imposent.
Les seuils de FC, FR, PA et température ne valent que pour l'adulte.
"""

from __future__ import annotations

from dataclasses import dataclass

from triage.data.schema import Vitals

LEVEL_ORDER = ("1", "2", "3A", "3B", "4", "5")
ADULT_AGE = 15


@dataclass(frozen=True)
class Alert:
    level: str
    reason: str


def severity(level: str) -> int:
    """0 pour le tri 1 (le plus grave), 5 pour le tri 5."""
    return LEVEL_ORDER.index(level)


def most_severe(*levels: str) -> str:
    return min(levels, key=severity)


def vital_alerts(vitals: Vitals | None, age_years: float | None) -> list[Alert]:
    if vitals is None:
        return []
    v = vitals
    alerts: list[Alert] = []

    def add(condition: bool, level: str, reason: str) -> None:
        if condition:
            alerts.append(Alert(level, reason))

    if v.spo2 is not None:
        add(v.spo2 < 86, "1", f"SpO2 à {v.spo2} % (< 86 %)")
        add(86 <= v.spo2 <= 90, "2", f"SpO2 à {v.spo2} % (86-90 %)")
    if v.gcs is not None:
        add(v.gcs <= 8, "1", f"score de Glasgow à {v.gcs} (≤ 8)")
        add(9 <= v.gcs <= 13, "2", f"score de Glasgow à {v.gcs} (9-13)")

    if age_years is None or age_years < ADULT_AGE:
        return alerts

    if v.respiratory_rate is not None:
        fr = v.respiratory_rate
        add(fr >= 40, "1", f"FR à {fr}/min (≥ 40/min)")
        add(30 <= fr < 40, "2", f"FR à {fr}/min (30-40/min)")
    if v.systolic_bp is not None:
        pas = v.systolic_bp
        add(pas <= 70, "1", f"PAS à {pas} mmHg (≤ 70 mmHg)")
        add(70 < pas <= 90, "2", f"PAS à {pas} mmHg (≤ 90 mmHg)")
        add(
            90 < pas <= 100 and (v.heart_rate or 0) > 100,
            "2",
            f"PAS à {pas} mmHg avec FC à {v.heart_rate}/min (PAS ≤ 100 et FC > 100)",
        )
        add(pas >= 220, "2", f"PAS à {pas} mmHg (≥ 220 mmHg)")
    if v.heart_rate is not None:
        fc = v.heart_rate
        add(fc >= 180, "1", f"FC à {fc}/min (≥ 180/min)")
        add(130 <= fc < 180, "2", f"FC à {fc}/min (≥ 130/min)")
        add(fc <= 40, "1", f"FC à {fc}/min (≤ 40/min)")
    if v.temperature is not None:
        t = v.temperature
        add(t <= 32, "1", f"température à {t:.1f} °C (≤ 32 °C)")
        add(32 < t <= 35.2, "2", f"température à {t:.1f} °C (≤ 35,2 °C)")
        add(t >= 40, "2", f"température à {t:.1f} °C (≥ 40 °C)")
    return alerts


def vital_floor(vitals: Vitals | None, age_years: float | None) -> Alert | None:
    """L'alerte la plus grave, ou None si les constantes n'imposent rien."""
    alerts = vital_alerts(vitals, age_years)
    return min(alerts, key=lambda a: severity(a.level)) if alerts else None
