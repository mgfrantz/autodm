"""
Navigation engine — region maps and overland travel.

Turns a world's flat ``regions`` list into a navigable graph: each region gets
stable coordinates, a terrain classification, and a set of connections to
neighbouring regions. The player can travel between connected regions, with a
chance of a random encounter drawn from the destination's ``dangers``.

Everything is derived deterministically from the world data, so the map layout
is stable across requests and only the *player position* (current region +
visited regions) needs to be persisted in the game state.
"""
from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field


# --- Terrain classification ---------------------------------------------------

# Keyword -> terrain type. Order matters: first match wins.
_TERRAIN_KEYWORDS: list[tuple[str, list[str]]] = [
    ("underground", ["cavern", "cave", "dungeon", "underdark", "underground", "mine", "depth"]),
    ("tundra", ["tundra", "snow", "ice", "frozen", "arctic", "glacier", "frost"]),
    ("swamp", ["swamp", "marsh", "bog", "fen", "mire", "wetland"]),
    ("desert", ["desert", "sand", "dune", "waste", "arid", "sahara"]),
    ("mountain", ["mountain", "peak", "mount", "highland", "cliff", "ridge", "hill", "volcano"]),
    ("coast", ["coast", "sea", "ocean", "beach", "shore", "bay", "island", "harbor", "port"]),
    ("forest", ["forest", "wood", "grove", "jungle", "taiga", "wilds"]),
    ("city", ["city", "town", "capitol", "capital", "urban", "metropolis", "citadel", "bastion"]),
    ("plains", ["plain", "field", "grassland", "meadow", "savanna", "prairie", "steppe", "valley", "farmland"]),
]

# Base random-encounter chance per terrain type (fraction in [0, 1]).
TERRAIN_ENCOUNTER_RATE: dict[str, float] = {
    "underground": 0.30,
    "tundra": 0.25,
    "desert": 0.25,
    "swamp": 0.25,
    "mountain": 0.25,
    "forest": 0.20,
    "coast": 0.15,
    "plains": 0.15,
    "city": 0.05,
}

# Emoji per terrain for the frontend.
TERRAIN_ICON: dict[str, str] = {
    "underground": "🕳️",
    "tundra": "❄️",
    "desert": "🏜️",
    "swamp": "🥾",
    "mountain": "⛰️",
    "coast": "🌊",
    "forest": "🌲",
    "city": "🏰",
    "plains": "🌾",
}


def classify_terrain(text: str) -> str:
    """Infer a terrain type from a region's name + description."""
    haystack = (text or "").lower()
    for terrain, keywords in _TERRAIN_KEYWORDS:
        if any(kw in haystack for kw in keywords):
            return terrain
    return "plains"


def terrain_encounter_rate(terrain: str) -> float:
    """Random-encounter probability for a terrain type."""
    return TERRAIN_ENCOUNTER_RATE.get(terrain, 0.15)


def _slugify(name: str) -> str:
    """Turn a region name into a stable, URL/JSON-safe id."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "region"


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# --- Data structures ----------------------------------------------------------

@dataclass
class RegionNode:
    """A single region on the world map."""
    id: str
    name: str
    description: str
    terrain: str
    settlements: list[str]
    dangers: list[str]
    coordinates: tuple[float, float]
    connections: list[str]

    @classmethod
    def from_raw(cls, raw: dict) -> "RegionNode":
        name = raw.get("name") or "Unnamed Region"
        description = raw.get("description") or ""
        coords = raw.get("coordinates") or raw.get("coords")
        if isinstance(coords, list) and len(coords) == 2:
            x = _clamp(float(coords[0]), 0.0, 1.0)
            y = _clamp(float(coords[1]), 0.0, 1.0)
            coordinates = (x, y)
        else:
            coordinates = (0.5, 0.5)  # placeholder, re-laid-out by the map
        connections = [str(c) for c in raw.get("connections", [])] if raw.get("connections") else []
        return cls(
            id=_slugify(name),
            name=name,
            description=description,
            terrain=raw.get("terrain") or classify_terrain(f"{name} {description}"),
            settlements=list(raw.get("settlements", []) or []),
            dangers=list(raw.get("dangers", []) or []),
            coordinates=coordinates,
            connections=connections,
        )

    @property
    def icon(self) -> str:
        return TERRAIN_ICON.get(self.terrain, "📍")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "terrain": self.terrain,
            "icon": self.icon,
            "settlements": self.settlements,
            "dangers": self.dangers,
            "coordinates": [round(self.coordinates[0], 4), round(self.coordinates[1], 4)],
            "connections": self.connections,
        }


@dataclass
class TravelResult:
    """Outcome of a travel attempt."""
    success: bool
    message: str
    from_region_id: str | None
    to_region: RegionNode | None
    travel_hours: int
    encounter_triggered: bool
    encounter_danger: str | None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "from_region_id": self.from_region_id,
            "to_region": self.to_region.to_dict() if self.to_region else None,
            "travel_hours": self.travel_hours,
            "encounter_triggered": self.encounter_triggered,
            "encounter_danger": self.encounter_danger,
        }


# --- Helpers for auto layout / connectivity ----------------------------------

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _assign_coordinates(regions: dict[str, RegionNode], order: list[str]) -> None:
    """Place any regions still on the placeholder onto an even circle.

    Regions that already carry explicit coordinates keep them.
    """
    needs_layout = [rid for rid in order if regions[rid].coordinates == (0.5, 0.5)]
    if not needs_layout:
        return

    # If every region is on the placeholder, lay them all out; otherwise just
    # the unplaced ones are arranged around the centre to avoid clashing.
    n = len(needs_layout)
    cx, cy = 0.5, 0.5
    radius = 0.38 if n > 1 else 0.0
    for i, rid in enumerate(needs_layout):
        if n == 1:
            regions[rid].coordinates = (cx, cy)
            continue
        angle = (2.0 * math.pi * i) / n - math.pi / 2.0  # start at top
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        regions[rid].coordinates = (round(x, 4), round(y, 4))


def _ensure_connections(regions: dict[str, RegionNode], order: list[str]) -> None:
    """Guarantee a single connected graph.

    Regions with author-provided connections keep them. For the rest we connect
    each region to its two nearest neighbours, then add bridge edges between any
    disconnected components.
    """
    if not order:
        return

    # Normalise existing connections: make them bidirectional and resolve any
    # author-supplied connection that is a bare name to a slug id.
    resolved: dict[str, set[str]] = {rid: set() for rid in order}
    for rid in order:
        node = regions[rid]
        for conn in list(node.connections):
            cid = conn if conn in regions else _slugify(conn)
            if cid in regions and cid != rid:
                resolved[rid].add(cid)
                resolved[cid].add(rid)
        node.connections = sorted(resolved[rid])

    # Auto-connect each region to its 2 nearest neighbours if it has no edges.
    for rid in order:
        if resolved[rid]:
            continue
        here = regions[rid].coordinates
        neighbours = sorted(
            (other for other in order if other != rid),
            key=lambda oid: _distance(here, regions[oid].coordinates),
        )
        for oid in neighbours[:2]:
            resolved[rid].add(oid)
            resolved[oid].add(rid)

    # Bridge disconnected components using the closest inter-component pair.
    _bridge_components(regions, order, resolved)

    for rid in order:
        regions[rid].connections = sorted(resolved[rid])


def _bridge_components(
    regions: dict[str, RegionNode],
    order: list[str],
    resolved: dict[str, set[str]],
) -> None:
    """Add edges until the graph has a single connected component."""
    while True:
        components = _connected_components(order, resolved)
        if len(components) <= 1:
            return
        # Find the closest pair of nodes spanning two different components.
        best_pair: tuple[str, str] | None = None
        best_dist = float("inf")
        for i in range(len(components)):
            for j in range(i + 1, len(components)):
                for a in components[i]:
                    for b in components[j]:
                        d = _distance(regions[a].coordinates, regions[b].coordinates)
                        if d < best_dist:
                            best_dist = d
                            best_pair = (a, b)
        if not best_pair:
            return
        a, b = best_pair
        resolved[a].add(b)
        resolved[b].add(a)


def _connected_components(order: list[str], resolved: dict[str, set[str]]) -> list[list[str]]:
    seen: set[str] = set()
    components: list[list[str]] = []
    for start in order:
        if start in seen:
            continue
        stack = [start]
        comp: list[str] = []
        seen.add(start)
        while stack:
            node = stack.pop()
            comp.append(node)
            for nb in resolved[node]:
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        components.append(comp)
    return components


def _find_starting_region(regions: dict[str, RegionNode], world_data: dict) -> str:
    """Pick the region the player begins in."""
    if not regions:
        return ""
    starting = (world_data.get("starting_settlement") or {}).get("name", "")
    starting_slug = _slugify(starting) if starting else ""
    # 1. A region whose settlements include the starting settlement.
    for node in regions.values():
        if starting_slug and any(starting_slug == _slugify(s) for s in node.settlements):
            return node.id
        if starting and starting.lower() in node.name.lower():
            return node.id
    # 2. Fall back to the first region.
    return next(iter(regions.values())).id


# --- WorldMap -----------------------------------------------------------------

@dataclass
class WorldMap:
    """The navigable world map and the player's position on it."""
    regions: dict[str, RegionNode]
    current_region_id: str
    visited_region_ids: list[str]

    # -- construction ----------------------------------------------------------

    @classmethod
    def from_world_data(cls, world_data: dict, game_state: dict) -> "WorldMap":
        """Build a map from world data, restoring the player's saved position."""
        raw_regions = world_data.get("regions") or []
        regions: dict[str, RegionNode] = {}
        order: list[str] = []
        for raw in raw_regions:
            node = RegionNode.from_raw(raw)
            # De-duplicate by id (keep first occurrence).
            if node.id in regions:
                continue
            regions[node.id] = node
            order.append(node.id)

        # If the world has no regions at all, synthesise one from the start.
        if not regions:
            name = (world_data.get("starting_settlement") or {}).get("name") or "Starting Region"
            regions[_slugify(name)] = RegionNode(
                id=_slugify(name),
                name=name,
                description=(world_data.get("starting_settlement") or {}).get("description", ""),
                terrain="city",
                settlements=[name],
                dangers=[],
                coordinates=(0.5, 0.5),
                connections=[],
            )
            order = [_slugify(name)]

        _assign_coordinates(regions, order)
        _ensure_connections(regions, order)

        starting = _find_starting_region(regions, world_data) or order[0]
        current_id = game_state.get("current_region_id") or starting
        if current_id not in regions:
            current_id = starting
        visited = game_state.get("visited_regions") or []
        if not visited:
            visited = [current_id]
        visited = [v for v in visited if v in regions]
        if current_id not in visited:
            visited.insert(0, current_id)

        return cls(regions=regions, current_region_id=current_id, visited_region_ids=visited)

    # -- queries ---------------------------------------------------------------

    def current_region(self) -> RegionNode:
        return self.regions[self.current_region_id]

    def get_region(self, region_id: str) -> RegionNode | None:
        return self.regions.get(region_id)

    def is_visited(self, region_id: str) -> bool:
        return region_id in self.visited_region_ids

    def reachable_region_ids(self) -> list[str]:
        """Ids of regions the player can travel to right now."""
        current = self.current_region()
        return [cid for cid in current.connections if cid in self.regions]

    def reachable_regions(self) -> list[RegionNode]:
        return [self.regions[rid] for rid in self.reachable_region_ids()]

    def can_travel(self, region_id: str) -> bool:
        return region_id in self.current_region().connections and region_id in self.regions

    # -- actions ---------------------------------------------------------------

    def travel(self, region_id: str, rng: random.Random | None = None) -> TravelResult:
        """Attempt to travel to ``region_id`` from the current region."""
        rng = rng or random.Random()

        if region_id not in self.regions:
            return TravelResult(
                success=False,
                message=f"Unknown region '{region_id}'.",
                from_region_id=self.current_region_id,
                to_region=None,
                travel_hours=0,
                encounter_triggered=False,
                encounter_danger=None,
            )

        if region_id == self.current_region_id:
            return TravelResult(
                success=False,
                message="You are already here.",
                from_region_id=self.current_region_id,
                to_region=self.regions[region_id],
                travel_hours=0,
                encounter_triggered=False,
                encounter_danger=None,
            )

        if not self.can_travel(region_id):
            dest = self.regions[region_id]
            return TravelResult(
                success=False,
                message=f"{dest.name} is not connected to {self.current_region().name}; there is no direct route.",
                from_region_id=self.current_region_id,
                to_region=dest,
                travel_hours=0,
                encounter_triggered=False,
                encounter_danger=None,
            )

        from_region = self.current_region()
        dest = self.regions[region_id]
        dist = _distance(from_region.coordinates, dest.coordinates)
        # Normalise distance (0..~0.76 diagonal) into travel hours.
        travel_hours = max(4, round(dist * 48))

        # Random encounter roll based on destination terrain.
        chance = terrain_encounter_rate(dest.terrain)
        triggered = rng.random() < chance
        danger: str | None = None
        if triggered and dest.dangers:
            danger = rng.choice(dest.dangers)

        # Commit the move.
        self.current_region_id = region_id
        if region_id not in self.visited_region_ids:
            self.visited_region_ids.append(region_id)

        if triggered and danger:
            message = (
                f"You travel for about {travel_hours} hours toward {dest.name}. "
                f"Your journey is interrupted: {danger}!"
            )
        elif triggered:
            message = (
                f"You travel for about {travel_hours} hours toward {dest.name}. "
                f"Something stirs in the {dest.terrain} — danger is near."
            )
        else:
            message = f"You travel for about {travel_hours} hours and arrive safely at {dest.name}."

        return TravelResult(
            success=True,
            message=message,
            from_region_id=from_region.id,
            to_region=dest,
            travel_hours=travel_hours,
            encounter_triggered=triggered,
            encounter_danger=danger,
        )

    # -- persistence ------------------------------------------------------------

    def to_game_state(self) -> dict:
        """The portion of game state that must be persisted between requests."""
        return {
            "current_region_id": self.current_region_id,
            "visited_regions": list(self.visited_region_ids),
        }

    def to_dict(self) -> dict:
        return {
            "current_region_id": self.current_region_id,
            "current_region": self.current_region().to_dict(),
            "visited_region_ids": list(self.visited_region_ids),
            "reachable_region_ids": self.reachable_region_ids(),
            "regions": [node.to_dict() for node in self.regions.values()],
        }
