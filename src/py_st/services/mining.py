"""Pure, spec-limited diagnostics for unsurveyed ore extraction."""

from datetime import datetime
from typing import Any


def diagnose_mining(
    ship: dict[str, Any], waypoint: dict[str, Any], *, now: datetime
) -> dict[str, Any]:
    """Inspect supplied snapshots only; never authorize an extraction."""
    blockers: list[str] = []
    unknowns: list[str] = []
    warnings: list[str] = []
    nav = ship.get("nav", {})
    if not isinstance(nav, dict):
        nav = {}
    if not nav.get("waypointSymbol") or not waypoint.get("symbol"):
        unknowns.append("Ship/waypoint location is missing")
    elif nav["waypointSymbol"] != waypoint["symbol"]:
        blockers.append("Ship is not at the supplied waypoint")
    status = nav.get("status")
    if status in ("DOCKED", "IN_TRANSIT"):
        blockers.append("Extraction requires IN_ORBIT")
    elif status != "IN_ORBIT":
        unknowns.append("Orbit status is unknown")

    waypoint_type = waypoint.get("type")
    extractability = (
        "documented_example"
        if waypoint_type == "ASTEROID_FIELD"
        else "unknown"
    )
    if extractability == "unknown":
        unknowns.append(
            f"Extractability of {waypoint_type!r} is not established: "
            "the spec has no exhaustive type/trait eligibility matrix"
        )
    mounts = ship.get("mounts")
    if not isinstance(mounts, list) or any(
        not isinstance(mount, dict)
        or not isinstance(mount.get("symbol"), str)
        or not mount["symbol"].strip()
        for mount in mounts
    ):
        unknowns.append("Installed mount evidence is missing or incomplete")
    elif not any(
        mount.get("symbol")
        in (
            "MOUNT_MINING_LASER_I",
            "MOUNT_MINING_LASER_II",
            "MOUNT_MINING_LASER_III",
        )
        for mount in mounts
    ):
        blockers.append("No installed Mining Laser for ore extraction")

    cargo = ship.get("cargo", {})
    if not isinstance(cargo, dict):
        cargo = {}
    capacity, units = cargo.get("capacity"), cargo.get("units")
    free_cargo = None
    if type(capacity) is int and type(units) is int and 0 <= units <= capacity:
        free_cargo = capacity - units
        if free_cargo == 0:
            blockers.append("No free cargo capacity to store extracted ore")
    else:
        unknowns.append("Cargo capacity/units are missing or inconsistent")

    cooldown = ship.get("cooldown", {})
    if not isinstance(cooldown, dict):
        cooldown = {}
    remaining = cooldown.get("remainingSeconds")
    if type(remaining) is not int or remaining < 0:
        unknowns.append("Cooldown remainingSeconds is missing or invalid")
    elif remaining > 0:
        blockers.append("Snapshot reports an active cooldown")
    expiration = cooldown.get("expiration")
    if expiration is not None:
        try:
            expires = datetime.fromisoformat(expiration)
            if expires.utcoffset() is None or now.utcoffset() is None:
                raise ValueError("Timezone required")
        except (TypeError, ValueError):
            unknowns.append("Cooldown comparison needs valid timezone dates")
        else:
            if expires > now and remaining == 0:
                unknowns.append(
                    "Cooldown expiration conflicts with zero remainingSeconds"
                )
            elif expires <= now and type(remaining) is int and remaining > 0:
                unknowns.append(
                    "Cooldown expiration conflicts with positive "
                    "remainingSeconds"
                )

    traits = waypoint.get("traits", [])
    modifiers = waypoint.get("modifiers", [])
    stripped = False
    for field, items in (("traits", traits), ("modifiers", modifiers)):
        if not isinstance(items, list):
            unknowns.append(f"Waypoint {field} evidence is malformed")
            continue
        for item in items:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("symbol"), str)
                or not item["symbol"].strip()
            ):
                unknowns.append(f"Waypoint {field} evidence is incomplete")
                continue
            if item["symbol"] == "STRIPPED":
                stripped = True
    if stripped:
        warnings.append(
            "STRIPPED is a depletion warning, not proof of a non-extractable "
            "waypoint, zero yield, or a particular server error"
        )
    unknowns.append(
        "Installed equipment crew/power operability is not established; "
        "the spec supplies no complete runtime allocation rule"
    )
    return {
        "ship": ship.get("symbol"),
        "waypoint": waypoint.get("symbol"),
        "waypoint_type": waypoint_type,
        "mode": "unsurveyed ore extraction",
        "extractability": extractability,
        "free_cargo": free_cargo,
        "cooldown": cooldown,
        "traits": traits,
        "modifiers": modifiers,
        "blockers": blockers,
        "unknowns": unknowns,
        "warnings": warnings,
        "assessment": "blocked" if blockers else "unknown",
        "execution_authorized": False,
        "note": "No survey or Surveyor is required for this diagnosis. "
        "Resource traits do not guarantee a particular ore, yield or profit. "
        "Full cargo proves no storage space, not a specific API rejection. "
        "Snapshots cannot establish the prior owner's failure without the "
        "original request and error payload. Server acceptance is untested.",
    }
