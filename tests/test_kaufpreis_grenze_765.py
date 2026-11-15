"""Der Kauf-Kern kauft nur bis zum Hauspreis (2.3.14, cos20 #765, Betreuer-Durchgang Shikigon
`c6f552f`, B6).

Bis 2.3.13 nahm der Baum das billigste Angebot einer gewollten Art bis zur ganzen Energie des
Agenten: das einzige Angebot der Art, von einem anderen Spieler, bekam so alles. Der Server nennt
seit cos20 #765 je Art den Hauspreis (``market_buy.house_prices``); eine Art, die dort fehlt, wird
nicht gekauft, ein Server ohne das Feld bleibt beim Verhalten von 2.3.13. Gegenprobe: gegen 2.3.13
rot sind die Tests 1, 4, 5 und 7 (Kennzeichnung ``[rot an 2.3.13]``).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from cosmergon_decider_tree.decider import (
    TreeDecider,
    _predict_delta,
    is_valid,
    resolve_action_params,
)

HAUSPREIS = 200.0
ENERGIE = 10_000.0
FELD = SimpleNamespace(id="f1", entity_tier=1)


def _angebot(listing_id: str, preis: float, art: str = "preset") -> Any:
    return SimpleNamespace(listing_id=listing_id, item_type=art, price_energy=preis)


def _zustand(angebote: list[Any], markt: dict[str, Any] | None, *, vorrat: int | None = 0) -> Any:
    """Diplomat mit eigenem Feld und leerer Saat-Kammer: die Absicht ``preset`` ist da.

    ``markt`` ist der Block ``market_buy`` ohne ``preset_stock``; ``vorrat=None`` laesst
    ``preset_stock`` weg (aelterer Server, Altzweig)."""
    block: dict[str, Any] = dict(markt or {})
    if vorrat is not None:
        block["preset_stock"] = vorrat
    return SimpleNamespace(
        persona_type="diplomat",
        energy=ENERGIE,
        fields=[FELD],
        universe_cubes=[],
        available_actions={"market_buy": block},
        world_briefing=SimpleNamespace(
            market=SimpleNamespace(buyable=angebote), contract_targets=[]
        ),
        compass_preset=None,
    )


def _liste(zustand: Any) -> str | None:
    params = resolve_action_params(zustand, "market_buy", "diplomat")
    return params.get("listing_id")


@pytest.mark.asyncio
async def test_einziges_angebot_weit_ueber_dem_hauspreis_wird_nicht_gekauft() -> None:
    """1 [rot an 2.3.13]: der Preis ist fast die ganze Energie, der Hauspreis ein Bruchteil."""
    z = _zustand([_angebot("fremd", ENERGIE - 1)], {"house_prices": {"preset": HAUSPREIS}})
    assert is_valid(z, "market_buy") is False
    assert _liste(z) is None
    assert _predict_delta(z, "market_buy", {}) == {}
    aktion, _ = await TreeDecider().decide(z)
    assert aktion != "market_buy"


@pytest.mark.asyncio
async def test_angebot_bis_zum_hauspreis_wird_wie_bisher_gekauft() -> None:
    """2: genau am Hauspreis ist es noch ein Kauf, in allen drei Eingaengen."""
    z = _zustand([_angebot("haus", HAUSPREIS)], {"house_prices": {"preset": HAUSPREIS}})
    assert is_valid(z, "market_buy") is True
    assert _liste(z) == "haus"
    assert _predict_delta(z, "market_buy", {})["energy"] == -HAUSPREIS
    aktion, params = await TreeDecider().decide(z)
    if aktion == "market_buy":
        assert params == {"listing_id": "haus"}


def test_ein_angebot_ueber_und_eines_unter_dem_hauspreis_nimmt_das_untere() -> None:
    """3: das teurere steht zuerst und ist billiger als die Energie, gekauft wird das untere."""
    z = _zustand(
        [_angebot("teuer", 9_000.0), _angebot("recht", 150.0)],
        {"house_prices": {"preset": HAUSPREIS}},
    )
    assert _liste(z) == "recht"


def test_art_die_im_feld_fehlt_wird_nicht_gekauft() -> None:
    """4 [rot an 2.3.13]: das Haus bietet die Art nicht an (oder mit Preis 0, unlesbar)."""
    for preise in ({}, {"mega_bomb": 900.0}, {"preset": 0}, {"preset": "x"}, {"preset": None}):
        z = _zustand([_angebot("billig", 1.0)], {"house_prices": preise})
        assert is_valid(z, "market_buy") is False, preise
        assert _liste(z) is None, preise


@pytest.mark.parametrize("wert", ["preset", ["preset"], [200], 200, None, True])
def test_feld_das_kein_objekt_ist_kauft_nichts(wert: Any) -> None:
    """5 [rot an 2.3.13]: ein Wort oder eine Liste dort ist „Feld da, kein Preis“, keine Ausnahme."""
    z = _zustand([_angebot("billig", 1.0)], {"house_prices": wert})
    assert is_valid(z, "market_buy") is False
    assert _liste(z) is None
    assert _predict_delta(z, "market_buy", {}) == {}


def test_ohne_das_feld_wie_2_3_13() -> None:
    """6: ein aelterer Server nennt es nicht, der Kauf bleibt durchlaessig (auch zum Wucherpreis)."""
    z = _zustand([_angebot("fremd", ENERGIE - 1)], None)
    assert is_valid(z, "market_buy") is True
    assert _liste(z) == "fremd"
    assert _predict_delta(z, "market_buy", {})["energy"] == -(ENERGIE - 1)


def test_altzweig_ohne_preset_stock_hat_dieselbe_grenze() -> None:
    """7 [rot an 2.3.13]: ``preset_stock`` fehlt (Legacy-Typ-Filter), das Feld ist da."""
    teuer = _zustand(
        [_angebot("fremd", ENERGIE - 1)], {"house_prices": {"preset": HAUSPREIS}}, vorrat=None
    )
    assert is_valid(teuer, "market_buy") is False
    assert _liste(teuer) is None
    fehlt = _zustand([_angebot("billig", 1.0)], {"house_prices": {}}, vorrat=None)
    assert is_valid(fehlt, "market_buy") is False
    wort = _zustand([_angebot("billig", 1.0)], {"house_prices": "x"}, vorrat=None)
    assert is_valid(wort, "market_buy") is False
    ok = _zustand([_angebot("haus", 150.0)], {"house_prices": {"preset": HAUSPREIS}}, vorrat=None)
    assert is_valid(ok, "market_buy") is True
    assert _liste(ok) == "haus"
