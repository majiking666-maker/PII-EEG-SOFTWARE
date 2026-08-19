"""
SSVEP target management.

Design constraints locked in project discussion (2026-08-17):
- Only a limited number of distinct flicker frequencies can be reliably
  told apart at once (realistic ceiling ~4-8 simultaneous targets before
  interference/confusion - published SSVEP constraint).
- For screens with more interactive elements than that, use hierarchical
  navigation: first SSVEP-select a broad region/quadrant (few targets),
  then a second step narrows within it - not one giant flickering screen.
- Target positions come from OS accessibility APIs (not computer vision) -
  this module assumes element positions are already known/provided, it
  does not do any screen analysis itself.

This module only handles frequency ASSIGNMENT and hierarchical GROUPING
logic. Actual SSVEP signal detection (matching EEG frequency to a target)
is a separate concern - see core/events.py's SSVEP_TARGET event type,
which this module's output feeds into.
"""

from dataclasses import dataclass, field
from enum import Enum


# Realistic ceiling on simultaneous distinguishable frequencies.
# Conservative default (6) sits within the published 4-8 range.
MAX_SIMULTANEOUS_TARGETS = 6

# A safe, commonly-used SSVEP frequency band (Hz). Real hardware/display
# refresh rate constraints will narrow this further later - these are
# placeholder values for software-layer development.
#
# Note: this is the WHOLE SYSTEM's available frequency set, not a per-screen
# limit. MAX_SIMULTANEOUS_TARGETS below governs how many can flicker at once
# within a single dynamic group - a separate, smaller constraint. The pool
# needs to be large enough to cover permanently-reserved CONFIRM (2) and
# SCROLL (2-4) frequencies from TargetRegistry, with enough left over for
# dynamic targets to still be useful.
DEFAULT_FREQUENCY_POOL = [8.0, 10.0, 12.0, 15.0, 17.0, 20.0, 23.0, 26.0, 29.0, 33.0]


@dataclass
class UIElement:
    """A single interactive element on screen, as reported by the OS
    accessibility API (position/bounds are illustrative - real integration
    will use whatever format the platform API provides)."""
    element_id: str
    label: str
    x: float
    y: float
    width: float
    height: float


@dataclass
class SSVEPTarget:
    """A UI element with an assigned flicker frequency, ready for display."""
    element: UIElement
    frequency: float


@dataclass
class TargetGroup:
    """
    One 'screen' of simultaneously-flickering targets. If there are more
    elements than MAX_SIMULTANEOUS_TARGETS, elements are split into
    multiple groups (quadrants/regions), navigated hierarchically.
    """
    targets: list[SSVEPTarget] = field(default_factory=list)
    group_label: str = ""


def assign_frequencies(elements: list[UIElement], frequency_pool: list[float] = None) -> list[SSVEPTarget]:
    """
    Assigns one frequency per element from the pool. Raises if there are
    more elements than available frequencies - caller should have already
    grouped elements via `group_into_regions` first if needed.
    """
    pool = frequency_pool or DEFAULT_FREQUENCY_POOL
    if len(elements) > len(pool):
        raise ValueError(
            f"Cannot assign unique frequencies to {len(elements)} elements "
            f"with only {len(pool)} frequencies available. "
            f"Group elements into regions first (see group_into_regions)."
        )
    return [SSVEPTarget(element=el, frequency=freq) for el, freq in zip(elements, pool)]


def group_into_regions(
    elements: list[UIElement],
    screen_width: float,
    screen_height: float,
    max_per_group: int = MAX_SIMULTANEOUS_TARGETS,
) -> list[TargetGroup]:
    """
    Splits elements into a grid of regions (quadrants, or finer if needed)
    such that no single group exceeds max_per_group elements. This is what
    powers the hierarchical "select a region, then select within it" flow
    for screens with too many elements to flicker all at once.

    Simple, deterministic spatial grid approach for now (not adaptive
    clustering) - good enough for the software-flow layer; can be refined
    later without changing the interface other modules depend on.
    """
    if len(elements) <= max_per_group:
        return [TargetGroup(targets=[], group_label="single_group")]  # caller assigns frequencies directly

    # Determine grid size needed (e.g. 2x2=4 regions, 3x3=9, etc.)
    import math
    n_elements = len(elements)
    n_regions_needed = math.ceil(n_elements / max_per_group)
    grid_dim = math.ceil(math.sqrt(n_regions_needed))

    region_width = screen_width / grid_dim
    region_height = screen_height / grid_dim

    groups: dict[tuple[int, int], list[UIElement]] = {}
    for el in elements:
        col = min(int(el.x // region_width), grid_dim - 1)
        row = min(int(el.y // region_height), grid_dim - 1)
        groups.setdefault((row, col), []).append(el)

    result = []
    for (row, col), els in sorted(groups.items()):
        # If a region still has too many elements, this simple grid isn't
        # fine enough - caller should recurse with a smaller sub-region.
        # Flagged clearly rather than silently truncating.
        if len(els) > max_per_group:
            raise ValueError(
                f"Region ({row},{col}) has {len(els)} elements, exceeding "
                f"max_per_group={max_per_group}. Increase grid_dim or "
                f"recurse into sub-regions for this area."
            )
        result.append(TargetGroup(targets=[], group_label=f"region_{row}_{col}"))
        result[-1].targets = [SSVEPTarget(element=el, frequency=0.0) for el in els]  # frequency assigned next step

    return result


def prepare_screen(
    elements: list[UIElement],
    screen_width: float,
    screen_height: float,
    frequency_pool: list[float] = None,
) -> list[TargetGroup]:
    """
    Full pipeline: given raw UI elements from the accessibility API, produce
    one or more TargetGroups, each with frequencies assigned and ready for
    display. If elements fit in one group, returns a single group. If not,
    returns multiple regional groups for hierarchical navigation.
    """
    pool = frequency_pool or DEFAULT_FREQUENCY_POOL

    if len(elements) <= len(pool):
        targets = assign_frequencies(elements, pool)
        return [TargetGroup(targets=targets, group_label="single_group")]

    groups = group_into_regions(elements, screen_width, screen_height, max_per_group=len(pool))
    for group in groups:
        raw_elements = [t.element for t in group.targets]
        group.targets = assign_frequencies(raw_elements, pool)
    return groups


# =========================================================================
# Target Registry (added 2026-08-19, per Grok Note 10/11 priority #3)
#
# Extends the above single-screen logic to handle multiple simultaneous
# CATEGORIES of SSVEP targets that can be on-screen together, each needing
# its own reserved frequencies so they never collide:
#   - CONFIRM targets (yes_target/no_target) - used by core/confirm.py,
#     must always be available with a stable, reserved frequency pair.
#   - SCROLL targets (scrollbar up/down markers, possibly slow/fast tiers)
#     - per design_decisions.md, these are "always-visible" alongside
#       whatever else is on screen, so they need permanently reserved
#       frequencies distinct from the dynamic grid pool.
#   - UI_GRID / KEYBOARD targets - the dynamic, per-screen pool from
#     prepare_screen() above (general UI elements, keyboard letter groups,
#     prediction bar entries, etc.) - these can reuse the same frequencies
#     across different screens since they're never on-screen at the same
#     time as each other, but must never overlap with the reserved
#     CONFIRM/SCROLL frequencies.
# =========================================================================

class TargetCategory(Enum):
    CONFIRM = "confirm"
    SCROLL = "scroll"
    DYNAMIC = "dynamic"  # UI grid, keyboard groups, predictions, etc.


class TargetRegistry:
    """
    Central authority for frequency allocation across all SSVEP target
    categories, so CONFIRM and SCROLL always have stable reserved
    frequencies, and DYNAMIC (grid/keyboard) targets only ever draw from
    what's left over - never colliding with the reserved ones.

    One registry instance should be created per app session (or per
    device profile) and reused everywhere targets are assigned, rather
    than each feature picking its own frequencies independently.
    """

    def __init__(self, full_pool: list[float] = None):
        self.full_pool = list(full_pool or DEFAULT_FREQUENCY_POOL)

        if len(self.full_pool) < 4:
            raise ValueError(
                "TargetRegistry needs at least 4 frequencies: 2 reserved "
                "for CONFIRM, at least 2 reserved for SCROLL, and "
                "something left over for DYNAMIC targets."
            )

        # Reserve the first two frequencies permanently for confirm (yes/no).
        # These must never change during a session - core/confirm.py's
        # SSVEP_FALLBACK mode depends on a stable yes_target/no_target
        # frequency mapping.
        self.confirm_targets = {
            "yes_target": self.full_pool[0],
            "no_target": self.full_pool[1],
        }

        # Reserve the next two for scroll (up/down). If there's enough room
        # to also reserve a fast-tier (per the stacked-marker speed design
        # in design_decisions.md) AND still leave at least
        # MIN_DYNAMIC_TARGETS free afterward, do so; otherwise fall back to
        # single-speed scroll markers only. Never silently consume the
        # entire pool - dynamic targets must always have room.
        MIN_DYNAMIC_TARGETS = 2
        remaining = self.full_pool[2:]

        if len(remaining) >= 4 + MIN_DYNAMIC_TARGETS:
            self.scroll_targets = {
                "scroll_up_slow": remaining[0],
                "scroll_down_slow": remaining[1],
                "scroll_up_fast": remaining[2],
                "scroll_down_fast": remaining[3],
            }
            dynamic_start = 6
        elif len(remaining) >= 2 + MIN_DYNAMIC_TARGETS:
            self.scroll_targets = {
                "scroll_up_slow": remaining[0],
                "scroll_down_slow": remaining[1],
            }
            dynamic_start = 4
        else:
            raise ValueError(
                f"Frequency pool too small: need at least "
                f"2 (confirm) + 2 (scroll) + {MIN_DYNAMIC_TARGETS} (dynamic) "
                f"= {4 + MIN_DYNAMIC_TARGETS} frequencies, got {len(self.full_pool)}."
            )

        self.dynamic_pool = self.full_pool[dynamic_start:]

    def reserved_frequencies(self) -> set[float]:
        """All frequencies that are permanently claimed and must never be
        reused by dynamic (grid/keyboard) targets."""
        return set(self.confirm_targets.values()) | set(self.scroll_targets.values())

    def prepare_dynamic_screen(
        self,
        elements: list[UIElement],
        screen_width: float,
        screen_height: float,
    ) -> list[TargetGroup]:
        """
        Same as the module-level prepare_screen(), but guaranteed to only
        use frequencies from this registry's dynamic_pool - never
        colliding with reserved CONFIRM/SCROLL frequencies. This is what
        keyboard groups, prediction entries, and general UI grids should
        call, instead of the raw prepare_screen() function directly.
        """
        return prepare_screen(elements, screen_width, screen_height, frequency_pool=self.dynamic_pool)

    def max_dynamic_targets_per_group(self) -> int:
        """How many simultaneous dynamic targets fit, given reserved frequencies took some of the pool."""
        return len(self.dynamic_pool)

