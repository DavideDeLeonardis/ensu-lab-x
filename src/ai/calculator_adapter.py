"""
The ONLY file in src/ai/ that imports the real src/lab/calculator.py.
Everything else in this package depends on ports.CalculatorPort, not on this
module directly, so if the real calculator's interface ever changes, this
is the one place to update.

Usage (once this package lives inside the real repo, run from repo root):

    from src.ai.calculator_adapter import RealCalculator
    calc = RealCalculator()
"""
from __future__ import annotations

try:
    from src.lab import calculator as _calc
except ImportError:
    _calc = None  # allows this file to be imported (e.g. for type-checking)
                  # even outside the real repo; RealCalculator() will raise
                  # a clear error if actually used without it.


class RealCalculator:
    def __init__(self):
        if _calc is None:
            raise ImportError(
                "src.lab.calculator not found -- run from the repo root, "
                "with data/equipment.csv, data/grid_intensity.csv and "
                "data/bookings.csv present."
            )

    def estimate(self, equipment_id, start, end, shelves=1, warmup=True):
        return _calc.estimate(equipment_id, start, end, shelves, warmup)

    def saving(self, booking_id, new_start=None, new_end=None, new_equipment=None,
               cancel=False, warmup=True):
        return _calc.saving(booking_id, new_start, new_end, new_equipment, cancel, warmup)
