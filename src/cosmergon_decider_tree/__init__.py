"""cosmergon-decider-tree — rule-based decision tree for Cosmergon api-agents.

Implements the SDK 0.13.0 Decider protocol with deterministic rule-based
logic — no inference, no model. Mirrors the Pet's S165 conditional
persona-sequences but in pure Python lambdas, suitable for Lab-Cluster
B.2 baseline (S165) and as a fallback decider when LLM-providers fail.
"""

from __future__ import annotations

from cosmergon_decider_tree.decider import TreeDecider

__version__ = "2.3.4"

__all__ = ["TreeDecider", "__version__"]
