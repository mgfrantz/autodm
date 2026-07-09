"""
Affliction engine for DnD 5e diseases and poisons.

Handles lingering afflictions with onset/incubation periods, staged effects,
and save-based recovery/curing. Distinct from the one-shot "poisoned" condition.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from enum import Enum
import random


class AfflictionType(Enum):
    """Type of lingering affliction."""
    DISEASE = "disease"
    POISON = "poison"


class EffectType(Enum):
    """Types of effects an affliction can apply."""
    # Damage types
    DAMAGE = "damage"
    MAX_HP_REDUCTION = "max_hp_reduction"
    
    # Condition application
    CONDITION = "condition"
    
    # Advantage/disadvantage
    DISADVANTAGE_CHECKS = "disadvantage_checks"
    DISADVANTAGE_ATTACKS = "disadvantage_attacks"
    DISADVANTAGE_SAVES = "disadvantage_saves"
    
    # Ability score changes
    ABILITY_PENALTY = "ability_penalty"
    
    # Special
    INCAPACITATED = "incapacitated"
    UNCONSCIOUS = "unconscious"
    DEATH = "death"
    
    # Description-only (for narration)
    NARRATIVE = "narrative"


@dataclass
class AfflictionEffect:
    """A single mechanical effect applied by an affliction."""
    type: EffectType
    value: Optional[Any] = None  # Damage dice, condition name, ability score, etc.
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "type": self.type.value,
            "value": self.value,
            "description": self.description
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AfflictionEffect":
        """Create from dictionary."""
        return cls(
            type=EffectType(data["type"]),
            value=data.get("value"),
            description=data.get("description", "")
        )


@dataclass
class AfflictionStage:
    """A stage in an affliction's progression."""
    name: str  # e.g., "Incubation", "Early", "Advanced", "Terminal"
    effects: List[AfflictionEffect]
    duration_days: Optional[int] = None  # None = indefinite until next stage
    save_dc: Optional[int] = None  # DC for save to end/progress this stage
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "effects": [e.to_dict() for e in self.effects],
            "duration_days": self.duration_days,
            "save_dc": self.save_dc
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AfflictionStage":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            effects=[AfflictionEffect.from_dict(e) for e in data.get("effects", [])],
            duration_days=data.get("duration_days"),
            save_dc=data.get("save_dc")
        )


@dataclass
class Affliction:
    """A disease or poison with staged progression."""
    id: str
    name: str
    type: AfflictionType
    description: str
    stages: List[AfflictionStage]
    onset_days: int = 0  # Days before first stage appears
    save_ability: str = "constitution"  # Ability for saves
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "description": self.description,
            "stages": [s.to_dict() for s in self.stages],
            "onset_days": self.onset_days,
            "save_ability": self.save_ability
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Affliction":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            type=AfflictionType(data["type"]),
            description=data["description"],
            stages=[AfflictionStage.from_dict(s) for s in data.get("stages", [])],
            onset_days=data.get("onset_days", 0),
            save_ability=data.get("save_ability", "constitution")
        )


@dataclass
class ActiveAffliction:
    """An active affliction on a character."""
    affliction_id: str
    affliction: Affliction
    stage_index: int = 0  # Current stage (or -1 for onset period)
    days_in_stage: int = 0
    days_since_onset: int = 0
    cured: bool = False
    
    @property
    def is_onset(self) -> bool:
        """True if still in onset period."""
        return self.days_since_onset < self.affliction.onset_days
    
    @property
    def current_stage(self) -> Optional[AfflictionStage]:
        """Get the current stage's effects."""
        if self.stage_index < 0 or self.stage_index >= len(self.affliction.stages):
            return None
        return self.affliction.stages[self.stage_index]
    
    @property
    def is_terminal(self) -> bool:
        """True if at the final stage."""
        return self.stage_index == len(self.affliction.stages) - 1
    
    @property
    def is_finished(self) -> bool:
        """True if cured or completed all stages."""
        return self.cured or (self.stage_index >= len(self.affliction.stages))
    
    def advance_day(self) -> "AfflictionAdvanceResult":
        """
        Advance the affliction by one day.
        Returns the result of the advancement.
        """
        if self.cured:
            return AfflictionAdvanceResult(
                changed=False,
                previous_stage=self.stage_index,
                new_stage=self.stage_index,
                effects_applied=[],
                narrative=""
            )
        
        self.days_since_onset += 1
        
        # If still in onset period
        if self.is_onset:
            return AfflictionAdvanceResult(
                changed=False,
                previous_stage=-1,
                new_stage=-1,
                effects_applied=[],
                narrative=f"Onset period continues ({self.days_since_onset}/{self.affliction.onset_days})"
            )
        
        # Move to first stage if just finished onset
        if self.stage_index == -1:
            self.stage_index = 0
            self.days_in_stage = 0
            stage = self.current_stage
            return AfflictionAdvanceResult(
                changed=True,
                previous_stage=-1,
                new_stage=0,
                effects_applied=stage.effects if stage else [],
                narrative=f"{self.affliction.name} has entered its {stage.name if stage else 'first'} stage"
            )
        
        # Check if current stage has ended
        stage = self.current_stage
        if not stage:
            return AfflictionAdvanceResult(
                changed=False,
                previous_stage=self.stage_index,
                new_stage=self.stage_index,
                effects_applied=[],
                narrative="No more stages"
            )
        
        self.days_in_stage += 1
        
        # If stage has duration and we've exceeded it
        if stage.duration_days is not None and self.days_in_stage >= stage.duration_days:
            # Check if there's a next stage
            if self.stage_index < len(self.affliction.stages) - 1:
                prev_stage = self.stage_index
                self.stage_index += 1
                self.days_in_stage = 0
                new_stage = self.current_stage
                return AfflictionAdvanceResult(
                    changed=True,
                    previous_stage=prev_stage,
                    new_stage=self.stage_index,
                    effects_applied=new_stage.effects if new_stage else [],
                    narrative=f"{self.affliction.name} has progressed to {new_stage.name if new_stage else 'next stage'}"
                )
        
        # No stage change
        return AfflictionAdvanceResult(
            changed=False,
            previous_stage=self.stage_index,
            new_stage=self.stage_index,
            effects_applied=[],
            narrative=f"{self.affliction.name} continues in {stage.name}"
        )
    
    def attempt_save(self, roll: int, modifier: int, treat: bool = False) -> "AfflictionSaveResult":
        """
        Attempt a save to cure or end the affliction.
        
        Args:
            roll: The d20 roll (before modifiers)
            modifier: Ability modifier
            treat: If True, character is being treated (advantage)
        
        Returns:
            Result of the save attempt
        """
        stage = self.current_stage
        if not stage or stage.save_dc is None:
            return AfflictionSaveResult(
                success=False,
                dc=0,
                roll=roll,
                modifier=modifier,
                total=roll + modifier,
                treated=treat,
                narrative="No save available for current stage"
            )
        
        dc = stage.save_dc
        total = roll + modifier
        success = total >= dc
        
        narrative = f"Save vs {self.affliction.name} ({self.affliction.save_ability}): rolled {roll} + {modifier} = {total} vs DC {dc}"
        if treat:
            narrative += " (with treatment)"
        
        if success:
            self.cured = True
            narrative += " — SAVED and cured!"
        else:
            narrative += " — FAILED"
        
        return AfflictionSaveResult(
            success=success,
            dc=dc,
            roll=roll,
            modifier=modifier,
            total=total,
            treated=treat,
            narrative=narrative
        )
    
    def get_active_effects(self) -> List[AfflictionEffect]:
        """Get all currently active effects."""
        if self.is_onset or self.cured:
            return []
        
        stage = self.current_stage
        return stage.effects if stage else []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "affliction_id": self.affliction_id,
            "affliction": self.affliction.to_dict(),
            "stage_index": self.stage_index,
            "days_in_stage": self.days_in_stage,
            "days_since_onset": self.days_since_onset,
            "cured": self.cured
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActiveAffliction":
        """Create from dictionary."""
        return cls(
            affliction_id=data["affliction_id"],
            affliction=Affliction.from_dict(data["affliction"]),
            stage_index=data.get("stage_index", 0),
            days_in_stage=data.get("days_in_stage", 0),
            days_since_onset=data.get("days_since_onset", 0),
            cured=data.get("cured", False)
        )


@dataclass
class AfflictionAdvanceResult:
    """Result of advancing an affliction by a day."""
    changed: bool
    previous_stage: int
    new_stage: int
    effects_applied: List[AfflictionEffect]
    narrative: str


@dataclass
class AfflictionSaveResult:
    """Result of an affliction save attempt."""
    success: bool
    dc: int
    roll: int
    modifier: int
    total: int
    treated: bool
    narrative: str


@dataclass
class AfflictionStatus:
    """Status of a character's afflictions."""
    active: List[ActiveAffliction] = field(default_factory=list)
    
    @property
    def active_afflictions(self) -> List[ActiveAffliction]:
        """Get non-cured afflictions."""
        return [a for a in self.active if not a.cured]
    
    @property
    def has_afflictions(self) -> bool:
        """True if character has any active afflictions."""
        return len(self.active_afflictions) > 0
    
    def add_affliction(self, affliction: Affliction) -> ActiveAffliction:
        """Add a new affliction."""
        active = ActiveAffliction(
            affliction_id=affliction.id,
            affliction=affliction,
            stage_index=0 if affliction.onset_days == 0 else -1,  # Stage 0 immediately if no onset, else onset period
            days_in_stage=0,
            days_since_onset=0,
            cured=False
        )
        self.active.append(active)
        return active
    
    def get_by_id(self, affliction_id: str) -> Optional[ActiveAffliction]:
        """Get an active affliction by ID."""
        for a in self.active:
            if a.affliction_id == affliction_id:
                return a
        return None
    
    def advance_days(self, days: int = 1) -> List[AfflictionAdvanceResult]:
        """Advance all afflictions by the given number of days."""
        results = []
        for _ in range(days):
            for affliction in self.active_afflictions:
                result = affliction.advance_day()
                if result.changed or result.narrative:
                    results.append(result)
        return results
    
    def get_all_active_effects(self) -> List[AfflictionEffect]:
        """Get all active effects from all afflictions."""
        effects = []
        for affliction in self.active_afflictions:
            effects.extend(affliction.get_active_effects())
        return effects
    
    def remove_cured(self) -> None:
        """Remove cured afflictions from the list."""
        self.active = [a for a in self.active if not a.cured]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "active": [a.to_dict() for a in self.active]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AfflictionStatus":
        """Create from dictionary."""
        return cls(
            active=[ActiveAffliction.from_dict(a) for a in data.get("active", [])]
        )


# ============================================================================
# AFFLICTION REGISTRY (DnD 5e DMG diseases and poisons)
# ============================================================================

AFFLICTION_REGISTRY: Dict[str, Affliction] = {}


def register_affliction(affliction: Affliction) -> None:
    """Register an affliction."""
    AFFLICTION_REGISTRY[affliction.id] = affliction


def get_affliction(affliction_id: str) -> Optional[Affliction]:
    """Get an affliction by ID."""
    return AFFLICTION_REGISTRY.get(affliction_id)


def list_afflictions(affliction_type: Optional[AfflictionType] = None) -> List[Affliction]:
    """List all registered afflictions, optionally filtered by type."""
    if affliction_type is None:
        return list(AFFLICTION_REGISTRY.values())
    return [a for a in AFFLICTION_REGISTRY.values() if a.type == affliction_type]


# Register DMG diseases
register_affliction(Affliction(
    id="cackle_fever",
    name="Cackle Fever",
    type=AfflictionType.DISEASE,
    description="A disease that affects humanoids, spread through infected spores.",
    onset_days=1,
    save_ability="constitution",
    stages=[
        AfflictionStage(
            name="Incubation",
            effects=[AfflictionEffect(EffectType.NARRATIVE, description="High fever and coughing fits")],
            duration_days=3,
            save_dc=13
        ),
        AfflictionStage(
            name="Advanced",
            effects=[
                AfflictionEffect(EffectType.DISADVANTAGE_CHECKS, description="Disadvantage on Constitution checks"),
                AfflictionEffect(EffectType.DAMAGE, value=3, description="3 (1d6) poison damage at end of each long rest"),
            ],
            duration_days=7,
            save_dc=13
        ),
    ]
))

register_affliction(Affliction(
    id="sewer_plague",
    name="Sewer Plague",
    type=AfflictionType.DISEASE,
    description="A disease spread by infected rats, common in sewers and filthy areas.",
    onset_days=1,
    save_ability="constitution",
    stages=[
        AfflictionStage(
            name="Incubation",
            effects=[AfflictionEffect(EffectType.NARRATIVE, description="Weakness and nausea")],
            duration_days=1,
            save_dc=11
        ),
        AfflictionStage(
            name="Advanced",
            effects=[
                AfflictionEffect(EffectType.INCAPACITATED, description="Incapacitated"),
            ],
            duration_days=6,
            save_dc=11
        ),
    ]
))

register_affliction(Affliction(
    id="mindfire",
    name="Mindfire",
    type=AfflictionType.DISEASE,
    description="A disease that affects the mind, causing confusion and memory loss.",
    onset_days=0,  # Immediate
    save_ability="constitution",
    stages=[
        AfflictionStage(
            name="Early",
            effects=[
                AfflictionEffect(EffectType.DISADVANTAGE_SAVES, description="Disadvantage on Intelligence, Wisdom, and Charisma saving throws"),
            ],
            duration_days=7,
            save_dc=12
        ),
    ]
))

register_affliction(Affliction(
    id="seizure",
    name="Seizure",
    type=AfflictionType.DISEASE,
    description="A disease affecting the nervous system, causing convulsions.",
    onset_days=1,
    save_ability="constitution",
    stages=[
        AfflictionStage(
            name="Incubation",
            effects=[AfflictionEffect(EffectType.NARRATIVE, description="Headaches and dizziness")],
            duration_days=1,
            save_dc=13
        ),
        AfflictionStage(
            name="Advanced",
            effects=[
                AfflictionEffect(EffectType.INCAPACITATED, description="Incapacitated - seizures prevent action"),
            ],
            duration_days=None,  # Until cured
            save_dc=13
        ),
    ]
))

register_affliction(Affliction(
    id="slimy_doom",
    name="Slimy Doom",
    type=AfflictionType.DISEASE,
    description="A horrific disease that causes the flesh to rot and slough off.",
    onset_days=1,
    save_ability="constitution",
    stages=[
        AfflictionStage(
            name="Incubation",
            effects=[AfflictionEffect(EffectType.NARRATIVE, description="Skin becomes discolored and blisters")],
            duration_days=3,
            save_dc=14
        ),
        AfflictionStage(
            name="Advanced",
            effects=[
                AfflictionEffect(EffectType.DAMAGE, value=7, description="7 (2d6) necrotic damage at end of each long rest"),
                AfflictionEffect(EffectType.MAX_HP_REDUCTION, value=7, description="Maximum HP reduced by 7"),
            ],
            duration_days=7,
            save_dc=14
        ),
    ]
))

# Register DMG poisons
register_affliction(Affliction(
    id="purple_worm_poison",
    name="Purple Worm Poison",
    type=AfflictionType.POISON,
    description="Potent poison from the purple worm, acting quickly.",
    onset_days=0,
    save_ability="constitution",
    stages=[
        AfflictionStage(
            name="Initial",
            effects=[
                AfflictionEffect(EffectType.DAMAGE, value=42, description="42 (12d6) poison damage"),
            ],
            duration_days=1,
            save_dc=19
        ),
    ]
))

register_affliction(Affliction(
    id="assassins_blood",
    name="Assassin's Blood",
    type=AfflictionType.POISON,
    description="A poison that remains in the bloodstream, acting over time.",
    onset_days=0,
    save_ability="constitution",
    stages=[
        AfflictionStage(
            name="Initial",
            effects=[
                AfflictionEffect(EffectType.DAMAGE, value=21, description="21 (6d6) poison damage"),
            ],
            duration_days=1,
            save_dc=13
        ),
    ]
))

register_affliction(Affliction(
    id="essence_of_ether",
    name="Essence of Ether",
    type=AfflictionType.POISON,
    description="A knockout gas that incapacitates victims.",
    onset_days=0,
    save_ability="constitution",
    stages=[
        AfflictionStage(
            name="Unconscious",
            effects=[
                AfflictionEffect(EffectType.UNCONSCIOUS, description="Unconscious for 1 hour"),
            ],
            duration_days=0,  # 1 hour (treated as same day for simplicity)
            save_dc=15
        ),
    ]
))

register_affliction(Affliction(
    id="malice",
    name="Malice",
    type=AfflictionType.POISON,
    description="A poison that causes paranoia and irrational hostility.",
    onset_days=0,
    save_ability="constitution",
    stages=[
        AfflictionStage(
            name="Psychotic",
            effects=[
                AfflictionEffect(EffectType.CONDITION, value="charmed", description="Charmed by the poisoner"),
                AfflictionEffect(EffectType.DISADVANTAGE_ATTACKS, description="Disadvantage on attack rolls against creatures other than poisoner"),
            ],
            duration_days=1,
            save_dc=15
        ),
    ]
))

register_affliction(Affliction(
    id="burnt_othertears",
    name="Burnt Othertears",
    type=AfflictionType.POISON,
    description="A contact poison that causes painful burning and necrosis.",
    onset_days=0,
    save_ability="constitution",
    stages=[
        AfflictionStage(
            name="Burning",
            effects=[
                AfflictionEffect(EffectType.DAMAGE, value=21, description="21 (6d6) poison damage"),
                AfflictionEffect(EffectType.CONDITION, value="poisoned", description="Poisoned condition"),
            ],
            duration_days=1,
            save_dc=16
        ),
    ]
))

register_affliction(Affliction(
    id="dragon_bile",
    name="Dragon Bile",
    type=AfflictionType.POISON,
    description="A potent acidic poison from dragons.",
    onset_days=0,
    save_ability="constitution",
    stages=[
        AfflictionStage(
            name="Acidic",
            effects=[
                AfflictionEffect(EffectType.DAMAGE, value=28, description="28 (8d6) poison damage"),
                AfflictionEffect(EffectType.CONDITION, value="poisoned", description="Poisoned condition"),
            ],
            duration_days=1,
            save_dc=18
        ),
    ]
))


# ============================================================================
# HELPERS FOR DM CONTEXT AND UI
# ============================================================================

def affliction_summary(active_affliction: ActiveAffliction) -> str:
    """Generate a one-line summary of an active affliction for DM context."""
    if active_affliction.is_onset:
        return f"{active_affliction.affliction.name} (onset: day {active_affliction.days_since_onset}/{active_affliction.affliction.onset_days})"
    
    stage = active_affliction.current_stage
    if stage:
        return f"{active_affliction.affliction.name} ({stage.name}, day {active_affliction.days_in_stage}{f'/{stage.duration_days}' if stage.duration_days else ''})"
    return active_affliction.affliction.name


def get_affliction_effects_for_combat(affliction_status: AfflictionStatus) -> Dict[str, Any]:
    """
    Get combat-relevant effects from afflictions.
    Returns a dict of modifiers for combat resolution.
    """
    effects = {
        "disadvantage_attacks": False,
        "disadvantage_saves": False,
        "max_hp_reduction": 0,
        "incapacitated": False,
    }
    
    for affliction in affliction_status.active_afflictions:
        for effect in affliction.get_active_effects():
            if effect.type == EffectType.DISADVANTAGE_ATTACKS:
                effects["disadvantage_attacks"] = True
            elif effect.type == EffectType.DISADVANTAGE_SAVES:
                effects["disadvantage_saves"] = True
            elif effect.type == EffectType.MAX_HP_REDUCTION and isinstance(effect.value, int):
                effects["max_hp_reduction"] += effect.value
            elif effect.type == EffectType.INCAPACITATED:
                effects["incapacitated"] = True
    
    return effects


def affliction_effects_breakdown(affliction_status: AfflictionStatus) -> List[Dict[str, Any]]:
    """
    Get a detailed breakdown of all affliction effects for UI display.
    """
    breakdown = []
    
    for affliction in affliction_status.active_afflictions:
        if affliction.is_onset:
            continue
        
        stage = affliction.current_stage
        if not stage:
            continue
        
        affliction_info = {
            "affliction_name": affliction.affliction.name,
            "affliction_id": affliction.affliction_id,
            "stage_name": stage.name,
            "days_in_stage": affliction.days_in_stage,
            "stage_duration": stage.duration_days,
            "save_dc": stage.save_dc,
            "save_ability": affliction.affliction.save_ability,
            "effects": []
        }
        
        for effect in stage.effects:
            affliction_info["effects"].append({
                "type": effect.type.value,
                "value": effect.value,
                "description": effect.description
            })
        
        breakdown.append(affliction_info)
    
    return breakdown