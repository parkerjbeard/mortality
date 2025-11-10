"""Utilities for exposing Mortality state over the Model Context Protocol.

Diaries are private; the shared bus only exposes explicit broadcast snippets.
"""

from .bus import BroadcastResource, BroadcastScope, SharedMCPBus

__all__ = [
    "BroadcastResource",
    "BroadcastScope",
    "SharedMCPBus",
]
