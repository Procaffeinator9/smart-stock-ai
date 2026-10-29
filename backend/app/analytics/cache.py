"""Per-snapshot memoisation for derived analytics.

Results are stored on the dataset object (``RetailDataset._cache``), so they are dropped
automatically when the repository loads a new snapshot (changed CSV files or a Databricks
refresh). Each namespace is a small LRU, so arbitrary filter combinations cannot grow memory
without bound.
"""

import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any, TypeVar

T = TypeVar("T")

DEFAULT_MAX_ENTRIES = 64

_lock = threading.Lock()


def memoize(
    dataset: Any, namespace: str, key: Hashable, compute: Callable[[], T], max_entries: int = DEFAULT_MAX_ENTRIES
) -> T:
    """``compute()`` once per (namespace, key) for this dataset snapshot.

    The computation runs outside the lock (it is CPU-only), so a slow calculation never blocks
    requests for results that are already cached. Two concurrent first requests for the same key
    may both compute it; the results are identical and the later one wins.
    """
    with _lock:
        entries: OrderedDict = dataset._cache.setdefault(namespace, OrderedDict())
        if key in entries:
            entries.move_to_end(key)
            return entries[key]
    value = compute()
    with _lock:
        entries[key] = value
        entries.move_to_end(key)
        while len(entries) > max_entries:
            entries.popitem(last=False)
    return value
