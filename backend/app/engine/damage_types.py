"""Damage-type resistances, immunities, and vulnerabilities (PHB ch.9 / Monster Manual).

A DnD 5e creature can modify incoming damage of a specific type:

* **Vulnerability** — damage of that type is doubled (×2).
* **Resistance** — damage of that type is halved (×0.5), rounded down.
* **Immunity** — damage of that type is negated (→ 0).

A modifier can be **qualified** so it only applies to *nonmagical* attacks or to
attacks that are not *silvered* — this models the ubiquitous "resistant/immune
to bludgeoning, piercing, and slashing damage from nonmagical weapons" trait of
fiends, undead, constructs, lycanthropes, and elementals.

Resolution order (PHB p.197, "Damage Resistance and Vulnerability"):

1. Immunity wins outright (0 damage) if any applicable immunity matches.
2. Otherwise resistance halves the damage (rounded down), *then* vulnerability
   doubles it — i.e. "resistance and then vulnerability are applied".
3. Multiple instances of the same kind against one damage type count once
   (no stacking). Rounding happens once per step, rounding down.

This module is **pure** — it never touches the database, combat state, or dice.
``Combatant.apply_damage_modifiers`` (in ``combat.py``) is the single integration
point used by ``Encounter.resolve_attack``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence


# --------------------------------------------------------------------------- #
# Damage type vocabulary
# --------------------------------------------------------------------------- #

# The 13 PHB damage types (PHB ch.9).
DAMAGE_TYPES: tuple[str, ...] = (
    "acid",
    "bludgeoning",
    "cold",
    "fire",
    "force",
    "lightning",
    "necrotic",
    "piercing",
    "poison",
    "psychic",
    "radiant",
    "slashing",
    "thunder",
)

# The three physical damage types — the ones most often resisted by monsters
# via a "from nonmagical weapons" qualifier.
BPS: tuple[str, ...] = ("bludgeoning", "piercing", "slashing")


def normalize_type(damage_type: str) -> str:
    """Lower-case + strip a damage type for matching (case-insensitive)."""
    return (damage_type or "").strip().lower()


# --------------------------------------------------------------------------- #
# Modifier kinds
# --------------------------------------------------------------------------- #

RESISTANCE = "resistance"
IMMUNITY = "immunity"
VULNERABILITY = "vulnerability"

_KINDS: frozenset[str] = frozenset({RESISTANCE, IMMUNITY, VULNERABILITY})


def _normalize_types(types: str | Sequence[str]) -> tuple[str, ...]:
    """Accept a single type or a sequence and return a normalized tuple."""
    if isinstance(types, str):
        types = [t.strip() for t in types.split(",") if t.strip()]
    return tuple(normalize_type(t) for t in types)


@dataclass(frozen=True)
class DamageModifier:
    """One resistance / immunity / vulnerability entry.

    Attributes:
        types: damage types this entry covers (normalized, lower-case).
        kind: one of ``resistance`` / ``immunity`` / ``vulnerability``.
        bypassed_by_magic: if True, this modifier is ignored when the incoming
            attack is magical (models "from nonmagical weapons/attacks").
        bypassed_by_silver: if True, this modifier is ignored when the incoming
            weapon is silvered (models "that aren't silvered").
    """

    types: tuple[str, ...]
    kind: str
    bypassed_by_magic: bool = False
    bypassed_by_silver: bool = False

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ValueError(
                f"DamageModifier.kind must be one of {sorted(_KINDS)}, "
                f"got {self.kind!r}"
            )
        if not self.types:
            raise ValueError("DamageModifier must cover at least one damage type")

    # -- matching -------------------------------------------------------- #

    def covers(self, damage_type: str) -> bool:
        """True if this entry applies to *damage_type* (case-insensitive)."""
        return normalize_type(damage_type) in self.types

    def applies(
        self,
        damage_type: str,
        *,
        magical: bool = False,
        silvered: bool = False,
    ) -> bool:
        """True if this entry actually modifies *damage_type* here.

        A qualified entry ("from nonmagical weapons that aren't silvered") is
        **bypassed** when the attack is magical **or** silvered, matching the
        Monster Manual wording. Concretely:

            bypassed = (bypassed_by_magic and magical) or (bypassed_by_silver and silvered)
        """
        if not self.covers(damage_type):
            return False
        return not (
            (self.bypassed_by_magic and magical)
            or (self.bypassed_by_silver and silvered)
        )

    # -- serialization --------------------------------------------------- #

    def to_dict(self) -> dict:
        d: dict = {"types": list(self.types), "kind": self.kind}
        if self.bypassed_by_magic:
            d["bypassed_by_magic"] = True
        if self.bypassed_by_silver:
            d["bypassed_by_silver"] = True
        return d

    @classmethod
    def from_dict(cls, data: dict | DamageModifier) -> "DamageModifier":
        if isinstance(data, DamageModifier):
            return data
        return cls(
            types=_normalize_types(data.get("types", data.get("type", []))),
            kind=str(data.get("kind", data.get("category", RESISTANCE))).lower(),
            bypassed_by_magic=bool(data.get("bypassed_by_magic", False)),
            bypassed_by_silver=bool(data.get("bypassed_by_silver", False)),
        )


# --------------------------------------------------------------------------- #
# Convenience constructors (terse monster-stat-block syntax)
# --------------------------------------------------------------------------- #


def resist(types: str | Sequence[str], *, magic: bool = False, silver: bool = False) -> DamageModifier:
    """A resistance entry. ``magic=True`` → "from nonmagical attacks" qualifier."""
    return DamageModifier(_normalize_types(types), RESISTANCE, bypassed_by_magic=magic, bypassed_by_silver=silver)


def immune(types: str | Sequence[str], *, magic: bool = False, silver: bool = False) -> DamageModifier:
    """An immunity entry."""
    return DamageModifier(_normalize_types(types), IMMUNITY, bypassed_by_magic=magic, bypassed_by_silver=silver)


def vuln(types: str | Sequence[str]) -> DamageModifier:
    """A vulnerability entry (vulnerabilities are never qualified in 5e)."""
    return DamageModifier(_normalize_types(types), VULNERABILITY)


# Shorthand for the very common "resistant/immune to BPS from nonmagical weapons".
def resist_nonmagical_bps() -> DamageModifier:
    return DamageModifier(BPS, RESISTANCE, bypassed_by_magic=True)


def immune_nonmagical_bps(*, silver_bypasses: bool = False) -> DamageModifier:
    """Immune to nonmagical BPS. Set ``silver_bypasses`` for lycanthropes."""
    return DamageModifier(
        BPS,
        IMMUNITY,
        bypassed_by_magic=True,
        bypassed_by_silver=silver_bypasses,
    )


# --------------------------------------------------------------------------- #
# Modifier set
# --------------------------------------------------------------------------- #


@dataclass
class DamageModifierSet:
    """All of a creature's resistances/immunities/vulnerabilities."""

    modifiers: list[DamageModifier] = field(default_factory=list)

    # -- construction ---------------------------------------------------- #

    def add(self, modifier: DamageModifier) -> "DamageModifierSet":
        self.modifiers.append(modifier)
        return self

    def extend(self, modifiers: Iterable[DamageModifier]) -> "DamageModifierSet":
        self.modifiers.extend(modifiers)
        return self

    @classmethod
    def of(cls, *modifiers: DamageModifier) -> "DamageModifierSet":
        return cls(modifiers=list(modifiers))

    @classmethod
    def from_lists(
        cls,
        resistances: Iterable[Any] = (),
        immunities: Iterable[Any] = (),
        vulnerabilities: Iterable[Any] = (),
    ) -> "DamageModifierSet":
        """Build from three iterables of DamageModifier or raw dicts/strings.

        Each element may be a ``DamageModifier``, a serialized ``dict``, or a
        bare damage-type string (treated as an unqualified modifier of that
        list's kind).
        """

        def _coerce(items: Iterable[Any], kind: str) -> list[DamageModifier]:
            out: list[DamageModifier] = []
            for it in items:
                if isinstance(it, DamageModifier):
                    out.append(it)
                elif isinstance(it, dict):
                    out.append(DamageModifier.from_dict(it))
                else:  # bare string
                    out.append(DamageModifier(_normalize_types(str(it)), kind))
            return out

        return cls(
            modifiers=_coerce(resistances, RESISTANCE)
            + _coerce(immunities, IMMUNITY)
            + _coerce(vulnerabilities, VULNERABILITY)
        )

    # -- inspection ------------------------------------------------------ #

    def __len__(self) -> int:
        return len(self.modifiers)

    def __bool__(self) -> bool:
        return bool(self.modifiers)

    @property
    def is_empty(self) -> bool:
        return not self.modifiers

    def resistances(self) -> list[DamageModifier]:
        return [m for m in self.modifiers if m.kind == RESISTANCE]

    def immunities(self) -> list[DamageModifier]:
        return [m for m in self.modifiers if m.kind == IMMUNITY]

    def vulnerabilities(self) -> list[DamageModifier]:
        return [m for m in self.modifiers if m.kind == VULNERABILITY]

    def has_any(self, damage_type: str) -> bool:
        return any(m.covers(damage_type) for m in self.modifiers)

    # -- serialization --------------------------------------------------- #

    def to_dict(self) -> list[dict]:
        return [m.to_dict() for m in self.modifiers]

    @classmethod
    def from_dict(cls, data: Any) -> "DamageModifierSet":
        if data is None:
            return cls()
        if isinstance(data, DamageModifierSet):
            return cls(modifiers=list(data.modifiers))
        if isinstance(data, dict):
            # Tolerate the {"resistances": [...], "immunities": [...], ...} shape.
            if any(k in data for k in ("resistances", "immunities", "vulnerabilities")):
                return cls.from_lists(
                    resistances=data.get("resistances", []),
                    immunities=data.get("immunities", []),
                    vulnerabilities=data.get("vulnerabilities", []),
                )
            data = [data]
        # list of dicts / DamageModifiers / strings
        mods: list[DamageModifier] = []
        for it in data:
            if isinstance(it, DamageModifier):
                mods.append(it)
            elif isinstance(it, dict):
                mods.append(DamageModifier.from_dict(it))
            elif isinstance(it, str):
                mods.append(DamageModifier(_normalize_types(it), RESISTANCE))
        return cls(modifiers=mods)


# --------------------------------------------------------------------------- #
# Core resolution
# --------------------------------------------------------------------------- #


def compute_damage(
    amount: int,
    damage_type: str,
    modifiers: Any,
    *,
    magical: bool = False,
    silvered: bool = False,
) -> int:
    """Apply a creature's damage modifiers to *amount* of *damage_type*.

    Args:
        amount: the raw incoming damage (already rolled, pre-modifier).
        damage_type: e.g. "fire", "slashing", "poison".
        modifiers: a ``DamageModifierSet``, a list of serialized modifiers, or
            ``None`` (no modifiers → damage unchanged).
        magical: whether the attack is magical (bypasses "from nonmagical").
        silvered: whether the weapon is silvered (bypasses "that aren't silvered").

    Returns:
        The modified damage (never negative).

    Order of operations (PHB p.197):
        immunity → 0; else resistance (halve, round down) then vulnerability (×2).
    """
    if amount <= 0:
        return 0

    if modifiers is None or isinstance(modifiers, DamageModifierSet):
        modset: DamageModifierSet = modifiers or DamageModifierSet()
    else:
        modset = DamageModifierSet.from_dict(modifiers)

    resisted = False
    vulnerable = False
    for mod in modset.modifiers:
        if not mod.applies(damage_type, magical=magical, silvered=silvered):
            continue
        if mod.kind == IMMUNITY:
            return 0
        if mod.kind == RESISTANCE:
            resisted = True
        elif mod.kind == VULNERABILITY:
            vulnerable = True

    out = amount
    if resisted:
        out = out // 2  # 5e: round down
    if vulnerable:
        out = out * 2
    return max(0, out)


def damage_multiplier(
    damage_type: str,
    modifiers: Any,
    *,
    magical: bool = False,
    silvered: bool = False,
) -> float:
    """Return the effective multiplier (0, 0.5, 1, or 2) for *damage_type*.

    Useful for DM summaries and UI badges. Does not reflect rounding.
    """
    if modifiers is None or isinstance(modifiers, DamageModifierSet):
        modset: DamageModifierSet = modifiers or DamageModifierSet()
    else:
        modset = DamageModifierSet.from_dict(modifiers)

    resisted = vulnerable = False
    for mod in modset.modifiers:
        if not mod.applies(damage_type, magical=magical, silvered=silvered):
            continue
        if mod.kind == IMMUNITY:
            return 0.0
        if mod.kind == RESISTANCE:
            resisted = True
        elif mod.kind == VULNERABILITY:
            vulnerable = True
    if resisted and vulnerable:
        # PHB order: halve then double → net ≈ 1 (but rounding differs).
        return 1.0
    if vulnerable:
        return 2.0
    if resisted:
        return 0.5
    return 1.0


# --------------------------------------------------------------------------- #
# DM / UI helpers
# --------------------------------------------------------------------------- #


def summary_for_dm(modifiers: Any) -> str:
    """A one-line DM-facing summary, e.g. 'Resist fire; Immune poison; Vuln cold'.

    Returns an empty string when there are no modifiers.
    """
    if modifiers is None or isinstance(modifiers, DamageModifierSet):
        modset: DamageModifierSet = modifiers or DamageModifierSet()
    else:
        modset = DamageModifierSet.from_dict(modifiers)
    if modset.is_empty:
        return ""

    parts: list[str] = []

    def _fmt(group: list[DamageModifier], label: str) -> None:
        items: list[str] = []
        for m in group:
            label_types = ", ".join(m.types)
            # Fold BPS into the common "nonmagical weapons" phrasing.
            if set(m.types) == set(BPS):
                label_types = "bludgeoning/piercing/slashing"
            suffix = ""
            if m.bypassed_by_magic and m.bypassed_by_silver:
                suffix = " (nonmagical & nonsilvered)"
            elif m.bypassed_by_magic:
                suffix = " (nonmagical)"
            elif m.bypassed_by_silver:
                suffix = " (nonsilvered)"
            items.append(f"{label_types}{suffix}")
        if items:
            parts.append(f"{label} {'; '.join(items)}")

    _fmt(modset.resistances(), "Resist")
    _fmt(modset.immunities(), "Immune")
    _fmt(modset.vulnerabilities(), "Vuln")
    return "; ".join(parts)
