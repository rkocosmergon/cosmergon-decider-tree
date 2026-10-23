"""Fremde Formen in den Fakten des Servers (2.3.10, cos20 #492, sechster Durchgang an Shikigon).

Das SDK reicht ``available_actions`` ungeprueft weiter. Bis 2.3.9 beendete ein Wort, eine Liste
oder ein Ziel ohne ``field_id`` an der falschen Stelle den Aufrufer (``int(stock)``,
``ziele[0]["field_id"]``, ``.get`` auf einem Wort), bei Shikigon das Gehirn bei jedem Zug. Und
``ready_fields`` kostete Felder x startbare Felder. Gegenprobe: gegen 2.3.9 rot am Verhalten
(eine Ausnahme statt eines Zugs, eine Zeitgrenze gerissen).
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import pytest
from cosmergon_agent.state import GameState

from cosmergon_decider_tree import decider as d
from cosmergon_decider_tree.decider import TreeDecider

# Was eine Welt an die Stelle einer Zahl, einer Liste oder eines Objekts setzen kann.
FREMD: list[Any] = ["many", [1], [[1]], {"x": 1}, 7, True, float("nan"), float("inf"), None]
PERSONAS = ("scientist", "trader", "warrior", "diplomat", "farmer", "expansionist")
FELD = {"id": "f1", "cube_id": "c1", "z_position": 0, "active_cell_count": 4, "entity_tier": 1}


def _fakten_varianten() -> list[Any]:
    """``available_actions`` in jeder Form, die die Fakten einer Welt annehmen koennen."""
    varianten: list[Any] = [[1], "x", 5]
    for wert in FREMD:
        varianten.append(
            {
                "market_buy": {"available": True, "preset_stock": wert},
                "start_mission": {
                    "available": True,
                    "marauder_state": wert,
                    "mega_bombs": wert,
                    "ready_fields": wert,
                    "richest_loot_field": wert,
                },
                "claim_field": {"targets": wert},
                "market_list": {
                    "available": True,
                    "sellable_energy": wert,
                    "open_energy_listings": wert,
                    "sellable_items": {"mega_bomb": wert},
                    "reference_prices": {"mega_bomb": wert},
                },
                "create_field": {"next_cost": wert, "can_afford": True},
            }
        )
        varianten.append({name: wert for name in ("market_buy", "start_mission", "claim_field")})
    varianten.append({"claim_field": {"targets": [1, "x", {"no": "id"}, [2]]}})
    return varianten


def _zustand(fakten: Any, *, energy: float, felder: bool, persona: str) -> GameState:
    """Ein Zustand auf dem echten Weg des SDK (``GameState.from_api``), nicht als Attrappe."""
    return GameState.from_api(
        {
            "agent_id": "a1",
            "persona_type": persona,
            "energy_balance": energy,
            "fields": [FELD] if felder else [],
            "available_actions": fakten,
            "contracts": {
                "pending_inbound": [
                    {"contract_id": "k1", "contract_type": ["alliance"]},
                    {"contract_id": ["k2"], "contract_type": "alliance"},
                ]
            },
        }
    )


@pytest.mark.asyncio
async def test_jede_fremde_form_der_fakten_ergibt_einen_zug() -> None:
    fehler = []
    for fakten in _fakten_varianten():
        for persona in PERSONAS:
            for energy in (150.0, 50_000.0):  # in der Subsistenz und darueber
                for felder in (False, True):
                    state = _zustand(fakten, energy=energy, felder=felder, persona=persona)
                    try:
                        action, params = await TreeDecider().decide(state)
                    except Exception as exc:  # noqa: BLE001 - gesammelt, dann gemeldet
                        fehler.append((repr(fakten)[:80], persona, energy, felder, repr(exc)))
                        continue
                    assert isinstance(action, str) and isinstance(params, dict)
    assert not fehler, fehler[:5]


def _attrappe(fakten: Any, *, energy: float = 150.0, felder: list[Any] | None = None) -> Any:
    return SimpleNamespace(
        persona_type="warrior",
        energy=energy,
        fields=felder or [],
        universe_cubes=[],
        reachable_cubes=[],
        available_actions=fakten,
        pending_contracts=(),
        world_briefing=SimpleNamespace(market=SimpleNamespace(buyable=[]), contract_targets=[]),
        compass_preset=None,
    )


@pytest.mark.parametrize("fakten", _fakten_varianten(), ids=lambda f: repr(f)[:40])
def test_jede_lesestelle_der_fakten_haelt_fremde_formen(fakten: Any) -> None:
    """Jede Stelle, die ``available_actions`` liest, einzeln: keine wirft."""
    feld = SimpleNamespace(id="f1", active_cell_count=4, entity_tier=1)
    for felder in ([], [feld]):
        state = _attrappe(fakten, felder=felder)
        d._kauf_absichten(state)
        d._feldlos_eroberungs_zug(state)
        d._bereite_felder(state, felder)
        d._market_list_plan(state)
        d._can_afford_field(state)
        d._next_field_cost(state)
        d._start_mission_moeglich(state)
        d._server_verneint(state, "start_mission")
        d.resolve_action_params(state, "start_mission", "warrior")


def test_bereite_felder_kostet_nicht_felder_mal_startbare() -> None:
    """20.000 eigene Felder, 20.000 startbare: einmal die Menge, nicht 20.000-mal."""
    felder = [SimpleNamespace(id=f"f{i}") for i in range(20_000)]
    state = _attrappe({"start_mission": {"ready_fields": [f"f{i}" for i in range(20_000)]}})
    begonnen = time.monotonic()
    bereit = d._bereite_felder(state, felder)
    dauer = time.monotonic() - begonnen
    assert len(bereit) == 20_000
    assert dauer < 1.0, f"{dauer:.1f} s"


def test_bereite_felder_bleibt_wie_es_war() -> None:
    """Regression: nur genannte Felder, eine fehlende Liste laesst alle."""
    felder = [SimpleNamespace(id="a"), SimpleNamespace(id="b")]
    assert d._bereite_felder(_attrappe({"start_mission": {"ready_fields": ["b"]}}), felder) == [
        felder[1]
    ]
    assert d._bereite_felder(_attrappe({"start_mission": {}}), felder) == felder
