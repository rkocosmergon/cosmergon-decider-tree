# cosmergon-decider-tree

Rule-based tree decider for Cosmergon api-agents — deterministic, no
inference, latency well under 10 ms.

Implements the `Decider` protocol from `cosmergon-agent` 0.13.0+.
The branch logic follows Cosmergon's default decision tree for api-agents; the
thresholds are inspired by the conditional sequences of `cosmergon-pet`.

## Architektur

```
state (GameState)
   │
   ├─ persona = state.persona_type or "scientist"
   ▼
PERSONA_TREES[persona]   (list of (condition, action_fn) tuples)
   │
   ├─ first matching condition wins
   ▼
(action, params)           ← optional Compass-Modulation
```

Sechs Persona-Bäume (scientist / warrior / expansionist / trader /
diplomat / farmer), gemeinsamer Survival-Header (critical-energy → wait,
0-fields → create_field, empty-field → place_cells block) und
gemeinsamer Wachstums-Fallback (fewest-cells, wait).

## Usage

```python
from cosmergon_decider_tree import TreeDecider

decider = TreeDecider()  # no config — fully deterministic

# In runner-loop:
async with CosmergonAgent(api_key=..., base_url="https://cosmergon.com") as agent:
    while True:
        await agent.refresh_state()
        action, params = await decider.decide(agent.state)
        await agent.act(action, **params)
        await asyncio.sleep(90)
```

## Vorteile

- **Deterministisch:** identischer State → identische Action.
- **Schnell:** <10 ms pro `decide()`-Call (lambda-evaluation, kein
  Modell-Load).
- **Interpretierbar:** Branch-Liste ist lesbar, Debug-fähig.
- **Offline-fähig:** kein LLM-Provider, kein Modell-File, läuft auf
  jedem ARM-Linux mit Python 3.10+.

## Begrenzung

- **Lernt nicht:** Cosmergon-Mechanik-Änderungen (neue Action-Klassen,
  geänderte Konditions-Schwellen) brechen Tree → klare Versions-Bindung
  an SDK + Backend-Stand.
- **Persona-Bäume teils ähnlich:** Konzept §3.2 hat das adressiert,
  Differenzierung muss strukturiert sichtbar sein.

## Tests

```bash
cd research/decider-cluster/decider-tree
pip install -e '.[dev]'
pytest -q
```
