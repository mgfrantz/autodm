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
from app.engine.multiclassing import (
    parse_classes,
    serialize_classes,
    calculate_multiclass_hp,
    calculate_proficiency_bonus,
    calculate_multiclass_asi_status,
    build_multiclass_summary,
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
    classes: dict[str, int]  # All classes with levels
    primary_class: str  # The class with the highest level
    total_level: int  # Sum of all class levels (source of truth for multiclass)


class AwardXPRequest(BaseModel):
    xp: int  # amount to add (may be negative, e.g. XP adjustment)
    target_class: str | None = None  # Optional: which class to level up (for multiclass)


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
    classes: dict[str, int]  # Updated classes
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
    classes: dict[str, int]  # All classes with levels
    features: dict[str, list[dict]]  # Features per class
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

    This now properly handles multiclassing by summing HP from all classes.
    """
    con_mod = ability_modifier(character.constitution or 10)
    classes = parse_classes(character.classes or "{}")
    if not classes:
        # Backward compatibility
        classes = {character.char_class.lower(): character.level or 1}

    new_max, _ = calculate_multiclass_hp(classes, con_mod)
    old_max = character.max_hp or 1
    character.max_hp = max(1, new_max)
    # Shift current HP by the same delta so a CON gain heals proportionally.
    delta = character.max_hp - old_max
    if delta > 0:
        character.current_hp = min(character.max_hp, (character.current_hp or 0) + delta)


def _progress_for(character: Character) -> LevelingProgress:
    """Build leveling progress, handling multiclassing."""
    classes = parse_classes(character.classes or "{}")
    if not classes:
        classes = {character.char_class.lower(): character.level or 1}

    # The total level is the sum of all class levels — this is the source of
    # truth for multiclass characters and is more reliable than the (possibly
    # stale) ``character.level`` column.
    total_level = sum(classes.values())

    progress = level_progress(character.xp or 0)
    from app.engine.leveling import asi_levels

    # Calculate total ASIs across all classes
    total_earned = 0
    next_asi_level = None
    for cls_name, cls_level in classes.items():
        total_earned += len([lvl for lvl in asi_levels(cls_name) if lvl <= cls_level])
        for lvl in asi_levels(cls_name):
            if lvl > cls_level:
                if next_asi_level is None or lvl < next_asi_level:
                    next_asi_level = lvl
                break

    used = character.asi_used or 0
    avail = max(0, total_earned - used)

    primary_class = max(classes.items(), key=lambda x: x[1])[0] if classes else "commoner"

    return LevelingProgress(
        level=total_level,
        xp=character.xp or 0,
        level_start_xp=progress["level_start_xp"],
        next_level_xp=progress["next_level_xp"],
        xp_into_level=progress["xp_into_level"],
        xp_to_next=progress["xp_to_next"],
        progress=round(progress["progress"], 4),
        proficiency_bonus=calculate_proficiency_bonus(classes),
        asi_available=avail,
        asi_used=used,
        asi_count_earned=total_earned,
        next_asi_level=next_asi_level,
        classes=classes,
        primary_class=primary_class,
        total_level=total_level,
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

    For multiclass characters, the `target_class` field allows choosing which
    class gets the level-up. If not specified, the primary class (highest level)
    is used.

    HP gains are calculated using the hit die of the class being leveled.
    Ability Score Improvements are *not* spent automatically — the response
    reports `asi_available` so the player can choose (see `apply-asi`).
    """
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    xp_before = character.xp or 0
    xp_total = max(0, xp_before + request.xp)

    con_mod = ability_modifier(character.constitution or 10)

    # Get current classes
    classes = parse_classes(character.classes or "{}")
    if not classes:
        classes = {character.char_class.lower(): character.level or 1}

    # Determine which class to level up
    target_class = request.target_class
    if target_class is None:
        # Default to primary class (highest level)
        target_class = max(classes.items(), key=lambda x: x[1])[0]
    else:
        target_class = target_class.lower()
        if target_class not in classes:
            raise HTTPException(
                status_code=400,
                detail=f"Character does not have levels in {target_class}"
            )

    # Calculate current level for the target class
    from_level_total = sum(classes.values())
    to_level_total = level_for_xp(xp_total)

    # Check if the character actually levels up
    if to_level_total <= from_level_total:
        # No level up, just update XP
        character.xp = xp_total
        character.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(character)

        return AwardXPResponse(
            success=True,
            xp_awarded=request.xp,
            xp_total=xp_total,
            leveled_up=False,
            from_level=from_level_total,
            to_level=to_level_total,
            levels_gained=0,
            hp_gained=0,
            max_hp=character.max_hp,
            current_hp=character.current_hp,
            proficiency_bonus=calculate_proficiency_bonus(classes),
            proficiency_changed=False,
            asi_unlocked=False,
            asi_available=_progress_for(character).asi_available,
            new_features=[],
            classes=classes,
            message=f"{character.name} gained {request.xp} XP ({xp_total} total).",
        )

    # Level up! Determine how many levels to add to the target class
    levels_gained = to_level_total - from_level_total

    # Add levels to the target class
    old_target_level = classes[target_class]
    classes[target_class] += levels_gained
    new_target_level = classes[target_class]

    # Calculate HP gained (only for the new levels in the target class)
    from app.engine.leveling import hp_gained_for_levels
    hp_gained = hp_gained_for_levels(
        from_level=old_target_level,
        to_level=new_target_level,
        char_class=target_class,
        con_mod=con_mod,
    )

    # Update character state
    character.xp = xp_total
    character.level = to_level_total
    character.classes = serialize_classes(classes)
    character.char_class = max(classes.items(), key=lambda x: x[1])[0]

    # Add HP gains
    character.max_hp = (character.max_hp or 0) + hp_gained
    character.current_hp = (character.current_hp or 0) + hp_gained

    character.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(character)

    # Get new features for the levels gained
    new_features = []
    for lvl in range(old_target_level + 1, new_target_level + 1):
        feat = features_at_level(target_class, lvl)
        if feat:
            new_features.append({
                "level": lvl,
                "class": target_class,
                "feature": feat,
            })

    # Check for ASI unlock
    from app.engine.leveling import asi_levels
    asi_lvls = asi_levels(target_class)
    asi_unlocked = any(old_target_level < lvl <= new_target_level for lvl in asi_lvls)

    # Get ASI status
    summary = build_multiclass_summary(classes, con_mod, character.asi_used or 0)

    # Build message
    feats_str = ", ".join(f"{f['class']} L{f['level']}: {f['feature']}" for f in new_features)
    asi_note = " ASI available — allocate ability scores!" if asi_unlocked else ""
    message = (
        f"{character.name} advanced from level {from_level_total} to "
        f"{to_level_total}! Gained {hp_gained} HP in {target_class}."
        + (f" New abilities: {feats_str}." if feats_str else "")
        + asi_note
    )

    return AwardXPResponse(
        success=True,
        xp_awarded=request.xp,
        xp_total=xp_total,
        leveled_up=True,
        from_level=from_level_total,
        to_level=to_level_total,
        levels_gained=levels_gained,
        hp_gained=hp_gained,
        max_hp=character.max_hp,
        current_hp=character.current_hp,
        proficiency_bonus=summary.proficiency_bonus,
        proficiency_changed=proficiency_bonus(from_level_total) != summary.proficiency_bonus,
        asi_unlocked=asi_unlocked,
        asi_available=summary.asi_status.available,
        new_features=new_features,
        classes=classes,
        message=message,
    )


@router.post("/{character_id}/leveling/apply-asi", response_model=ApplyASIResponse)
def apply_asi_endpoint(
    character_id: int,
    request: ApplyASIRequest,
    db: Session = Depends(get_db),
):
    """Spend one Ability Score Improvement instance.

    Body `choices` must total exactly 2 points (one ability +2, or two
    abilities +1 each). Scores are clamped to 20. Raising CON also increases
    max HP retroactively (one CON mod step per level).

    For multiclass characters, ASIs from any class can be spent freely.
    """
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    if not request.choices:
        raise HTTPException(status_code=400, detail="At least one choice required")

    choices = [ASIChoice(ability=c.ability, amount=c.amount) for c in request.choices]

    # Get ASI status across all classes
    classes = parse_classes(character.classes or "{}")
    if not classes:
        classes = {character.char_class.lower(): character.level or 1}

    asi_status = calculate_multiclass_asi_status(classes, character.asi_used or 0)

    if asi_status.available <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"No ASIs available. Earned: {asi_status.earned}, Used: {asi_status.used}"
        )

    result = apply_asi(
        abilities=_load_abilities(character),
        choices=choices,
        level=character.level,  # Use total level
        char_class=character.char_class,  # Use primary class for basic validation
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

    # Recalculate ASI status
    asi_status = calculate_multiclass_asi_status(classes, character.asi_used)

    return ApplyASIResponse(
        success=True,
        message=result.message,
        abilities=_load_abilities(character),
        asi_used=character.asi_used,
        asi_available=asi_status.available,
        max_hp=character.max_hp,
        applied=[{"ability": c.ability, "amount": c.amount} for c in result.applied],
    )


@router.get("/{character_id}/leveling/features", response_model=FeaturesResponse)
def get_features(character_id: int, db: Session = Depends(get_db)):
    """List class features a character has earned, and a preview of the next."""
    character = db.query(Character).filter(Character.id == character_id).first()
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    classes = parse_classes(character.classes or "{}")
    if not classes:
        classes = {character.char_class.lower(): character.level or 1}

    # Get features for each class
    all_features = {}
    for cls_name, cls_level in classes.items():
        earned = features_through_level(cls_name, cls_level)
        all_features[cls_name] = [{"level": lvl, "feature": f} for lvl, f in earned]

    # Find the next level feature across all classes
    next_level = character.level + 1
    next_feature = None
    if next_level <= 20:
        # Check if any class gets a feature at the next total level
        for cls_name in classes.keys():
            feat = features_at_level(cls_name, next_level)
            if feat:
                next_feature = {"level": next_level, "class": cls_name, "feature": feat}
                break

    return FeaturesResponse(
        classes=classes,
        features=all_features,
        next_level_feature=next_feature,
    )