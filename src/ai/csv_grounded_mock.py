"""
A calculator stand-in that's more honest than mock_calculator.py's flat-rate
model: it uses bookings.csv's own cached kwh/kg_low/kg_typ/kg_high columns
as the REAL "before" (current) state -- these are exactly what the real
calculator.py produced when the CSV was generated, so they're not an
approximation at all.

Only the "after" state (what a hypothetical reschedule/share/cancel would
cost) is still approximated, using a per-equipment kg/hour rate derived
from the real data itself (average kg_typ / duration across that
equipment's real bookings), combined with a simple time-of-day multiplier
to give reschedule candidates something real to find.

This only exists because equipment.csv has no data rows yet (see chat) --
once it does, use RealCalculator (calculator_adapter.py) instead, which
needs no approximation at all.
"""
from __future__ import annotations
from datetime import datetime, timedelta

from .domain import Booking, FMT

# Equipment ids whose real energy cost is ~fixed per booking regardless of
# duration (autoclave-style cycles) rather than proportional to hours booked
# -- per README.md: "Autoclave cycles cost 6 kWh regardless of load."
CYCLE_MODE_EQUIPMENT = {"AUT-1"}


def _hour_multiplier(hour: int) -> float:
    if 10 <= hour < 16:
        return 1.3   # peak
    if 16 <= hour < 22:
        return 1.0   # evening
    return 0.6       # overnight / early morning


def derive_rates(bookings: list[Booking]) -> dict[str, float]:
    """Average kg/hour per equipment (or average kg/booking for cycle-mode
    equipment), computed straight from real cached values in bookings.csv."""
    totals: dict[str, list[float]] = {}
    for b in bookings:
        if b.cached_kg_typ is None:
            continue
        hours = max((b.end - b.start).total_seconds() / 3600, 1e-6)
        value = b.cached_kg_typ if b.equipment_id in CYCLE_MODE_EQUIPMENT else b.cached_kg_typ / hours
        totals.setdefault(b.equipment_id, []).append(value)
    return {eq: sum(vals) / len(vals) for eq, vals in totals.items()}


class CsvGroundedMockCalculator:
    def __init__(self, bookings_by_id: dict[str, Booking]):
        self._bookings = bookings_by_id
        self._rates = derive_rates(list(bookings_by_id.values()))

    def _approx_estimate(self, equipment_id, start, end, shelves=1, warmup=True):
        """Only used for hypothetical (not-currently-booked) equipment/time
        combinations -- see module docstring."""
        t0, t1 = datetime.strptime(start, FMT), datetime.strptime(end, FMT)
        rate = self._rates.get(equipment_id, 1.0)
        if equipment_id in CYCLE_MODE_EQUIPMENT:
            kg = rate * _hour_multiplier(t0.hour)
        else:
            kg, t = 0.0, t0
            while t < t1:
                kg += rate * min(1.0, (t1 - t).total_seconds() / 3600) * _hour_multiplier(t.hour)
                t += timedelta(hours=1)
        kwh = round(kg / 0.35, 3)
        return {
            "kwh": kwh,
            "kg": {"low": round(kg * 0.7, 3), "typ": round(kg, 3), "high": round(kg * 1.35, 3)},
            "avg_grid_g_per_kwh": round(kg / kwh * 1000, 1) if kwh else None,
        }

    def estimate(self, equipment_id, start, end, shelves=1, warmup=True):
        # If this exactly matches a real booking's own current slot, use the
        # real cached numbers instead of approximating.
        for b in self._bookings.values():
            if (b.equipment_id == equipment_id and b.start.strftime(FMT) == start
                    and b.end.strftime(FMT) == end and b.cached_kg_typ is not None):
                return {
                    "kwh": b.cached_kwh,
                    "kg": {"low": b.cached_kg_low, "typ": b.cached_kg_typ, "high": b.cached_kg_high},
                    "avg_grid_g_per_kwh": None,
                }
        return self._approx_estimate(equipment_id, start, end, shelves, warmup)

    def saving(self, booking_id, new_start=None, new_end=None, new_equipment=None,
               cancel=False, warmup=True):
        b = self._bookings[booking_id]
        before = self.estimate(b.equipment_id, b.start.strftime(FMT), b.end.strftime(FMT), b.shelves or 1)
        if cancel:
            after = {"kwh": 0.0, "kg": {"low": 0.0, "typ": 0.0, "high": 0.0}, "avg_grid_g_per_kwh": None}
        else:
            after = self.estimate(
                new_equipment or b.equipment_id,
                new_start or b.start.strftime(FMT),
                new_end or b.end.strftime(FMT),
                b.shelves or 1,
                warmup=warmup,
            )
        saving_kg = {k: round(before["kg"][k] - after["kg"][k], 3) for k in ("low", "typ", "high")}
        saving_pct = round((1 - after["kg"]["typ"] / before["kg"]["typ"]) * 100, 1) if before["kg"]["typ"] else 0
        return {
            "booking_id": booking_id,
            "before": before,
            "after": after,
            "saving_kwh": round(before["kwh"] - after["kwh"], 3),
            "saving_kg": saving_kg,
            "saving_pct": saving_pct,
        }
