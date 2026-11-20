"""2.4.0 (cos20 #749) — der Baum lernt aus der eigenen Erfahrung, wenn man ihm einen Speicher gibt.

- Ohne Speicher entscheidet er bit-identisch (der Lern-Term ist leer, der Kompass unverändert).
- Mit Speicher geht der Vorsprung der Zugarten als vierte, additive Bias-Schicht in die Bewertung.
- ``observe`` legt die Wirkung eines Zuges in den Speicher (``ObservingDecider`` des SDK).
- Mit einem SDK ohne ``experience`` bleibt alles wie in 2.3.x.

Die zwei Tests, die den Speicher des SDK brauchen, überspringen sich auf einem SDK ohne
``cosmergon_agent.experience``; die übrigen laufen auf jedem SDK ab 0.19.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from cosmergon_decider_tree import decider as baum
from cosmergon_decider_tree.decider import TreeDecider

pytestmark = pytest.mark.asyncio


def _state(**kw: Any) -> Any:
    feld = SimpleNamespace(
        id="44444444-4444-4444-4444-444444444444",
        active_cell_count=5,
        entity_tier=1,
        reife_score=0,
        entity_type="still_life",
    )
    return SimpleNamespace(
        persona_type=kw.get("persona", "scientist"),
        energy=kw.get("energy", 10_000),
        fields=[feld],
        universe_cubes=[],
        available_actions={},
        world_briefing=SimpleNamespace(market=SimpleNamespace(buyable=[]), contract_targets=[]),
        compass_preset=None,
        tournament=None,
    )


class _Speicher:
    def __init__(self, vorteil: dict[str, tuple[float, float]]) -> None:
        self.vorteil = vorteil
        self.gebucht: list[tuple[str, str, float]] = []

    def record(self, action: str, situation: str, value: float, *, later: bool = False) -> None:
        self.gebucht.append((action, situation, value))

    def advantage(self, situation: str) -> dict[str, tuple[float, float]]:
        return self.vorteil


async def _modifikator(decider: TreeDecider, state: Any, monkeypatch: pytest.MonkeyPatch) -> dict:
    gesehen: dict = {}

    def _spion(state, persona, pool, goal, bias_map, compass_modifier, blocked):  # noqa: ANN001, ANN202
        gesehen.update(compass_modifier)
        return {}

    monkeypatch.setattr(baum, "_score_pool", _spion)
    await decider.decide(state)
    return gesehen


async def test_ohne_speicher_bleibt_der_kompass_unveraendert(monkeypatch) -> None:
    alt = await _modifikator(TreeDecider(), _state(), monkeypatch)
    assert alt == baum.COMPASS_BIAS.get("autonomous", {})


async def test_mit_speicher_geht_der_vorsprung_in_die_bewertung(monkeypatch) -> None:
    pytest.importorskip("cosmergon_agent.experience")
    speicher = _Speicher({"market_list": (500.0, 50.0), "transfer_energy": (-500.0, 50.0)})
    mod = await _modifikator(TreeDecider(store=speicher), _state(), monkeypatch)
    kompass = baum.COMPASS_BIAS.get("autonomous", {})
    assert mod["market_list"] - kompass.get("market_list", 0.0) > 0.1
    assert mod["transfer_energy"] - kompass.get("transfer_energy", 0.0) < -0.1


async def test_entscheidung_ohne_speicher_wie_bisher() -> None:
    state = _state()
    assert await TreeDecider().decide(state) == await TreeDecider(store=None).decide(state)


async def test_observe_legt_die_wirkung_in_den_speicher(tmp_path) -> None:
    experience = pytest.importorskip("cosmergon_agent.experience")
    from cosmergon_agent.action import ActionResult
    from cosmergon_agent.decider import ObservingDecider

    FileExperienceStore = experience.FileExperienceStore  # noqa: N806
    speicher = FileExperienceStore(tmp_path / "e.json")
    decider = TreeDecider(store=speicher)
    ergebnis = ActionResult(
        success=True,
        action="transfer_energy",
        data={"result": {}, "energy_effect": {"free": -300.0, "held": 0.0, "items": 0.0}},
    )

    await decider.observe(_state(), "transfer_energy", {}, ergebnis)

    assert isinstance(decider, ObservingDecider)
    assert speicher.advantage("field|world")["transfer_energy"] == pytest.approx((-300.0, 1.0))


async def test_altes_sdk_ohne_experience_entscheidet_wie_bisher(monkeypatch) -> None:
    speicher = _Speicher({"market_list": (500.0, 50.0), "transfer_energy": (-500.0, 50.0)})
    monkeypatch.setitem(sys.modules, "cosmergon_agent.experience", None)
    mod = await _modifikator(TreeDecider(store=speicher), _state(), monkeypatch)
    assert mod == baum.COMPASS_BIAS.get("autonomous", {})
