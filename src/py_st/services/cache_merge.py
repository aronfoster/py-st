"""Helper for smart cache merging logic."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def smart_merge_cache(
    model_class: type[T],
    cache_entry: dict[str, object] | None,
    fresh_model: T,
    keep_field: str,
    timestamp_field: str,
    fields_to_update: list[str] | None = None,
) -> tuple[T, str | None]:
    """
    Merge fresh API model into cache entry, preserving key field when needed.

    This function handles the common pattern where API responses may lack
    certain fields (e.g., tradeGoods, ships) when queried from a distance,
    but we want to preserve those fields from cache if they exist.

    Args:
        model_class: The Pydantic model class (e.g., Market or Shipyard)
        cache_entry: The current cache entry dict or None if cache miss
        fresh_model: Fresh model fetched from API
        keep_field: Field name to preserve if fresh model has None
                   (e.g., "tradeGoods", "ships")
        timestamp_field: Timestamp field name in cache entry
                        (e.g., "prices_updated", "ships_updated")
        fields_to_update: List of field names to update from fresh model.
                         If None, updates all fields except keep_field.

    Returns:
        Tuple of (final_model, timestamp_str | None):
        - final_model: The model to return and save to cache
        - timestamp_str: ISO timestamp when keep_field was last updated,
                        or None if keep_field is None
    """
    # Check if fresh model has the key field populated
    fresh_field_value = getattr(fresh_model, keep_field, None)

    # Case 1: Fresh model has the key field - use it entirely
    if fresh_field_value is not None:
        new_timestamp = datetime.now(UTC).isoformat()
        logging.debug(
            f"Fresh {model_class.__name__} has {keep_field}, "
            f"using fresh data"
        )
        return (fresh_model, new_timestamp)

    # Case 2: Fresh model lacks the key field
    # Try to preserve it from cache if available
    if cache_entry:
        try:
            cached_model = model_class.model_validate(cache_entry["data"])
            cached_field_value = getattr(cached_model, keep_field, None)

            # Sub-case 2a: Cache has the key field - merge and preserve
            if cached_field_value is not None:
                # Update specific fields from fresh model
                fresh_dict = fresh_model.model_dump()
                cached_dict = cached_model.model_dump()

                # Determine which fields to update
                if fields_to_update is not None:
                    # Update only specified fields
                    for field_name in fields_to_update:
                        if field_name in fresh_dict:
                            cached_dict[field_name] = fresh_dict[field_name]
                else:
                    # Update all fields except keep_field (backward compat)
                    for field_name, fresh_value in fresh_dict.items():
                        if field_name != keep_field:
                            cached_dict[field_name] = fresh_value

                # Reconstruct merged model
                merged_model = model_class.model_validate(cached_dict)

                # Preserve the original timestamp
                old_timestamp_obj = cache_entry.get(timestamp_field)
                old_timestamp_str: str | None = (
                    old_timestamp_obj
                    if isinstance(old_timestamp_obj, str)
                    else None
                )
                logging.debug(
                    f"Merged {model_class.__name__}: updated fields from "
                    f"fresh data while preserving {keep_field} from cache"
                )
                return (merged_model, old_timestamp_str)

        except Exception as e:
            logging.warning(
                f"Failed to merge cached {model_class.__name__}: {e}"
            )

    # Case 3: No cache or cache lacks the key field
    # Use fresh model as-is with no timestamp
    logging.debug(
        f"Fresh {model_class.__name__} lacks {keep_field} "
        f"and no cached data available"
    )
    return (fresh_model, None)
