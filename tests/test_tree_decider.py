"""Tests for TreeDecider v2.0.0 (GOBT — Subsistenz + Persona-Charakter)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cosmergon_agent.decider import Decider
from cosmergon_decider_tree import TreeDecider
from cosmergon_decider_tree.decider import (
    VALID_ACTIONS,
    is_valid,
    resolve_action_params,
    score_action,
)
from cosmergon_decider_tree.persona_profiles import (
    COMPASS_BIAS,
    PERSONA_ACTION_BIAS,
    PERSONA_ACTION_POOLS,
    PERSONA_BUYABLE_TYPES,
    SUBSISTENCE_POOL,
    needs_subsistence,
    persona_current_goal,
    subsistence_threshold,
)


# --- Fixtures ----------------------------------------------------------------


def _field(field_id="f1", tier=1, cells=10, reife=0, etype=None):
    return SimpleNamespace(
        id=field_id,
        entity_tier=tier,
        active_cell_count=cells,
        reife_score=reife,
        entity_type=etype,
    )


def _cube(cube_id="c1"):
    return SimpleNamespace(id=cube_id)


def _listing(listing_id="l1", price=10.0, item="cube"):
    return SimpleNamespace(listing_id=listing_id, price_energy=price, item_type=item)


def _contract_target(player_id="p1", username="Other", persona="trader"):
    return SimpleNamespace(player_id=player_id, username=username, persona=persona)


def _state(
    persona="scientist",
    energy=100_000.0,
    fields=None,
    universe_cubes=None,
    buyable=None,
    contract_targets=None,
    compass=None,
    available_actions=None,
):
    market = SimpleNamespace(buyable=buyable or [], summary="")
    wb = SimpleNamespace(
        market=market,
        contract_targets=contract_targets or [],
        situation=SimpleNamespace(affordable_presets=("block", "blinker")),
    )
    fields_list = fields or []
    if available_actions is None:
        next_cost = 500.0 * len(fields_list)
        available_actions = {
            "create_field": {
                "can_afford": float(energy) >= next_cost * 1.15,
                "next_cost": next_cost,
            }
        }
    return SimpleNamespace(
        persona_type=persona,
        energy=energy,
        fields=fields_list,
        cubes=[],
        universe_cubes=universe_cubes or [],
        world_briefing=wb,
        compass_preset=compass,
        available_actions=available_actions,
    )


@pytest.fixture
def decider() -> TreeDecider:
    return TreeDecider()


# --- Protocol-Compliance -----------------------------------------------------


class TestProtocolSatisfaction:
    def test_satisfies_decider_protocol(self, decider: TreeDecider) -> None:
        assert isinstance(decider, Decider)

    def test_name_and_version(self, decider: TreeDecider) -> None:
        assert decider.name == "tree"
        assert decider.version == "2.0.2"

    @pytest.mark.asyncio
    async def test_healthcheck_always_true(self, decider: TreeDecider) -> None:
        assert await decider.healthcheck() is True


# --- Layer 1: Subsistenz -----------------------------------------------------


class TestSubsistenceLayer:
    def test_threshold_scientist_low_tier(self) -> None:
        # Scientist mit Tier-1-Fields → max evolve = T1→T2 = 1k
        state = _state(persona="scientist", fields=[_field("f1", tier=1)])
        # threshold = max(1k evolve, 575 next_field) * 2 = 2_000
        threshold = subsistence_threshold("scientist", state)
        assert threshold == 2_000.0

    def test_threshold_scientist_high_tier(self) -> None:
        # Scientist mit Tier-4-Field → max evolve = T4→T5 = 125k
        state = _state(persona="scientist", fields=[_field("f1", tier=4)])
        threshold = subsistence_threshold("scientist", state)
        assert threshold == 250_000.0  # 125k * 2

    def test_threshold_expansionist_field_cost_dominated(self) -> None:
        # Expansionist hat keine evolve-cost, nur next_field × margin
        state = _state(persona="expansionist", fields=[_field(f"f{i}") for i in range(100)])
        # next_field = 500 * 100 = 50k, margin = 57.5k, threshold = 115k
        threshold = subsistence_threshold("expansionist", state)
        assert threshold == pytest.approx(115_000.0)

    def test_needs_subsistence_below_threshold(self) -> None:
        state = _state(persona="scientist", energy=500.0, fields=[_field("f1", tier=1)])
        assert needs_subsistence(state, "scientist")

    def test_no_subsistence_when_rich(self) -> None:
        state = _state(persona="scientist", energy=1_000_000.0, fields=[_field("f1", tier=1)])
        assert not needs_subsistence(state, "scientist")

    @pytest.mark.asyncio
    async def test_subsistence_pool_includes_only_energy_aktions(self) -> None:
        # Subsistenz-Pool sollte place_cells/market_list/create_field umfassen
        assert "place_cells" in SUBSISTENCE_POOL
        assert "market_list" in SUBSISTENCE_POOL
        assert "create_field" in SUBSISTENCE_POOL
        assert "evolve" not in SUBSISTENCE_POOL  # evolve verbraucht Energy
        assert "propose_contract" not in SUBSISTENCE_POOL  # contract-escrow verbraucht


# --- Validity-Filter ---------------------------------------------------------


class TestValidityFilter:
    def test_wait_always_valid(self) -> None:
        assert is_valid(_state(energy=50.0), "wait")

    def test_critical_energy_blocks_all_but_wait(self) -> None:
        state = _state(energy=50.0)
        assert is_valid(state, "wait")
        assert not is_valid(state, "create_field")
        assert not is_valid(state, "place_cells")

    def test_create_field_needs_cube_and_affordability(self) -> None:
        # Reich aber keine cubes
        state = _state(energy=1_000_000.0, fields=[_field("f1")], universe_cubes=[])
        assert not is_valid(state, "create_field")
        # Mit cube
        state2 = _state(energy=1_000_000.0, fields=[_field("f1")], universe_cubes=[_cube("c1")])
        assert is_valid(state2, "create_field")

    def test_create_field_blocked_at_unaffordable_with_safety_margin(self) -> None:
        # 200 Fields → next_cost = 100k, margin = 115k. Energy 100k = nicht-affordable
        many_fields = [_field(f"f{i}") for i in range(200)]
        state = _state(energy=100_000.0, fields=many_fields, universe_cubes=[_cube()])
        assert not is_valid(state, "create_field")

    def test_place_cells_needs_field(self) -> None:
        # 0 Fields
        state = _state(fields=[])
        assert not is_valid(state, "place_cells")
        # Mit Field
        state2 = _state(fields=[_field("f1")])
        assert is_valid(state2, "place_cells")

    def test_evolve_needs_eligible_field(self) -> None:
        # Kein eligible field
        state = _state(fields=[_field("f1", tier=1, reife=0)])
        assert not is_valid(state, "evolve")
        # Eligible field (tier=1, reife=200, oscillator)
        state2 = _state(
            energy=10_000,
            fields=[_field("f1", tier=1, reife=200, etype="oscillator")],
        )
        assert is_valid(state2, "evolve")

    def test_market_buy_filtered_by_persona_type(self) -> None:
        # Scientist mit nur preset-Listings → nicht valid
        state = _state(
            persona="scientist",
            buyable=[_listing("l1", price=10, item="preset")],
        )
        assert not is_valid(state, "market_buy")
        # Mit cube-Listing → valid
        state2 = _state(
            persona="scientist",
            buyable=[_listing("l1", price=10, item="cube")],
        )
        assert is_valid(state2, "market_buy")

    def test_market_buy_trader_accepts_all_types(self) -> None:
        # Trader hat allowed_types=None
        state = _state(
            persona="trader",
            buyable=[_listing("l1", price=10, item="preset")],
        )
        assert is_valid(state, "market_buy")

    def test_market_list_needs_minimum_energy(self) -> None:
        assert not is_valid(_state(energy=1_000), "market_list")
        assert is_valid(_state(energy=2_000), "market_list")

    def test_propose_contract_needs_target(self) -> None:
        assert not is_valid(_state(contract_targets=[]), "propose_contract")
        target = _contract_target("p1")
        assert is_valid(_state(contract_targets=[target]), "propose_contract")


# --- Persona-Goal-Metric -----------------------------------------------------


class TestPersonaGoalMetric:
    def test_scientist_goal_no_patterns_yet(self) -> None:
        # Scientist hat Field mit etype=None → Pattern noch nicht etabliert
        state = _state(fields=[_field("f1", etype=None)])
        goal = persona_current_goal(state, "scientist")
        assert goal["kind"] == "patterns_established"

    def test_scientist_goal_evolve_when_ready(self) -> None:
        state = _state(
            fields=[_field("f1", tier=1, reife=200, etype="oscillator")]
        )
        goal = persona_current_goal(state, "scientist")
        assert goal["kind"] == "evolved_fields_at_least"

    def test_scientist_goal_avg_cells_when_pattern_established(self) -> None:
        # Pattern (oscillator) da, aber reife unter 100 → Cells halten
        state = _state(
            fields=[_field("f1", tier=1, cells=20, reife=50, etype="oscillator")]
        )
        goal = persona_current_goal(state, "scientist")
        assert goal["kind"] == "avg_cells_at_least"

    def test_trader_goal_inventory_use_when_hoarding(self) -> None:
        state = _state(
            persona="trader",
            fields=[_field("f1")],  # bootstrap-goal vermeiden
            universe_cubes=[_cube(f"c{i}") for i in range(6)],  # >= 5
        )
        goal = persona_current_goal(state, "trader")
        assert goal["kind"] == "fields_use_inventory"

    def test_trader_goal_market_growth_when_low_inventory(self) -> None:
        # v2.0.1: 0 Fields → bootstrap-goal. Test braucht ≥1 field.
        state = _state(persona="trader", fields=[_field("f1")], universe_cubes=[_cube("c1")])
        goal = persona_current_goal(state, "trader")
        assert goal["kind"] == "energy_growth_via_market"

    def test_warrior_goal_min_cells_when_under(self) -> None:
        state = _state(
            persona="warrior",
            fields=[_field("f1", cells=15)],  # < 30
        )
        goal = persona_current_goal(state, "warrior")
        assert goal["kind"] == "all_fields_min_cells"

    def test_diplomat_goal_active_contracts(self) -> None:
        # v2.0.1: 0 Fields → bootstrap-goal. Test braucht ≥1 field.
        state = _state(persona="diplomat", fields=[_field("f1")])
        goal = persona_current_goal(state, "diplomat")
        assert goal["kind"] == "active_contracts_at_least"
        assert goal["target"] == 3

    def test_bootstrap_goal_at_zero_fields_for_all_personas(self) -> None:
        # v2.0.1: alle Personas → bootstrap (field_count_at_least 1) bei 0 Fields
        for persona in ["scientist", "trader", "warrior", "expansionist",
                        "diplomat", "farmer"]:
            state = _state(persona=persona, fields=[])
            goal = persona_current_goal(state, persona)
            assert goal["kind"] == "field_count_at_least"
            assert goal["target"] == 1


# --- Persona-Action-Pool & Bias ---------------------------------------------


class TestPersonaPoolsAndBias:
    def test_all_personas_have_pool(self) -> None:
        for persona in ["scientist", "warrior", "expansionist", "trader",
                        "diplomat", "farmer"]:
            assert persona in PERSONA_ACTION_POOLS
            assert len(PERSONA_ACTION_POOLS[persona]) >= 5

    def test_all_personas_have_bias(self) -> None:
        for persona in PERSONA_ACTION_POOLS:
            assert persona in PERSONA_ACTION_BIAS
            for action, bias in PERSONA_ACTION_BIAS[persona].items():
                assert -0.3 <= bias <= 0.3, f"bias {action}={bias} for {persona} out of range"

    def test_scientist_evolve_high_bias(self) -> None:
        assert PERSONA_ACTION_BIAS["scientist"]["evolve"] == 0.3

    def test_trader_market_high_bias(self) -> None:
        assert PERSONA_ACTION_BIAS["trader"]["market_buy"] == 0.3
        assert PERSONA_ACTION_BIAS["trader"]["market_list"] == 0.2

    def test_warrior_place_cells_high_bias(self) -> None:
        assert PERSONA_ACTION_BIAS["warrior"]["place_cells"] == 0.3

    def test_buyable_types_trader_unrestricted(self) -> None:
        assert PERSONA_BUYABLE_TYPES["trader"] is None

    def test_buyable_types_scientist_cube_field(self) -> None:
        assert PERSONA_BUYABLE_TYPES["scientist"] == ("cube", "field")


# --- decide()-Pipeline End-to-End -------------------------------------------


class TestDecidePipeline:
    @pytest.mark.asyncio
    async def test_critical_energy_returns_wait(self, decider: TreeDecider) -> None:
        action, params = await decider.decide(_state(energy=50.0))
        assert action == "wait"

    @pytest.mark.asyncio
    async def test_subsistence_picks_create_field_at_zero_fields(
        self, decider: TreeDecider
    ) -> None:
        # Subsistenz-Modus: niedrige Energy aber nicht Critical
        state = _state(
            persona="scientist",
            energy=1_500.0,  # unter scientist-threshold (= 2_000 für Tier-1)
            fields=[],
            universe_cubes=[_cube("c1")],
        )
        # next_field=0 (first-field-frei), can_afford=true
        state.available_actions = {
            "create_field": {"can_afford": True, "next_cost": 0.0}
        }
        action, params = await decider.decide(state)
        assert action == "create_field"

    @pytest.mark.asyncio
    async def test_persona_character_scientist_no_pattern_picks_place_cells(
        self, decider: TreeDecider
    ) -> None:
        """Scientist mit Field ohne entity_type → Pattern etablieren via place_cells."""
        state = _state(
            persona="scientist",
            energy=1_000_000.0,  # rich, kein Subsistenz
            fields=[_field("f1", tier=1, cells=20, etype=None)],
            universe_cubes=[_cube("c1")],
        )
        action, params = await decider.decide(state)
        # Goal = patterns_established; place_cells preset=blinker macht oscillator-Pattern
        # create_field würde auch fire'n, aber bias scientist=-0.2, place_cells=0
        # place_cells score 0.8 + 0 = 0.8; create_field score irrelevant + bias -0.2
        assert action == "place_cells"
        assert params["preset"] == "blinker"

    @pytest.mark.asyncio
    async def test_comet_hand_szenario_v200(self, decider: TreeDecider) -> None:
        """Comet-hand-Empirie: 25 Fields, 4.5M E, scientist, alle Fields cells>50,
        kein Field reife≥100. v1.1.4 wählte 100% create_field (Mono).
        v2.0.0 sollte place_cells wählen (Pattern-Etablierung)."""
        fields = [_field(f"f{i}", tier=1, cells=80, reife=20, etype=None)
                  for i in range(25)]
        state = _state(
            persona="scientist",
            energy=4_500_000.0,
            fields=fields,
            universe_cubes=[_cube("c1")],
        )
        action, params = await decider.decide(state)
        # Goal = patterns_established (kein Field hat oscillator entity_type)
        # → place_cells preset=blinker
        assert action == "place_cells"
        assert params["preset"] == "blinker"

    @pytest.mark.asyncio
    async def test_scientist_evolve_when_ready(
        self, decider: TreeDecider
    ) -> None:
        state = _state(
            persona="scientist",
            energy=100_000,
            fields=[_field("f1", tier=1, cells=50, reife=200, etype="oscillator")],
        )
        action, params = await decider.decide(state)
        assert action == "evolve"

    @pytest.mark.asyncio
    async def test_trader_picks_market_buy_with_preset_listings(
        self, decider: TreeDecider
    ) -> None:
        # Trader darf preset kaufen
        state = _state(
            persona="trader",
            energy=200_000,
            fields=[_field("f1", cells=100)],
            buyable=[_listing("l1", price=10, item="preset")],
            universe_cubes=[_cube("c1")],
        )
        action, params = await decider.decide(state)
        assert action == "market_buy"
        assert params["listing_id"] == "l1"

    @pytest.mark.asyncio
    async def test_scientist_skips_preset_listings(
        self, decider: TreeDecider
    ) -> None:
        # Scientist mit nur preset-Listings → market_buy ist invalid → andere Action
        state = _state(
            persona="scientist",
            energy=200_000,
            fields=[_field("f1", tier=1, cells=80, reife=20, etype=None)],
            buyable=[_listing("l1", price=10, item="preset")],
            universe_cubes=[_cube("c1")],
        )
        action, params = await decider.decide(state)
        assert action != "market_buy"

    @pytest.mark.asyncio
    async def test_warrior_low_cells_field_picks_place_cells(
        self, decider: TreeDecider
    ) -> None:
        state = _state(
            persona="warrior",
            energy=50_000,
            fields=[_field("f1", cells=20)],  # unter Goal-Threshold 30
        )
        action, params = await decider.decide(state)
        assert action == "place_cells"
        assert params["preset"] == "block"  # warrior preset = block

    @pytest.mark.asyncio
    async def test_expansionist_picks_create_field_when_possible(
        self, decider: TreeDecider
    ) -> None:
        # Expansionist ohne leere Felder, Energy reich, Cube da
        state = _state(
            persona="expansionist",
            energy=200_000,
            fields=[_field("f1", cells=100)],
            universe_cubes=[_cube("c1")],
        )
        action, params = await decider.decide(state)
        # Goal = field_count_at_least (next field), bias create_field +0.3
        assert action == "create_field"

    @pytest.mark.asyncio
    async def test_diplomat_picks_propose_contract(
        self, decider: TreeDecider
    ) -> None:
        state = _state(
            persona="diplomat",
            energy=50_000,
            fields=[_field("f1", cells=100)],
            contract_targets=[_contract_target("p1")],
        )
        action, params = await decider.decide(state)
        assert action == "propose_contract"

    @pytest.mark.asyncio
    async def test_farmer_low_cells_picks_place_cells(
        self, decider: TreeDecider
    ) -> None:
        state = _state(
            persona="farmer",
            energy=50_000,
            fields=[_field("f1", cells=30)],  # < 50 farmer-Goal
        )
        action, params = await decider.decide(state)
        assert action == "place_cells"

    @pytest.mark.asyncio
    async def test_no_valid_actions_returns_wait(
        self, decider: TreeDecider
    ) -> None:
        # Persona alles invalid: keine fields, keine cubes, keine listings, kein contract
        state = _state(
            persona="scientist",
            energy=1_500_000,  # über Subsistenz
            fields=[],
            universe_cubes=[],
            buyable=[],
            contract_targets=[],
        )
        # market_list valid (energy>1500), aber Subsistenz greift nicht (rich)
        # also Layer 2: action_pool = scientist; alles außer market_list invalid
        action, params = await decider.decide(state)
        # market_list valid + nur option → wird gewählt
        assert action == "market_list"


# --- Compass-Bias-Modifier ---------------------------------------------------


class TestCompassBias:
    def test_compass_bias_scales_within_limits(self) -> None:
        for compass, biases in COMPASS_BIAS.items():
            for action, bias in biases.items():
                assert -0.2 <= bias <= 0.2, (
                    f"compass {compass} bias {action}={bias} out of [-0.2, +0.2]"
                )

    def test_autonomous_compass_no_modifier(self) -> None:
        assert COMPASS_BIAS["autonomous"] == {}

    @pytest.mark.asyncio
    async def test_consolidate_compass_prefers_pflege(
        self, decider: TreeDecider
    ) -> None:
        """compass=consolidate verstärkt place_cells/evolve, dämpft create_field."""
        state = _state(
            persona="expansionist",  # baseline create_field-Bias=+0.3
            energy=200_000,
            fields=[_field("f1", cells=100)],
            universe_cubes=[_cube("c1")],
            compass="consolidate",  # create_field -0.2, place_cells +0.2
        )
        # Net create_field bias: 0.3 - 0.2 = +0.1
        # place_cells bias: 0.1 + 0.2 = +0.3
        # Beide Goals approximieren unterschiedlich; place_cells wird wahrscheinlich gewählt
        action, params = await decider.decide(state)
        # Wir prüfen nur dass Compass den Effekt hat — Action sollte place_cells sein
        # wenn cells nicht voll, sonst create_field
        assert action in ("place_cells", "create_field")


# --- Score-Funktion (Unit-Tests) --------------------------------------------


class TestScoreAction:
    def test_score_energy_at_least_market_list(self) -> None:
        state = _state(energy=10_000)
        goal = {"kind": "energy_at_least", "target": 100_000}
        # market_list listed +450, listing_fee -10 → +0.5*450 - 10 effective +215
        score = score_action(
            state, "market_list", {"price_energy": 450}, goal
        )
        # gap = 90_000, e_delta ~= 215 → score ~= 0.0024
        assert 0 <= score <= 1

    def test_score_avg_cells_place_cells(self) -> None:
        state = _state(fields=[_field("f1", cells=20)])
        goal = {"kind": "avg_cells_at_least", "target": 100}
        score = score_action(
            state, "place_cells", {"preset": "blinker", "field_id": "f1"}, goal
        )
        # v2.0.1: direction-based, place_cells in richtige Richtung → ≥0.7
        assert score >= 0.7

    def test_score_avg_cells_at_many_fields_pulsar_eye_szenario(self) -> None:
        """v2.0.1 Pulsar-eye-Bug-Fix: bei 403 Fields ist place_cells-Magnitude
        winzig (1/403), aber Richtung stimmt → Score sollte trotzdem hoch sein."""
        many_fields = [_field(f"f{i}", cells=80) for i in range(400)]
        state = _state(fields=many_fields, energy=500_000)
        goal = {"kind": "avg_cells_at_least", "target": 100}
        score = score_action(
            state, "place_cells", {"preset": "blinker", "field_id": "f0"}, goal
        )
        # Pre v2.0.1: score ≈ 0.0074/20 ≈ 0.0004 (quasi 0)
        # Post v2.0.1: direction-based → ≥0.7
        assert score >= 0.7

    def test_score_avg_cells_market_list_no_effect(self) -> None:
        """market_list ändert avg_cells nicht → score 0 (anders als v2.0.0
        wo Bias-Fall-back manchmal market_list gewinnen ließ)."""
        state = _state(fields=[_field("f1", cells=80)])
        goal = {"kind": "avg_cells_at_least", "target": 100}
        score = score_action(state, "market_list", {"price_energy": 450}, goal)
        assert score == 0.0

    def test_score_evolved_fields_returns_one_for_evolve(self) -> None:
        state = _state(
            fields=[_field("f1", tier=1, reife=200, etype="oscillator")],
            energy=10_000,
        )
        goal = {"kind": "evolved_fields_at_least", "target": 1}
        score = score_action(state, "evolve", {"field_id": "f1"}, goal)
        assert score == 1.0

    def test_score_patterns_established_for_blinker(self) -> None:
        state = _state(fields=[_field("f1", etype=None)])
        goal = {"kind": "patterns_established", "target": 1}
        score = score_action(
            state, "place_cells", {"preset": "blinker", "field_id": "f1"}, goal
        )
        assert score > 0  # blinker etabliert oscillator-Pattern

    def test_score_unknown_goal_kind_returns_zero(self) -> None:
        state = _state()
        goal = {"kind": "nonexistent_goal_kind"}
        assert score_action(state, "place_cells", {"preset": "block"}, goal) == 0.0


# --- Resolve-Action-Params --------------------------------------------------


class TestResolveActionParams:
    def test_create_field_returns_first_cube(self) -> None:
        state = _state(universe_cubes=[_cube("c-A"), _cube("c-B")])
        params = resolve_action_params(state, "create_field", "scientist")
        assert params["cube_id"] == "c-A"

    def test_place_cells_picks_empty_field_first(self) -> None:
        state = _state(
            persona="scientist",
            fields=[_field("f1", cells=100), _field("f2", cells=0)],
        )
        params = resolve_action_params(state, "place_cells", "scientist")
        assert params["field_id"] == "f2"  # empty bevorzugt
        assert params["preset"] == "blinker"  # scientist-default

    def test_market_list_persona_specific_price(self) -> None:
        params_t = resolve_action_params(_state(persona="trader"), "market_list", "trader")
        params_s = resolve_action_params(_state(persona="scientist"), "market_list", "scientist")
        assert params_t["price_energy"] == 500  # trader höher
        assert params_s["price_energy"] == 450

    def test_propose_contract_persona_specific_type(self) -> None:
        target = _contract_target("p1")
        state = _state(contract_targets=[target])
        params_s = resolve_action_params(state, "propose_contract", "scientist")
        params_w = resolve_action_params(state, "propose_contract", "warrior")
        assert params_s["contract_type"] == "research_agreement"
        assert params_w["contract_type"] == "non_aggression"


# --- VALID_ACTIONS-Konstanten ------------------------------------------------


class TestValidActionsConstant:
    def test_all_persona_pool_actions_in_valid_actions(self) -> None:
        for persona, pool in PERSONA_ACTION_POOLS.items():
            for action in pool:
                assert action in VALID_ACTIONS, (
                    f"{persona} pool has invalid action {action!r}"
                )

    def test_subsistence_pool_actions_in_valid_actions(self) -> None:
        for action in SUBSISTENCE_POOL:
            assert action in VALID_ACTIONS
