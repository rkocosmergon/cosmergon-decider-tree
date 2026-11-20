# cosmergon-decider-tree

**The part that decides, without a model.**

An agent in [Cosmergon](https://cosmergon.com) is asked for a move again and again: plant cells,
buy on the market, build up a field, or wait. This package gives it one in under 10 ms, from rules
you can read: no inference, no key, no bill. It is what a
[Shikigon](https://github.com/rkocosmergon/shikigon) and the terminal of
[`cosmergon-agent`](https://github.com/rkocosmergon/cosmergon-agent) play with when no model is
advising them.

```python
from cosmergon_decider_tree import TreeDecider
action, params = await TreeDecider().decide(state)
```

Six characters (scientist, warrior, expansionist, trader, diplomat, farmer), one compass you can
turn, and since 2.4.2 it builds up its fields when the world offers that.

It is fun, it is easy, and it never sends you a bill.

## Install

```bash
pip install cosmergon-decider-tree
```

It implements the `Decider` protocol of `cosmergon-agent` 0.13.0 and later.

## How it decides

```
state (GameState)
   │
   ├─ persona = state.persona_type or "scientist"
   ▼
PERSONA_TREES[persona]   (list of (condition, action_fn) tuples)
   │
   ├─ first matching condition wins
   ▼
(action, params)           ← optionally turned by the compass
```

Six persona trees share a survival header (critical energy: wait; no field: create one; an empty
field: plant cells) and a growth fallback (the field with the fewest cells, then wait).

## In a loop

```python
import asyncio

from cosmergon_agent import CosmergonAgent
from cosmergon_decider_tree import TreeDecider

decider = TreeDecider()  # no configuration: fully deterministic


async def main() -> None:
    async with CosmergonAgent(api_key=..., base_url="https://cosmergon.com") as agent:
        while True:
            await agent.refresh_state()
            action, params = await decider.decide(agent.state)
            await agent.act(action, **params)
            await asyncio.sleep(90)


asyncio.run(main())
```

## What it is good at

- **Deterministic.** The same state gives the same move.
- **Fast.** Under 10 ms per `decide()`: conditions are evaluated, no model is loaded.
- **Readable.** The branches are a list you can read and debug.
- **Offline.** No model provider and no model file; it runs on any ARM Linux with Python 3.10
  or later.

## Its limits

- **It follows the world's rules as they were when it was written.** A new kind of action or a
  changed threshold in Cosmergon needs a new version of this package; each version is bound to a
  state of the SDK and of the world.
- **Some persona trees are alike.** They differ in what they prefer, less in what they can do.

## Tests

```bash
pip install -e '.[dev]'
pytest -q
```
