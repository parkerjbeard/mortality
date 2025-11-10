from __future__ import annotations

"""Name generation utilities.

Implements the Adjective–Object–NN scheme, optimized for easy visual scan and
memorability. Output uses kebab-case and a two-digit suffix.

Pattern: `adjective-object-##`

The implementation is deterministic for a given integer index so experiments
can reproduce names across runs without global random state.
"""

from typing import List, Tuple

_ADJECTIVES: List[str] = [
    # Punchy, concrete, and visually distinct word shapes.
    "brisk",
    "mellow",
    "tart",
    "lithe",
    "sable",
    "crisp",
    "vivid",
    "blunt",
    "bright",
    "calm",
    "clear",
    "daring",
    "deep",
    "eager",
    "even",
    "feral",
    "gleam",
    "granite",
    "hushed",
    "keen",
    "lucid",
    "neat",
    "nimble",
    "plain",
    "plush",
    "prime",
    "quick",
    "quiet",
    "raw",
    "round",
    "sharp",
    "sleek",
    "solid",
    "spry",
    "stark",
    "still",
    "suave",
    "tame",
    "tawny",
    "tidy",
    "tonal",
    "true",
    "uniform",
    "velvet",
    "warm",
    "wary",
    "zesty",
]

_OBJECTS: List[str] = [
    # Concrete, neutral objects with distinct letterforms; avoid animals/people.
    "anchor",
    "apex",
    "beacon",
    "blade",
    "branch",
    "brick",
    "bridge",
    "cable",
    "chisel",
    "cinder",
    "cipher",
    "compass",
    "cradle",
    "dial",
    "echo",
    "filament",
    "flint",
    "fuse",
    "gasket",
    "gear",
    "hinge",
    "kernel",
    "knob",
    "lantern",
    "ledger",
    "lever",
    "lumen",
    "matrix",
    "module",
    "needle",
    "notch",
    "orb",
    "parcel",
    "peg",
    "piston",
    "plinth",
    "prism",
    "pulley",
    "relay",
    "rivet",
    "rod",
    "socket",
    "spindle",
    "spring",
    "stencil",
    "strand",
    "tile",
    "token",
    "valve",
    "vector",
    "vertex",
    "vessel",
    "visor",
]


def adjective_object_nn_for_index(index: int) -> Tuple[str, str]:
    """Return (display_name, agent_id) for `index` using Adjective–Object–NN.

    The mapping is stable across runs. The two-digit suffix cycles from 00–99.

    Example: ("brisk-vertex-04", "brisk-vertex-04")
    """

    if index < 0:
        index = abs(index)
    adj = _ADJECTIVES[index % len(_ADJECTIVES)]
    obj = _OBJECTS[index % len(_OBJECTS)]
    suffix = f"{index % 100:02d}"
    name = f"{adj}-{obj}-{suffix}"
    # For now agent_id is the same kebab-case string; kept for symmetry.
    return name, name


__all__ = ["adjective_object_nn_for_index"]

