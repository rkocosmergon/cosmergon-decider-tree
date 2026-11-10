"""cos20 #711 — das Vertragsziel ist erreicht, also kein Höchstwert für weitere Vorschläge.

``active_contracts_at_least`` gab jedem Vorschlag 1,0, auch bei erfülltem Ziel: Vortex-bright
(warrior, Ziel 1) schlug bei 222 aktiven Verträgen 430 weitere am Tag vor, 165 abgelehnt.
Jetzt wie ``field_count_at_least``: Lücke 0 → 0,1.
"""

from __future__ import annotations

from types import SimpleNamespace

from cosmergon_decider_tree.decider import _score_gegen_ziel

ZIEL = {"kind": "active_contracts_at_least", "target": 1}


def _lage(aktiv: int) -> SimpleNamespace:
    return SimpleNamespace(
        persona_type="warrior",
        energy=50_000,
        fields=[],
        universe_cubes=[],
        available_actions={},
        world_briefing=SimpleNamespace(market=SimpleNamespace(buyable=[]), contract_targets=[]),
        active_contracts=tuple({"contract_id": f"c{i}"} for i in range(aktiv)),
    )


def test_erfuelltes_vertragsziel_bewertet_vorschlag_niedrig_711() -> None:
    assert _score_gegen_ziel(_lage(222), "propose_contract", {}, ZIEL) == 0.1


def test_offenes_vertragsziel_bleibt_hoechstwert_711() -> None:
    assert _score_gegen_ziel(_lage(0), "propose_contract", {}, ZIEL) == 1.0
