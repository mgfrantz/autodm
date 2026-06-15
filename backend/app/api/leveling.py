"""
Leveling API — XP awarding, auto level-up, and ability score improvements.

Endpoints (mounted under /api/characters):
- GET  /{character_id}/leveling            — XP/level progress overview
- POST /{character_id}/leveling/award-xp   — award XP and auto-level-up
- POST /{character_id}/leveling/apply-asi  — spend an Ability Score Improvement
- GET  /{character_id}/leveling/features   — class features earned so far
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import Character
from app.engine.dice import ability_modifier, proficiency_bonus
from app.engine.leveling import (
    ASIChoice,
    apply_asi,
    apply_xp,
    asi_available,
    asi_count_through,
    features_at_level,
    features_through_level,
    hit_die_for_class,
    is_asi_level,
    level_progress,
    level_for_xp,
    xp_for_level,
    MAX_ABILITY_SCORE,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class LevelingProgress(BaseModel):
    level: int
    xp: int
    level_start_xp: int
    next_level_xp: int | None
    xp_into_level: int
    xp_to_next: int | None
    progress: float
    proficiency_bonus: int
    asi_available: int
    asi_used: int
    asi_count_earned: int
    next_asi_level: int | None


class AwardXPRequest(BaseModel):
    xp: int  # amount to add (may be negative, e.g. XP adjustment)


class AwardXPResponse(BaseModel):
    success: bool
    xp_awarded: int
    xp_total: int
    leveled_up: bool
    from_level: int
    to_level: int
    levels_gained: int
    hp_gained: int
    max_hp: int
    current_hp: int
    proficiency_bonus: int
    proficiency_changed: bool
    asi_unlocked: bool
    asi_available: int
    new_features: list[dict]
    message: str


class ASIChoiceModel(BaseModel):
    ability: str  # strength | dexterity | constitution | intelligence | wisdom | charisma
    amount: int = 1


class ApplyASIRequest(BaseModel):
    # A single ASI instance = 2 points. Pass one choice of amount 2, or two of
    # amount 1. The engine validates the total.
    choices: list[ASIChoiceModel]


class ApplyASIResponse(BaseModel):
    success: bool
    message: str
    abilities: dict[str, int]
    asi_used: int
    asi_available: int
    max_hp: int  # current_hp unaffected, but CON changes shift max HP
    applied: list[dict]


class FeaturesResponse(BaseModel):
    char_class: str
    level: int
    features: list[dict]
    next_level_feature: dict | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ABILITY_FIELDS = (
    "strength", "dexterity", "constitution",
    "intelligence", "wisdom", "charisma",
)


def _load_abilities(character: Character) -> dict[str, int]:
    return {a: int(getattr(character, a)) for a in _ABILITY_FIELDS}


def _recompute_max_hp(character: Character) -> None:
    """Recompute max_hp from CON when a CON ASI shifts the modifier.

    This is an approximation: it recalculates max_hp as if every level used the
    fixed-average gain plus the (possibly updated) CON mod. We only call this
    after an ASI to CON, so the delta equals (con_mod_after - con_mod_before)
    * character.level.
    """
    con_mod = ability_modifier(character.constitution)
    hd = hit_die_for_class(character.char_class)
    base = hd + con_mod  # level 1 starting HP
    per_level = (hd // 2 + 1) + con_mod
    new_max = base + per_level * (character.level - 1)
    # Floor at 1 and don't reduce current_hp below a sensible minimum.
    old_max = character.max_hp or 1
    character.max_hp = max(1, new_max)
    # Shift current HP by the same delta so a CON gain heals proportionally.
    delta = character.max_hp - old_max
    if delta > 0:
        character.current_hp = min(character.max_hp, (character.current_hp or 0) + delta)


def _progress_for(character: Character) -> LevelingProgress:
    cls = character.char_class
    progress = level_progress(character.xp or 0)
    from app.engine.leveling import asi_levels
    earned = asi_count_through(character.level, cls)
    used = character.asi_used or 0
    avail = asi_available(character.level, cls, used)

    all_asi = asi_levels(cls)
    next_asi = next((lvl for lvl in all_asi if lvl > character.level), None)

    return LevelingProgress(
        level=character.level,
        xp=character.xp or 0,
        level_start_xp=progress["level_start_xp"],
        next_level_xp=progress["next_level_xp"],
        xp_into_level=progress["xp_into_level"],
        xp_to_next=progress["xp_to_next"],
        progress=round(progress["progress"], 4),
        proficiency_bonus=proficiency_bonus(character.level),
        asi_available=avail,
        asi_used=used,
        asi_count_earned=earned,
        next_asi_level=next_asi,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/{character_id}/leveling", response_model=LevelingProgress)
def get_leveling(character_id: int, db: Session = Depends(get_db)):
    """Get a character's XP/level progress, proficiency, and ASI status."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")
    return _progress_for(character)


@router.post("/{character_id}/leveling/award-xp", response_model=AwardXPResponse)
def award_xp(character_id: int, request: AwardXPRequest, db: Session = Depends(get_db)):
    """Award XP to a character and automatically apply any level-ups.

    On each level gained the character gains HP (fixed-average hit die + CON
    mod) which is added to both max and current HP. Proficiency bonus is
    derived from level everywhere else, so no separate update is needed.
    Ability Score Improvements are *not* spent automatically — the response
    reports ``asi_available`` so the player can choose (see ``apply-asi``).
    """
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    xp_before = character.xp or 0
    xp_total = max(0, xp_before + request.xp)

    con_mod = ability_modifier(character.constitution)
    result = apply_xp(
        char_class=character.char_class,
        level=character.level,
        xp_before=xp_before,
        xp_after=xp_total,
        con_mod=con_mod,
        asi_used=character.asi_used or 0,
    )

    # Persist.
    character.xp = xp_total
    if result.leveled_up:
        character.level = result.to_level
        if result.hp_gained:
            character.max_hp = (character.max_hp or 0) + result.hp_gained
            character.current_hp = (character.current_hp or 0) + result.hp_gained
    character.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(character)

    if result.leveled_up:
        feats = ", ".join(f"Level {lvl}: {f}" for lvl, f in result.new_features)
        asi_note = " ASI available — allocate ability scores!" if result.asi_unlocked else ""
        message = (
            f"{character.name} advanced from level {result.from_level} to "
            f"{result.to_level}! Gained {result.hp_gained} HP."
            + (f" New abilities: {feats}." if feats else "")
            + asi_note
        )
    else:
        message = f"{character.name} gained {request.xp} XP ({xp_total} total)."

    return AwardXPResponse(
        success=True,
        xp_awarded=request.xp,
        xp_total=xp_total,
        leveled_up=result.leveled_up,
        from_level=result.from_level,
        to_level=result.to_level,
        levels_gained=result.levels_gained,
        hp_gained=result.hp_gained,
        max_hp=character.max_hp,
        current_hp=character.current_hp,
        proficiency_bonus=proficiency_bonus(character.level),
        proficiency_changed=result.proficiency_changed,
        asi_unlocked=result.asi_unlocked,
        asi_available=result.asi_available,
        new_features=[{"level": lvl, "feature": f} for lvl, f in result.new_features],
        message=message,
    )


@router.post("/{character_id}/leveling/apply-asi", response_model=ApplyASIResponse)
def apply_asi_endpoint(
    character_id: int,
    request: ApplyASIRequest,
    db: Session = Depends(get_db),
):
    """Spend one Ability Score Improvement instance.

    Body ``choices`` must total exactly 2 points (one ability +2, or two
    abilities +1 each). Scores are clamped to 20. Raising CON also increases
    max HP retroactively (one CON mod step per level).
    """
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    if not request.choices:
        raise HTTPException(status_code=400, detail="At least one choice required")

    choices = [ASIChoice(ability=c.ability, amount=c.amount) for c in request.choices]

    result = apply_asi(
        abilities=_load_abilities(character),
        choices=choices,
        level=character.level,
        char_class=character.char_class,
        asi_used=character.asi_used or 0,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    # Persist ability changes.
    con_changed = False
    for choice in result.applied:
        current = int(getattr(character, choice.ability))
        setattr(character, choice.ability, current + choice.amount)
        if choice.ability == "constitution" and choice.amount > 0:
            con_changed = True

    character.asi_used = (character.asi_used or 0) + 1
    if con_changed:
        _recompute_max_hp(character)
    character.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(character)

    return ApplyASIResponse(
        success=True,
        message=result.message,
        abilities=_load_abilities(character),
        asi_used=character.asi_used,
        asi_available=asi_available(character.level, character.char_class, character.asi_used),
        max_hp=character.max_hp,
        applied=[{"ability": c.ability, "amount": c.amount} for c in result.applied],
    )


@router.get("/{character_id}/leveling/features", response_model=FeaturesResponse)
def get_features(character_id: int, db: Session = Depends(get_db)):
    """List class features a character has earned, and a preview of the next."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    earned = features_through_level(character.char_class, character.level)

    next_level = character.level + 1
    next_feature = None
    if next_level <= 20:
        feat = features_at_level(character.char_class, next_level)
        next_feature = {"level": next_level, "feature": feat} if feat else None

    return FeaturesResponse(
        char_class=character.char_class,
        level=character.level,
        features=[{"level": lvl, "feature": f} for lvl, f in earned],
        next_level_feature=next_feature,
    )
