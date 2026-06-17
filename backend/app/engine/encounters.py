"""
Encounter Difficulty / CR Balancing engine.

Implements DnD 5e encounter building rules:
- Challenge Rating (CR) to XP conversion
- XP budget thresholds per level (easy/medium/hard/deadly)
- Encounter difficulty calculation
- Multipliers for groups of enemies
- Recommendations for enemy counts based on party level

This engine is pure (no DB, no LLM) and fully unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# CR to XP mapping (DnD 5e DMG, page 274)
# Fractional CRs are represented as decimals
CR_TO_XP = {
    0: 10,
    1/8: 25,
    1/4: 50,
    1/2: 100,
    1: 200,
    2: 450,
    3: 700,
    4: 1100,
    5: 1800,
    6: 2300,
    7: 2900,
    8: 3900,
    9: 5000,
    10: 5900,
    11: 7200,
    12: 8400,
    13: 10000,
    14: 11500,
    15: 13000,
    16: 15000,
    17: 18000,
    18: 20000,
    19: 22000,
    20: 25000,
    21: 33000,
    22: 41000,
    23: 50000,
    24: 62000,
    25: 75000,
    26: 90000,
    27: 105000,
    28: 120000,
    29: 135000,
    30: 155000,
}


def cr_to_xp(cr: float) -> int:
    """Convert Challenge Rating to XP value."""
    # Normalize fractional CRs to match dictionary keys
    if cr in CR_TO_XP:
        return CR_TO_XP[cr]
    # For CRs not in our table (shouldn't happen with valid 5e monsters),
    # approximate using linear interpolation between known values
    sorted_crs = sorted(CR_TO_XP.keys())
    if cr <= sorted_crs[0]:
        return CR_TO_XP[sorted_crs[0]]
    if cr >= sorted_crs[-1]:
        return CR_TO_XP[sorted_crs[-1]]
    
    # Find the bracket and interpolate
    for i in range(len(sorted_crs) - 1):
        if sorted_crs[i] <= cr <= sorted_crs[i + 1]:
            lower_cr = sorted_crs[i]
            upper_cr = sorted_crs[i + 1]
            lower_xp = CR_TO_XP[lower_cr]
            upper_xp = CR_TO_XP[upper_cr]
            # Linear interpolation
            ratio = (cr - lower_cr) / (upper_cr - lower_cr) if upper_cr != lower_cr else 0
            return int(lower_xp + ratio * (upper_xp - lower_xp))
    
    return 0


# XP thresholds per character level (DnD 5e DMG, page 82)
# Columns: [Easy, Medium, Hard, Deadly]
XP_THRESHOLDS = {
    1: [25, 50, 75, 100],
    2: [50, 100, 150, 200],
    3: [75, 150, 225, 400],
    4: [125, 250, 375, 500],
    5: [250, 500, 750, 1100],
    6: [300, 600, 900, 1400],
    7: [350, 750, 1100, 1700],
    8: [450, 900, 1400, 2100],
    9: [550, 1100, 1600, 2400],
    10: [600, 1200, 1900, 2800],
    11: [800, 1600, 2400, 3600],
    12: [1000, 2000, 3000, 4500],
    13: [1100, 2200, 3400, 5100],
    14: [1250, 2500, 3800, 5700],
    15: [1400, 2800, 4300, 6400],
    16: [1600, 3200, 4800, 7200],
    17: [2000, 3900, 5900, 8800],
    18: [2100, 4200, 6300, 9500],
    19: [2400, 4900, 7300, 10900],
    20: [2800, 5700, 8500, 12700],
}


# Multipliers for groups of enemies (DnD 5e DMG, page 82)
# Adjusted XP = Sum of individual XP × Multiplier
GROUP_MULTIPLIERS = {
    1: 1.0,
    2: 1.5,
    3: 2.0,
    4: 2.0,
    5: 2.5,
    6: 2.5,
    7: 3.0,
    8: 3.0,
    9: 3.5,
    10: 3.5,
    11: 4.0,
    12: 4.0,
    13: 4.5,
    14: 4.5,
    15: 5.0,
}


def get_group_multiplier(num_enemies: int) -> float:
    """Get the XP multiplier for a group of enemies."""
    if num_enemies <= 0:
        return 1.0
    if num_enemies >= 15:
        return 5.0  # Cap at the highest multiplier
    return GROUP_MULTIPLIERS.get(num_enemies, 1.0)


def calculate_party_xp_budget(
    party_levels: list[int],
    difficulty: str = "medium"
) -> int:
    """Calculate the total XP budget for a party at a given difficulty.
    
    Args:
        party_levels: List of each party member's level
        difficulty: One of "easy", "medium", "hard", "deadly"
    
    Returns:
        Total XP budget for the encounter
    """
    difficulty = difficulty.lower()
    difficulty_index = {
        "easy": 0,
        "medium": 1,
        "hard": 2,
        "deadly": 3,
    }.get(difficulty, 1)
    
    total_budget = 0
    for level in party_levels:
        if level in XP_THRESHOLDS:
            total_budget += XP_THRESHOLDS[level][difficulty_index]
    
    return total_budget


@dataclass
class EnemyTemplate:
    """A monster or enemy template with its CR and basic stats."""
    name: str
    cr: float
    xp_value: int = field(init=False)
    armor_class: int = 10
    hp: int = 10
    attack_bonus: int = 0
    damage_dice: str = "1d6"
    
    def __post_init__(self):
        self.xp_value = cr_to_xp(self.cr)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for combat API."""
        return {
            "name": self.name,
            "max_hp": self.hp,
            "armor_class": self.armor_class,
            "initiative_bonus": 0,
            "speed": 30,
            "attacks": [
                {
                    "name": f"{self.name} Attack",
                    "attack_bonus": self.attack_bonus,
                    "damage_dice_count": 1,
                    "damage_dice_sides": 6,  # Simplified; would parse from damage_dice
                    "damage_bonus": 0,
                    "damage_type": "slashing",
                }
            ],
        }


@dataclass
class EncounterBudget:
    """The calculated XP budget and recommendations for an encounter."""
    total_budget: int
    easy_budget: int
    medium_budget: int
    hard_budget: int
    deadly_budget: int
    party_size: int
    party_level: int  # Average level
    recommended_enemies: dict[str, list[int]] = field(default_factory=dict)
    # Maps difficulty to list of (count, enemy_name) tuples
    
    def to_dict(self) -> dict:
        return {
            "total_budget": self.total_budget,
            "easy_budget": self.easy_budget,
            "medium_budget": self.medium_budget,
            "hard_budget": self.hard_budget,
            "deadly_budget": self.deadly_budget,
            "party_size": self.party_size,
            "party_level": self.party_level,
            "recommended_enemies": self.recommended_enemies,
        }


@dataclass
class EncounterDifficulty:
    """Analysis of an encounter's difficulty."""
    difficulty: str  # "easy", "medium", "hard", "deadly", "impossible"
    adjusted_xp: int
    raw_xp: int
    xp_budget: int
    party_size: int
    party_level: int
    multiplier: float
    description: str
    
    def to_dict(self) -> dict:
        return {
            "difficulty": self.difficulty,
            "adjusted_xp": self.adjusted_xp,
            "raw_xp": self.raw_xp,
            "xp_budget": self.xp_budget,
            "party_size": self.party_size,
            "party_level": self.party_level,
            "multiplier": self.multiplier,
            "description": self.description,
        }


def calculate_encounter_difficulty(
    enemies: list[dict],
    party_levels: list[int],
    target_difficulty: str = "medium"
) -> EncounterDifficulty:
    """Calculate the difficulty of an encounter.
    
    Args:
        enemies: List of enemy dicts, each with 'cr' and optionally 'name'
        party_levels: List of party member levels
        target_difficulty: The difficulty we're comparing against ("medium" by default)
    
    Returns:
        EncounterDifficulty analysis
    """
    if not enemies:
        return EncounterDifficulty(
            difficulty="trivial",
            adjusted_xp=0,
            raw_xp=0,
            xp_budget=0,
            party_size=len(party_levels),
            party_level=sum(party_levels) // len(party_levels) if party_levels else 1,
            multiplier=1.0,
            description="No enemies - not an encounter.",
        )
    
    # Calculate raw XP sum
    raw_xp = 0
    for enemy in enemies:
        cr = enemy.get("cr", 0)
        raw_xp += cr_to_xp(cr)
    
    # Apply group multiplier
    multiplier = get_group_multiplier(len(enemies))
    adjusted_xp = int(raw_xp * multiplier)
    
    # Get party info
    party_size = len(party_levels)
    party_level = sum(party_levels) // party_size if party_levels else 1
    
    # Get XP budgets for each difficulty
    budgets = {
        "easy": calculate_party_xp_budget(party_levels, "easy"),
        "medium": calculate_party_xp_budget(party_levels, "medium"),
        "hard": calculate_party_xp_budget(party_levels, "hard"),
        "deadly": calculate_party_xp_budget(party_levels, "deadly"),
    }
    
    # Determine difficulty
    difficulty = "unknown"
    target_budget = budgets.get(target_difficulty, budgets["medium"])
    
    if adjusted_xp <= budgets["easy"]:
        difficulty = "easy"
    elif adjusted_xp <= budgets["medium"]:
        difficulty = "medium"
    elif adjusted_xp <= budgets["hard"]:
        difficulty = "hard"
    elif adjusted_xp <= budgets["deadly"]:
        difficulty = "deadly"
    else:
        difficulty = "impossible"
    
    # Build description
    enemy_names = [e.get("name", f"CR {e.get('cr', 0)}") for e in enemies]
    enemies_str = ", ".join(enemy_names[:3])
    if len(enemy_names) > 3:
        enemies_str += f" and {len(enemy_names) - 3} more"
    
    description = (
        f"A party of {party_size} level {party_level} adventurers "
        f"faces {enemies_str}. "
        f"Raw XP: {raw_xp}, Adjusted XP (×{multiplier}): {adjusted_xp}. "
        f"This is a {difficulty.upper()} encounter "
        f"(budget for {target_difficulty}: {target_budget} XP)."
    )
    
    return EncounterDifficulty(
        difficulty=difficulty,
        adjusted_xp=adjusted_xp,
        raw_xp=raw_xp,
        xp_budget=target_budget,
        party_size=party_size,
        party_level=party_level,
        multiplier=multiplier,
        description=description,
    )


def build_encounter_budget(
    party_levels: list[int],
    difficulty: str = "medium"
) -> EncounterBudget:
    """Build an encounter budget with recommendations for enemy counts.
    
    Args:
        party_levels: List of party member levels
        difficulty: The target difficulty ("easy", "medium", "hard", "deadly")
    
    Returns:
        EncounterBudget with recommendations
    """
    party_size = len(party_levels)
    party_level = sum(party_levels) // party_size if party_levels else 1
    
    # Calculate budgets for all difficulties
    easy_budget = calculate_party_xp_budget(party_levels, "easy")
    medium_budget = calculate_party_xp_budget(party_levels, "medium")
    hard_budget = calculate_party_xp_budget(party_levels, "hard")
    deadly_budget = calculate_party_xp_budget(party_levels, "deadly")
    
    total_budget = calculate_party_xp_budget(party_levels, difficulty)
    
    # Build recommendations
    recommendations = {
        "easy": _recommend_enemies(easy_budget, party_level),
        "medium": _recommend_enemies(medium_budget, party_level),
        "hard": _recommend_enemies(hard_budget, party_level),
        "deadly": _recommend_enemies(deadly_budget, party_level),
    }
    
    return EncounterBudget(
        total_budget=total_budget,
        easy_budget=easy_budget,
        medium_budget=medium_budget,
        hard_budget=hard_budget,
        deadly_budget=deadly_budget,
        party_size=party_size,
        party_level=party_level,
        recommended_enemies=recommendations,
    )


def _recommend_enemies(budget: int, party_level: int) -> list[int]:
    """Generate recommendations for enemy counts at various CRs.
    
    Returns a list where index i represents how many enemies of CR i can fit.
    CRs are: 0, 1/8, 1/4, 1/2, 1, 2, 3, 4, 5, 6, 7, 8+
    """
    # Simplified: recommend a mix of enemies at different CRs
    # For now, just recommend a single CR level that fits
    recommendations = []
    
    # CRs that are reasonable for this party level (±2 levels)
    min_cr = max(0, party_level - 3)
    max_cr = min(party_level + 2, 8)
    
    for cr in [0, 1/8, 1/4, 1/2, 1, 2, 3, 4, 5, 6, 7, 8]:
        if cr < min_cr or cr > max_cr:
            recommendations.append(0)
            continue
        
        xp_per_enemy = cr_to_xp(cr)
        if xp_per_enemy == 0:
            recommendations.append(0)
            continue
        
        # Try to fit 1-5 enemies, accounting for multiplier
        best_count = 0
        for count in range(1, 6):
            raw_xp = xp_per_enemy * count
            multiplier = get_group_multiplier(count)
            adjusted_xp = int(raw_xp * multiplier)
            
            if adjusted_xp <= budget:
                best_count = count
            else:
                break
        
        recommendations.append(best_count)
    
    return recommendations


# Common enemy templates for quick reference
COMMON_ENEMIES = {
    # CR 0 (10 XP)
    "Crate": EnemyTemplate(name="Crate", cr=0, armor_class=10, hp=5, attack_bonus=0),
    "Rat": EnemyTemplate(name="Rat", cr=0, armor_class=10, hp=1, attack_bonus=0),
    
    # CR 1/8 (25 XP)
    "Goblin": EnemyTemplate(name="Goblin", cr=1/8, armor_class=15, hp=7, attack_bonus=4),
    "Skeleton": EnemyTemplate(name="Skeleton", cr=1/8, armor_class=13, hp=13, attack_bonus=4),
    
    # CR 1/4 (50 XP)
    "Giant Rat": EnemyTemplate(name="Giant Rat", cr=1/4, armor_class=12, hp=7, attack_bonus=4),
    "Kobold": EnemyTemplate(name="Kobold", cr=1/4, armor_class=12, hp=5, attack_bonus=4),
    
    # CR 1/2 (100 XP)
    "Bandit": EnemyTemplate(name="Bandit", cr=1/2, armor_class=12, hp=11, attack_bonus=3),
    "Giant Wolf Spider": EnemyTemplate(name="Giant Wolf Spider", cr=1/2, armor_class=13, hp=26, attack_bonus=4),
    
    # CR 1 (200 XP)
    "Bugbear": EnemyTemplate(name="Bugbear", cr=1, armor_class=16, hp=27, attack_bonus=4),
    "Dire Wolf": EnemyTemplate(name="Dire Wolf", cr=1, armor_class=14, hp=37, attack_bonus=5),
    
    # CR 2 (450 XP)
    "Ogre": EnemyTemplate(name="Ogre", cr=2, armor_class=11, hp=59, attack_bonus=7),
    "Gelatinous Cube": EnemyTemplate(name="Gelatinous Cube", cr=2, armor_class=6, hp=84, attack_bonus=4),
    
    # CR 3 (700 XP)
    "Owlbear": EnemyTemplate(name="Owlbear", cr=3, armor_class=13, hp=59, attack_bonus=7),
    "Minotaur": EnemyTemplate(name="Minotaur", cr=3, armor_class=14, hp=76, attack_bonus=6),
    
    # CR 4 (1100 XP)
    "Young Red Dragon": EnemyTemplate(name="Young Red Dragon", cr=4, armor_class=18, hp=75, attack_bonus=7),
    "Wight": EnemyTemplate(name="Wight", cr=4, armor_class=14, hp=45, attack_bonus=4),
    
    # CR 5 (1800 XP)
    "Hill Giant": EnemyTemplate(name="Hill Giant", cr=5, armor_class=13, hp=105, attack_bonus=8),
    "Werewolf": EnemyTemplate(name="Werewolf", cr=5, armor_class=14, hp=58, attack_bonus=7),
}


def get_enemy_template(name: str) -> Optional[EnemyTemplate]:
    """Get an enemy template by name."""
    return COMMON_ENEMIES.get(name)


def list_enemy_templates() -> list[str]:
    """List all available enemy template names."""
    return sorted(COMMON_ENEMIES.keys())


def get_enemies_by_cr(cr: float) -> list[EnemyTemplate]:
    """Get all enemies of a specific CR."""
    return [e for e in COMMON_ENEMIES.values() if e.cr == cr]