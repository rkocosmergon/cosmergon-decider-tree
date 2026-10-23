"""Eine Fassung, drei Stellen: ``pyproject.toml``, ``__version__`` und ``TreeDecider.version``.

Bei 2.3.10 stand ``__init__.py`` noch auf 2.3.9, gefunden erst in der Checkliste vor dem
Hochladen (cos20 #492, Pflichtenheft-SDK §7.1 „Version synchron"). Dieser Test macht daraus
ein Gate statt einer Gedaechtnisleistung.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import cosmergon_decider_tree
from cosmergon_decider_tree import TreeDecider

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_die_fassung_steht_an_allen_drei_stellen_gleich() -> None:
    declared = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
    assert cosmergon_decider_tree.__version__ == declared
    assert TreeDecider().version == declared
