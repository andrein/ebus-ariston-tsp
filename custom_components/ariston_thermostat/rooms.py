"""The room temperature reported for a house whose rooms each have their own thermostat."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Room:
    current: float | None
    target: float | None
    heating: bool


def reported_temperature(rooms: list[Room], target: float | None, frost: float | None) -> float | None:
    """The zone target less the largest room deficit, or None when no room has a temperature.

    The boiler compares this with the zone target, so the neediest room alone decides the heat request and, with the
    room sensor in the thermoregulation, how much the flow temperature rises.
    """
    if target is None:
        return None
    measured = [room for room in rooms if room.current is not None]
    if not measured:
        return None
    if frost is not None and target <= frost:
        # Zone off or holiday: the boiler protects the house against frost, which needs the real temperature.
        return min(room.current for room in measured)
    deficits = [room.target - room.current for room in measured if room.heating and room.target is not None]
    if not deficits:
        # Every room is off: nothing needs heat.
        return target
    return target - max(deficits)
