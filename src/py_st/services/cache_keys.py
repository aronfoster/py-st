"""
Helper functions for generating consistent cache keys.

These functions ensure cache key naming remains consistent across all
services and prevent typos in hard-coded strings.
"""

from __future__ import annotations


def key_for_agent() -> str:
    """
    Returns the cache key for agent information.

    Returns:
        str: The cache key "agent_info"
    """
    return "agent_info"


def key_for_ship_list() -> str:
    """
    Returns the cache key for the ship list.

    Returns:
        str: The cache key "ship_list"
    """
    return "ship_list"


def key_for_contract_list() -> str:
    """
    Returns the cache key for the contract list.

    Returns:
        str: The cache key "contract_list"
    """
    return "contract_list"


def key_for_waypoints(system_symbol: str) -> str:
    """
    Returns the cache key for waypoints in a system.

    Args:
        system_symbol: The system symbol (e.g., "X1-ABC")

    Returns:
        str: The cache key "waypoints_{system_symbol}"
    """
    return f"waypoints_{system_symbol}"


def key_for_market(waypoint_symbol: str) -> str:
    """
    Returns the cache key for market data at a waypoint.

    Args:
        waypoint_symbol: The waypoint symbol (e.g., "X1-ABC-1")

    Returns:
        str: The cache key "market_{waypoint_symbol}"
    """
    return f"market_{waypoint_symbol}"


def key_for_shipyard(waypoint_symbol: str) -> str:
    """
    Returns the cache key for shipyard data at a waypoint.

    Args:
        waypoint_symbol: The waypoint symbol (e.g., "X1-ABC-1")

    Returns:
        str: The cache key "shipyard_{waypoint_symbol}"
    """
    return f"shipyard_{waypoint_symbol}"
