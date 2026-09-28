"""Tests des TreeDecider-Kerns (SOURCE OF TRUTH; Vendor-Kopie: cosmergon-pet).

S298-Rueck-Sync: Testsatz aus dem Pet-Vendor uebernommen (Tree-pure Teile;
Loop-/Backoff-/run_pet-Tests leben beim Pet, weil tree_loop dort wohnt).

Verifies:
  - TreeDecider produces an action from a minimal GameState
  - Personas pick different first-actions on the same state
  - tree_decision_loop calls agent.act when given a non-wait action
  - Mutual-exclusion check at run_pet level (llm_provider XOR tree_decider)
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from cosmergon_decider_tree.decider import VALID_ACTIONS, TreeDecider


def _make_state(
    *,
    persona: str = "scientist",
    energy: float = 10_000,
    fields: list[Any] | None = None,
    cubes: list[Any] | None = None,
    available_actions: dict[str, dict[str, Any]] | None = None,
    compass: str | None = None,
) -> Any:
    """Lightweight GameState surrogate — duck-typed for the tree's getattr-paths."""
    return SimpleNamespace(
        persona_type=persona,
        energy=energy,
        fields=fields or [],
        universe_cubes=cubes or [],
        available_actions=available_actions or {},
        world_briefing=SimpleNamespace(
            market=SimpleNamespace(buyable=[]),
            contract_targets=[],
        ),
        compass_preset=compass,
    )


def _comet_hand_lage(**overrides: Any) -> dict[str, dict[str, Any]]:
    """Die ECHTEN Server-Fakten des S308-Live-Falls (24.08., v1.64.150):
    feldlos, solvent, Marauder recovery, 0 Bomben, reichstes Loot-Feld
    belegt, market_list verfuegbar — und kein freier Bauplatz."""
    fakten: dict[str, dict[str, Any]] = {
        "start_mission": {
            "available": True,
            "marauder_state": "recovery",
            "mega_bombs": 0,
            "richest_loot_field": {
                "field_id": "a7cb9d65-b959-48bc-a2f6-76b073f57dc8",
                "bomb_boxes": 14,
            },
        },
        "market_list": {
            "available": True,
            "sellable_energy": 365.95,
            "sellable_items": {},
        },
        "create_field": {"can_afford": True, "next_cost": 500.0, "available": False},
    }
    fakten.update(overrides)
    return fakten


@pytest.mark.asyncio
async def test_solventer_feldloser_nimmt_die_kette() -> None:
    """S308 Comet-hand-Repro — rot gegen v2.2.3.

    Der 0.9-Sonderfall hing an ``kind == "energy_at_least"`` (Subsistenz).
    Ein SOLVENTER Feldloser (scientist, Guthaben 11.449 >> Schwelle 2.000,
    Ziel ``field_count_at_least``) bekam fuer start_mission 0.0 und verlor
    0.20:0.15 gegen market_list (explore-Kompass) — minuetliches Listing
    statt Rueckkehr ins Spiel. Feldlos + Fakten muss die Kette gewinnen.
    """
    state = _make_state(
        energy=11_449,
        fields=[],
        cubes=[],  # volle Welt: kein Bauplatz
        available_actions=_comet_hand_lage(),
        compass="explore",
    )
    action, params = await TreeDecider().decide(state)
    assert action == "start_mission"
    assert params["params"]["mission_type"] == "gather_spores"


@pytest.mark.asyncio
async def test_freier_slot_schlaegt_erobern_trotz_kette() -> None:
    """Ueberkorrektur-Waechter: die Founder-Ordnung (S307, 0.9 < create_field)
    bleibt. Ist ein Bauplatz frei UND bezahlbar, schweigt der
    Ketten-Sonderfall strukturell — create_field gewinnt, obwohl die
    Landweg-Fakten vollstaendig vorliegen."""
    cube = SimpleNamespace(id="11111111-1111-1111-1111-111111111111")
    state = _make_state(
        energy=11_449,
        fields=[],
        cubes=[cube],  # freier Bauplatz
        # v2.3.2: der Server meldet den freien Platz auch (available =
        # can_afford UND Slot frei) — die Lage-Fixture sagt "kein Bauplatz".
        available_actions=_comet_hand_lage(
            create_field={"can_afford": True, "next_cost": 500.0, "available": True}
        ),
        compass="explore",
    )
    action, params = await TreeDecider().decide(state)
    assert action == "create_field"
    assert params["cube_id"] == str(cube.id)


@pytest.mark.asyncio
async def test_decider_returns_valid_action() -> None:
    state = _make_state()
    decider = TreeDecider()
    action, params = await decider.decide(state)
    assert action in VALID_ACTIONS
    assert isinstance(params, dict)


@pytest.mark.asyncio
async def test_decider_critical_energy_waits() -> None:
    state = _make_state(energy=10)  # below CRITICAL_ENERGY (100)
    decider = TreeDecider()
    action, _ = await decider.decide(state)
    assert action == "wait"


@pytest.mark.asyncio
async def test_decider_zero_fields_can_afford_creates_field() -> None:
    cube = SimpleNamespace(id="11111111-1111-1111-1111-111111111111")
    state = _make_state(
        energy=10_000,
        fields=[],
        cubes=[cube],
        available_actions={"create_field": {"can_afford": True}},
    )
    decider = TreeDecider()
    action, params = await decider.decide(state)
    assert action == "create_field"
    assert params["cube_id"] == str(cube.id)


@pytest.mark.asyncio
async def test_decider_unknown_persona_falls_back_to_scientist() -> None:
    state = _make_state(persona="some-future-persona", energy=10_000)
    decider = TreeDecider()
    action, _ = await decider.decide(state)
    assert action in VALID_ACTIONS  # scientist tree → always-valid action


def _ml_actions(
    *, available: bool, energy: float = 0.0, items: dict | None = None
) -> dict[str, dict[str, Any]]:
    return {
        "market_list": {
            "available": available,
            "sellable_energy": energy,
            "sellable_items": items or {},
        }
    }


@pytest.mark.asyncio
async def test_market_list_respektiert_server_nein() -> None:
    """Server sagt available=false (kein Ueberschuss, kein Inventar) —
    der Baum darf market_list NICHT waehlen (v2.0.2 tat es: energy>=1500)."""
    from cosmergon_decider_tree.decider import is_valid

    state = _make_state(energy=9_953, available_actions=_ml_actions(available=False))
    assert is_valid(state, "market_list") is False
    action, _ = await TreeDecider().decide(state)
    assert action != "market_list"


def test_market_list_energie_bei_ueberschuss() -> None:
    """Server meldet verkaeufliche Energie → klassisches Energie-Listing."""
    from cosmergon_decider_tree.decider import _market_list_plan

    state = _make_state(
        energy=20_000,
        available_actions=_ml_actions(available=True, energy=2_500),
    )
    plan = _market_list_plan(state)
    assert plan == {"price_energy": 450}  # scientist


def test_market_list_item_mit_marktreferenz() -> None:
    """Kein Ueberschuss, aber gedecktes Inventar: 1 Item zu 95 % des
    billigsten aktiven Listings desselben Typs."""
    from cosmergon_decider_tree.decider import _market_list_plan

    state = _make_state(
        energy=9_953,
        available_actions=_ml_actions(available=True, items={"mega_bomb": 7}),
    )
    state.world_briefing.market.buyable = [
        SimpleNamespace(item_type="mega_bomb", price_energy=100_000.0),
        SimpleNamespace(item_type="mega_bomb", price_energy=120_000.0),
    ]
    plan = _market_list_plan(state)
    assert plan == {
        "item_type": "mega_bomb",
        "item_data": {"count": 1},
        "price_energy": 95_000,
    }


def test_market_list_item_ohne_referenzpreis_wird_nicht_gelistet() -> None:
    """Ohne Vergleichspreis am Markt wird nicht geraten — kein Listing."""
    from cosmergon_decider_tree.decider import _market_list_plan

    state = _make_state(
        energy=9_953,
        available_actions=_ml_actions(available=True, items={"bus_ticket_x": 1}),
    )
    assert _market_list_plan(state) is None


def test_market_list_alter_server_fallback() -> None:
    """Backend ohne sellable_*-Schluessel: altes Verhalten (Schwelle 1500)."""
    from cosmergon_decider_tree.decider import _market_list_plan

    state = _make_state(energy=9_953, available_actions={})
    assert _market_list_plan(state) == {"price_energy": 450}


def test_start_mission_ohne_selbstbelohnung_und_ohne_none_ids() -> None:
    """reward_energy muss 0 sein (S278-Tor) und params duerfen keine
    None-UUIDs tragen; feldlos + cubelos ⇒ kein Kandidat."""
    from cosmergon_decider_tree.decider import is_valid, resolve_action_params

    mit_feld = _make_state(fields=[SimpleNamespace(id="33333333-3333-3333-3333-333333333333")])
    # v2.2.2: Draht-Form — mission_type/reward_energy reisen IM params-Sub-Dict
    # (ActionRequest kennt sie nicht flach; Pydantic verwarf sie still -> 422).
    aussen = resolve_action_params(mit_feld, "start_mission", "warrior")
    assert set(aussen.keys()) == {"params"}
    inner = aussen["params"]
    assert inner["reward_energy"] == 0
    assert inner["params"]["field_id"] == "33333333-3333-3333-3333-333333333333"

    feldlos = _make_state(fields=[], cubes=[])
    assert resolve_action_params(feldlos, "start_mission", "warrior") == {}
    assert is_valid(feldlos, "start_mission") is False


@pytest.mark.asyncio
async def test_decide_respektiert_blocked() -> None:
    """Eine gesperrte Aktion wird nicht gewaehlt — der Baum nimmt die
    naechstbeste statt zu haemmern."""
    field = SimpleNamespace(
        id="44444444-4444-4444-4444-444444444444",
        active_cell_count=5,
        entity_tier=1,
        reife_score=0,
        entity_type="still_life",
    )
    state = _make_state(energy=10_000, fields=[field])
    decider = TreeDecider()
    frei, _ = await decider.decide(state)
    geblockt, _ = await decider.decide(state, blocked=frozenset({frei}))
    assert geblockt != frei


def test_market_list_item_mit_server_referenzpreis() -> None:
    """Backend >= v1.64.31 liefert reference_prices — die gewinnen gegen das
    Briefing (das nur die 20 billigsten Listings traegt und mega_bomb nie)."""
    from cosmergon_decider_tree.decider import _market_list_plan

    actions = _ml_actions(available=True, items={"mega_bomb": 7})
    actions["market_list"]["reference_prices"] = {"mega_bomb": 100_000.0}
    state = _make_state(energy=9_953, available_actions=actions)
    # Briefing bewusst leer — der Serverpreis muss reichen.
    plan = _market_list_plan(state)
    assert plan == {
        "item_type": "mega_bomb",
        "item_data": {"count": 1},
        "price_energy": 95_000,
    }


def test_propose_contract_nur_backend_typen_mit_pflicht_terms() -> None:
    """Jede Persona sendet einen Vertragstyp, den das Backend kennt, mit
    vollstaendigen Pflicht-Terms.

    S298: der Baum erfand "research_agreement" (existiert im Backend nicht,
    validate_terms -> "Unknown contract type" -> HTTP 400) und sandte
    trade_agreement ohne den Pflicht-Term fee_discount_pct (dieselbe 400).
    Referenz abgeschrieben aus dem Backend (models/contract.py:CONTRACT_TYPES,
    Free-Tier-Teilmenge agent_game.py:_FREE_CONTRACT_TYPES) — der Pet ist ein
    free-Agent und darf nur diese Typen proponieren.
    """
    from cosmergon_decider_tree.decider import resolve_action_params

    free_types_required_terms = {
        "non_aggression": {"duration"},
        "trade_agreement": {"fee_discount_pct", "duration"},
    }
    target = SimpleNamespace(player_id="55555555-5555-5555-5555-555555555555")
    personas = [
        "scientist",
        "trader",
        "warrior",
        "diplomat",
        "farmer",
        "expansionist",
        "some-future-persona",
    ]
    for persona in personas:
        state = _make_state(persona=persona)
        state.world_briefing.contract_targets = [target]
        params = resolve_action_params(state, "propose_contract", persona)
        ctype = params["contract_type"]
        assert ctype in free_types_required_terms, (
            f"{persona}: '{ctype}' ist kein free-tier-proponierbarer Backend-Typ"
        )
        missing = free_types_required_terms[ctype] - set(params["terms"])
        assert not missing, f"{persona}/{ctype}: fehlende Pflicht-Terms {missing}"
        assert params["to_player_id"] == "55555555-5555-5555-5555-555555555555"


def test_propose_from_template_params_genestet_und_free_tier() -> None:
    """template_id/mode/slots muessen im params-Sub-Dict reisen (das SDK legt
    act()-kwargs flach in den Body, ActionRequest kennt sie nicht -> 422),
    und nur Free-Tier-Templates T07/T08 (T09/T06 rendern zu alliance/tribute,
    die 402-Klasse des direkten propose_contract-Wegs). S298 am Live-Fall
    Comet-hand: 3x 422 direkt nach dem v2.1.1-Deploy."""
    from cosmergon_decider_tree.decider import resolve_action_params

    required_slots = {
        "T08_NON_AGGRESSION": {"partner_id", "duration"},
        "T07_TRADE_AGREEMENT": {"partner_id", "fee_discount_pct", "duration"},
    }
    target = SimpleNamespace(player_id="66666666-6666-6666-6666-666666666666")
    for persona in ["scientist", "trader", "warrior", "diplomat", "farmer", "expansionist"]:
        state = _make_state(persona=persona)
        state.world_briefing.contract_targets = [target]
        out = resolve_action_params(state, "propose_from_template", persona)
        assert set(out) == {"params", "escrow_amount"}, f"{persona}: {set(out)}"
        inner = out["params"]
        tid = inner["template_id"]
        assert tid in required_slots, f"{persona}: {tid} ist kein Free-Tier-Template"
        missing = required_slots[tid] - set(inner["slots"])
        assert not missing, f"{persona}/{tid}: fehlende Slots {missing}"
        assert inner["mode"] == "targeted"


# --- v2.3.1 Kaufabsicht (S308, Live-Fall Socket-hand) ------------------------


def _preset_listing(price: float = 10.0) -> Any:
    return SimpleNamespace(listing_id="p1", item_type="preset", price_energy=price)


def _bomben_listing(price: float = 900.0) -> Any:
    return SimpleNamespace(listing_id="b1", item_type="mega_bomb", price_energy=price)


def test_voller_vorrat_kein_kauf_karussell_repro() -> None:
    """Der Socket-hand-Repro: diplomat, eigenes Feld, VOLLE Saat-Kammer,
    billiges Haus-Preset — gegen v2.3.0 war das ein garantierter Kauf
    (203 in 24 h). Mit Server-Faktum preset_stock >= 3 endet der Treadmill."""
    from cosmergon_decider_tree.decider import is_valid, resolve_action_params

    state = _make_state(
        persona="diplomat",
        fields=[SimpleNamespace(id="f1", entity_tier=1)],
        available_actions={"market_buy": {"preset_stock": 5}},
    )
    state.world_briefing.market.buyable = [_preset_listing()]
    assert is_valid(state, "market_buy") is False
    assert resolve_action_params(state, "market_buy", "diplomat") == {}


def test_leere_kammer_kauft_preset_nach() -> None:
    from cosmergon_decider_tree.decider import is_valid, resolve_action_params

    state = _make_state(
        persona="diplomat",
        fields=[SimpleNamespace(id="f1", entity_tier=1)],
        available_actions={"market_buy": {"preset_stock": 0}},
    )
    state.world_briefing.market.buyable = [_preset_listing()]
    assert is_valid(state, "market_buy") is True
    assert resolve_action_params(state, "market_buy", "diplomat")["listing_id"] == "p1"


def test_feldloser_mit_zielen_kauft_bomben() -> None:
    """Die Absicht ersetzt den statischen Typ-Filter: ein feldloser diplomat
    DARF die mega_bomb kaufen, wenn die Eroberungs-Kette sie braucht
    (Ziele sichtbar, Arsenal < 3) — der Kauf beschleunigt das Sammeln."""
    from cosmergon_decider_tree.decider import is_valid, resolve_action_params

    state = _make_state(
        persona="diplomat",
        energy=50_000,
        available_actions={
            "market_buy": {"preset_stock": 0},
            "start_mission": {"mega_bombs": 1},
            "claim_field": {"targets": [{"field_id": "z1"}]},
        },
    )
    state.world_briefing.market.buyable = [_bomben_listing()]
    assert is_valid(state, "market_buy") is True
    assert resolve_action_params(state, "market_buy", "diplomat")["listing_id"] == "b1"


def test_volles_arsenal_kauft_keine_bomben() -> None:
    from cosmergon_decider_tree.decider import is_valid

    state = _make_state(
        persona="diplomat",
        energy=50_000,
        available_actions={
            "market_buy": {"preset_stock": 0},
            "start_mission": {"mega_bombs": 3},
            "claim_field": {"targets": [{"field_id": "z1"}]},
        },
    )
    state.world_briefing.market.buyable = [_bomben_listing()]
    # Feldlos ohne eigenes Feld: preset-Absicht entfaellt (kein Feld),
    # Bomben-Absicht entfaellt (Arsenal voll) -> kein Kauf.
    assert is_valid(state, "market_buy") is False


def test_ohne_server_faktum_bleibt_legacy_verhalten() -> None:
    """Aelterer Server (kein market_buy.preset_stock): der Legacy-Typ-Filter
    traegt weiter — diplomat darf preset kaufen wie in v2.3.0 (durchlaessig,
    Muster marauder_state)."""
    from cosmergon_decider_tree.decider import is_valid

    state = _make_state(
        persona="diplomat",
        fields=[SimpleNamespace(id="f1", entity_tier=1)],
        available_actions={},
    )
    state.world_briefing.market.buyable = [_preset_listing()]
    assert is_valid(state, "market_buy") is True


def test_delta_folgt_demselben_kern() -> None:
    """Gate an einem von zwei Eingaengen ist keines: auch der Score-Delta
    sieht bei voller Kammer KEINEN Kauf (kein Geister-Delta fuer eine
    Aktion, die der Resolver verweigert)."""
    from cosmergon_decider_tree.decider import _predict_delta

    state = _make_state(
        persona="diplomat",
        fields=[SimpleNamespace(id="f1", entity_tier=1)],
        available_actions={"market_buy": {"preset_stock": 5}},
    )
    state.world_briefing.market.buyable = [_preset_listing()]
    assert _predict_delta(state, "market_buy", {}) == {}


# --- v2.3.2 Server-Faktum ``available`` (cosmergon#405, Live-Fall Socket-hand) --


@pytest.mark.asyncio
async def test_laufende_mission_bei_koerper_in_recovery_kein_start() -> None:
    """#405-Repro — rot gegen v2.3.1. Socket-hand 27.09. 19:36Z: Mission
    laeuft, Koerper steht in ``recovery``, der Server sagt
    ``available: false``. Die Nachbildung ``marauder_state != "recovery"``
    liess den Start durch (6 x 409 in 2 h)."""
    from cosmergon_decider_tree.decider import is_valid

    fakten = _comet_hand_lage()
    fakten["start_mission"]["available"] = False
    state = _make_state(energy=11_449, available_actions=fakten, compass="explore")

    assert is_valid(state, "start_mission") is False
    action, _ = await TreeDecider().decide(state)
    assert action != "start_mission"


def test_ohne_available_bleibt_start_durchlaessig() -> None:
    """Aelterer Server ohne ``available``: keine Sperre aus dem Fehlen."""
    from cosmergon_decider_tree.decider import is_valid

    fakten = _comet_hand_lage()
    del fakten["start_mission"]["available"]
    state = _make_state(energy=11_449, available_actions=fakten)
    assert is_valid(state, "start_mission") is True
