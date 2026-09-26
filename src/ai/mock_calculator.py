"""
A fake calculator matching the REAL src/lab/calculator.py's exact
input/output shape (see ports.py) -- same before/after saving() pattern,
same nested dict shape -- so swapping in RealCalculator later is a true
one-line change and these tests don't quietly drift from reality.

Models a simple time-of-day multiplier (peak/evening/overnight) on top of a
flat kg/hour rate per equipment, so reschedule candidates have something
real to find -- still not real data, just enough variation to meaningfully
exercise ranking.py/build.py's logic across all three candidate types.
"""
from __future__ import annotations
from datetime import datetime, timedelta

from .domain import Booking, FMT


def _hour_multiplier(hour: int) -> float:
    if 10 <= hour < 16:
        return 1.3   # peak
    if 16 <= hour < 22:
        return 1.0   # evening
    return 0.6       # overnight / early morning


class MockCalculator:
    def __init__(self, kg_per_hour_by_equipment: dict[str, float], bookings: dict[str, Booking]):
        self._rate = kg_per_hour_by_equipment
        self._bookings = bookings

    def estimate(self, equipment_id, start, end, shelves=1, warmup=True):
        t0 = datetime.strptime(start, FMT)
        t1 = datetime.strptime(end, FMT)
        rate = self._rate.get(equipment_id, 1.0)
        kg = 0.0
        t = t0
        while t < t1:
            step_hours = min(1.0, (t1 - t).total_seconds() / 3600)
            kg += rate * step_hours * _hour_multiplier(t.hour)
            t += timedelta(hours=1)
        kwh = round(kg / 0.35, 3)  # arbitrary illustrative kg/kWh factor
        return {
            "kwh": kwh,
            "kg": {"low": round(kg * 0.7, 3), "typ": round(kg, 3), "high": round(kg * 1.35, 3)},
            "avg_grid_g_per_kwh": round(kg / kwh * 1000, 1) if kwh else None,
        }

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
