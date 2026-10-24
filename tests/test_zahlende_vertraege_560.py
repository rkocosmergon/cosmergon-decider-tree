"""Vertraege, die den Agenten zahlen lassen (2.3.11, cos20 #560, Befund P1 an Shikigon `398a512`).

Bis 2.3.10 nahm der Baum ein Angebot nur nach seiner Art an: einen Tribut mit sich selbst als
Zahler, ein Buendnis mit Kosten je Tick. Jeder Spieler konnte einem solchen Agenten so Energie
abnehmen. Dieselbe Regel wie Shikigon ``brain/contracts.py:_kind_costs``. Gegenprobe: gegen
2.3.10 rot am Verhalten (``accept_contract`` statt ``reject_contract``).
"""

from __future__ import annotations

from typing import Any

import pytest
from cosmergon_agent.state import GameState

from cosmergon_decider_tree.decider import TreeDecider

ICH = "7d28a494-9365-4411-8c5e-3e16a7fc7de0"
ANDERER = "995a179c-1656-4d69-814c-cc34b06c2422"
# Die Schreibweisen, die der Server als dieselbe Kennung liest (``uuid.UUID``).
MEINE_SCHREIBWEISEN = (
    ICH,
    ICH.upper(),
    ICH.replace("-", ""),
    "{" + ICH + "}",
    "urn:uuid:" + ICH,
)
# Personas, die die Art nach ihrer Tabelle annehmen (``PERSONA_CONTRACT_BIAS``).
NEHMEN_TRIBUT = ("warrior", "trader", "diplomat", "expansionist")
NEHMEN_BUENDNIS = ("scientist", "warrior", "diplomat")


def _zustand(persona: str, art: str, terms: Any) -> GameState:
    """Ein Zustand auf dem echten Weg des SDK (``GameState.from_api``), ein Angebot im Eingang."""
    return GameState.from_api(
        {
            "agent_id": ICH,
            "persona_type": persona,
            "energy_balance": 50_000.0,
            "contracts": {
                "pending_inbound": [
                    {
                        "contract_id": "k1",
                        "contract_type": art,
                        "from_player_id": ANDERER,
                        "terms": terms,
                    }
                ]
            },
        }
    )


async def _zug(persona: str, art: str, terms: Any) -> tuple[str, dict[str, Any]]:
    return await TreeDecider().decide(_zustand(persona, art, terms))


@pytest.mark.asyncio
@pytest.mark.parametrize("persona", NEHMEN_TRIBUT)
@pytest.mark.parametrize("zahler", MEINE_SCHREIBWEISEN)
async def test_tribut_mit_mir_als_zahler_wird_abgelehnt(persona: str, zahler: str) -> None:
    """K1: in jeder Schreibweise der eigenen Kennung."""
    terms = {"payer_id": zahler, "amount_per_tick": 50}
    assert await _zug(persona, "tribute", terms) == ("reject_contract", {"contract_id": "k1"})


@pytest.mark.asyncio
@pytest.mark.parametrize("terms", [{}, {"payer_id": None}, {"payer_id": "nobody"}, "x", None])
async def test_tribut_ohne_lesbaren_zahler_wird_abgelehnt(terms: Any) -> None:
    """Wer zahlt, ist nicht zu lesen: wie ein Tribut, den der Agent zahlt."""
    assert await _zug("diplomat", "tribute", terms) == ("reject_contract", {"contract_id": "k1"})


@pytest.mark.asyncio
@pytest.mark.parametrize("persona", NEHMEN_BUENDNIS)
@pytest.mark.parametrize("kosten", [5, 0.5, "5", "many", float("nan"), True, [1]])
async def test_buendnis_mit_kosten_wird_abgelehnt(persona: str, kosten: Any) -> None:
    """K2: Kosten je Tick, auch unlesbare."""
    terms = {"cost_per_tick": kosten}
    assert await _zug(persona, "alliance", terms) == ("reject_contract", {"contract_id": "k1"})


@pytest.mark.asyncio
@pytest.mark.parametrize("persona", NEHMEN_TRIBUT)
async def test_tribut_den_der_andere_zahlt_wird_angenommen(persona: str) -> None:
    """K3: das gewoehnliche Spiel bleibt."""
    terms = {"payer_id": ANDERER, "amount_per_tick": 50}
    assert await _zug(persona, "tribute", terms) == (
        "accept_contract",
        {"contract_id": "k1", "escrow_amount": 0.0},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("persona", NEHMEN_BUENDNIS)
@pytest.mark.parametrize("terms", [{}, {"cost_per_tick": 0}, {"cost_per_tick": None}, None])
async def test_kostenloses_buendnis_wird_angenommen(persona: str, terms: Any) -> None:
    assert await _zug(persona, "alliance", terms) == (
        "accept_contract",
        {"contract_id": "k1", "escrow_amount": 0.0},
    )
