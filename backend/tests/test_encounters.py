"""
Tests for the encounters engine (CR/XP balancing).

Tests cover:
- CR to XP conversion
- XP budget calculations
- Group multipliers
- Encounter difficulty analysis
- Encounter budget building
- Enemy templates
"""
import pytest

from app.engine.encounters import (
    cr_to_xp,
    CR_TO_XP,
    XP_THRESHOLDS,
    GROUP_MULTIPLIERS,
    get_group_multiplier,
    calculate_party_xp_budget,
    EnemyTemplate,
    EncounterBudget,
    EncounterDifficulty,
    calculate_encounter_difficulty,
    build_encounter_budget,
    get_enemy_template,
    list_enemy_templates,
    get_enemies_by_cr,
    COMMON_ENEMIES,
)


class TestCRToXP:
    """Test CR to XP conversion."""
    
    def test_cr_zero(self):
        assert cr_to_xp(0) == 10
    
    def test_cr_one_eighth(self):
        assert cr_to_xp(0.125) == 25
    
    def test_cr_one_quarter(self):
        assert cr_to_xp(0.25) == 50
    
    def test_cr_one_half(self):
        assert cr_to_xp(0.5) == 100
    
    def test_cr_one(self):
        assert cr_to_xp(1) == 200
    
    def test_cr_five(self):
        assert cr_to_xp(5) == 1800
    
    def test_cr_ten(self):
        assert cr_to_xp(10) == 5900
    
    def test_cr_twenty(self):
        assert cr_to_xp(20) == 25000
    
    def test_all_standard_crs(self):
        """Verify all standard CRs have entries."""
        for cr in [0, 0.125, 0.25, 0.5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
            assert cr in CR_TO_XP
            assert cr_to_xp(cr) == CR_TO_XP[cr]
    
    def test_fractional_cr_lookup(self):
        """Test that fractional CRs are looked up correctly."""
        # Direct lookup should work
        assert cr_to_xp(0.125) == 25
        assert cr_to_xp(0.25) == 50
        assert cr_to_xp(0.5) == 100


class TestXPThresholds:
    """Test XP thresholds per level."""
    
    def test_level_one_thresholds(self):
        assert 1 in XP_THRESHOLDS
        easy, medium, hard, deadly = XP_THRESHOLDS[1]
        assert easy == 25
        assert medium == 50
        assert hard == 75
        assert deadly == 100
    
    def test_level_five_thresholds(self):
        easy, medium, hard, deadly = XP_THRESHOLDS[5]
        assert easy == 250
        assert medium == 500
        assert hard == 750
        assert deadly == 1100
    
    def test_level_ten_thresholds(self):
        easy, medium, hard, deadly = XP_THRESHOLDS[10]
        assert easy == 600
        assert medium == 1200
        assert hard == 1900
        assert deadly == 2800
    
    def test_level_twenty_thresholds(self):
        easy, medium, hard, deadly = XP_THRESHOLDS[20]
        assert easy == 2800
        assert medium == 5700
        assert hard == 8500
        assert deadly == 12700
    
    def test_all_levels_one_to_twenty(self):
        """Verify all levels 1-20 have thresholds."""
        for level in range(1, 21):
            assert level in XP_THRESHOLDS
            thresholds = XP_THRESHOLDS[level]
            assert len(thresholds) == 4
            # Thresholds should increase with difficulty
            assert thresholds[0] < thresholds[1] < thresholds[2] < thresholds[3]


class TestGroupMultipliers:
    """Test group size multipliers."""
    
    def test_single_enemy(self):
        assert get_group_multiplier(1) == 1.0
    
    def test_two_enemies(self):
        assert get_group_multiplier(2) == 1.5
    
    def test_three_enemies(self):
        assert get_group_multiplier(3) == 2.0
    
    def test_four_enemies(self):
        assert get_group_multiplier(4) == 2.0
    
    def test_five_enemies(self):
        assert get_group_multiplier(5) == 2.5
    
    def test_ten_enemies(self):
        assert get_group_multiplier(10) == 3.5
    
    def test_fifteen_plus_enemies(self):
        # Should cap at 5.0
        assert get_group_multiplier(15) == 5.0
        assert get_group_multiplier(20) == 5.0
        assert get_group_multiplier(100) == 5.0
    
    def test_zero_enemies(self):
        # Should default to 1.0
        assert get_group_multiplier(0) == 1.0


class TestPartyXPBudget:
    """Test party XP budget calculations."""
    
    def test_single_character_level_one_easy(self):
        budget = calculate_party_xp_budget([1], "easy")
        assert budget == 25
    
    def test_single_character_level_five_medium(self):
        budget = calculate_party_xp_budget([5], "medium")
        assert budget == 500
    
    def test_party_of_four_level_one(self):
        # 4 characters × 50 XP each (medium) = 200 XP
        budget = calculate_party_xp_budget([1, 1, 1, 1], "medium")
        assert budget == 200
    
    def test_party_of_four_level_five_hard(self):
        # 4 characters × 750 XP each (hard) = 3000 XP
        budget = calculate_party_xp_budget([5, 5, 5, 5], "hard")
        assert budget == 3000
    
    def test_mixed_levels(self):
        # Level 3 medium = 150, Level 4 medium = 250
        # Total = 150 + 150 + 250 = 550 XP
        budget = calculate_party_xp_budget([3, 3, 4], "medium")
        assert budget == 550
    
    def test_invalid_difficulty_defaults_to_medium(self):
        budget = calculate_party_xp_budget([1], "invalid")
        # Should default to medium (50 XP for level 1)
        assert budget == 50
    
    def test_all_difficulties_same_party(self):
        party = [3, 3, 4]
        easy = calculate_party_xp_budget(party, "easy")
        medium = calculate_party_xp_budget(party, "medium")
        hard = calculate_party_xp_budget(party, "hard")
        deadly = calculate_party_xp_budget(party, "deadly")
        
        # easy = 75+75+125 = 275, medium = 150+150+250 = 550, hard = 225+225+400 = 850, deadly = 400+400+570 = 1370
        assert easy < medium < hard < deadly
        # easy is 1/2 of medium for level 3
        assert easy * 2 == medium


class TestEnemyTemplate:
    """Test enemy template dataclass."""
    
    def test_create_template(self):
        template = EnemyTemplate(
            name="Test Goblin",
            cr=0.125,
            armor_class=15,
            hp=7,
            attack_bonus=4,
        )
        assert template.name == "Test Goblin"
        assert template.cr == 0.125
        assert template.xp_value == 25  # Auto-calculated from CR
        assert template.armor_class == 15
        assert template.hp == 7
        assert template.attack_bonus == 4
    
    def test_template_to_dict(self):
        template = EnemyTemplate(
            name="Test",
            cr=1,
            armor_class=12,
            hp=10,
            attack_bonus=3,
        )
        data = template.to_dict()
        
        assert data["name"] == "Test"
        assert data["max_hp"] == 10
        assert data["armor_class"] == 12
        assert "attacks" in data
        assert len(data["attacks"]) == 1
        assert data["attacks"][0]["name"] == "Test Attack"


class TestEncounterDifficulty:
    """Test encounter difficulty calculation."""
    
    def test_single_cr_one_enemy_vs_level_one_party(self):
        difficulty = calculate_encounter_difficulty(
            enemies=[{"cr": 1, "name": "Bugbear"}],
            party_levels=[1, 1, 1, 1],
            target_difficulty="medium",
        )
        
        assert difficulty.party_size == 4
        assert difficulty.party_level == 1
        assert difficulty.raw_xp == 200  # CR 1 = 200 XP
        assert difficulty.multiplier == 1.0  # Single enemy
        assert difficulty.adjusted_xp == 200
        
        # For level 1 party of 4, medium budget is 200 XP
        # So this is exactly a medium encounter
        assert difficulty.difficulty == "medium"
    
    def test_multiple_goblins_vs_level_one_party(self):
        difficulty = calculate_encounter_difficulty(
            enemies=[
                {"cr": 0.125, "name": "Goblin"},
                {"cr": 0.125, "name": "Goblin"},
                {"cr": 0.125, "name": "Goblin"},
            ],
            party_levels=[1, 1, 1],
            target_difficulty="medium",
        )
        
        assert difficulty.party_size == 3
        assert difficulty.raw_xp == 75  # 3 × 25 XP
        assert difficulty.multiplier == 2.0  # 3 enemies
        assert difficulty.adjusted_xp == 150
        
        # For level 1 party of 3, medium budget is 150 XP
        # So this is exactly a medium encounter
        assert difficulty.difficulty == "medium"
    
    def test_empty_encounter(self):
        difficulty = calculate_encounter_difficulty(
            enemies=[],
            party_levels=[3, 3, 4],
            target_difficulty="medium",
        )
        
        assert difficulty.difficulty == "trivial"
        assert difficulty.adjusted_xp == 0
        assert difficulty.raw_xp == 0
    
    def test_impossible_encounter(self):
        # A CR 10 enemy against level 1 party
        difficulty = calculate_encounter_difficulty(
            enemies=[{"cr": 10, "name": "Ancient Dragon"}],
            party_levels=[1, 1, 1, 1],
            target_difficulty="medium",
        )
        
        assert difficulty.difficulty == "impossible"
        assert difficulty.raw_xp == 5900
    
    def test_easy_encounter(self):
        # CR 1/2 enemy vs level 5 party
        difficulty = calculate_encounter_difficulty(
            enemies=[{"cr": 0.5, "name": "Bandit"}],
            party_levels=[5, 5, 5, 5],
            target_difficulty="medium",
        )
        
        assert difficulty.difficulty == "easy"
    
    def test_deadly_encounter(self):
        # CR 4 enemy (1100 XP) vs level 3-3-4 party (deadly budget = 1300 XP)
        difficulty = calculate_encounter_difficulty(
            enemies=[{"cr": 4, "name": "Young Red Dragon"}],
            party_levels=[3, 3, 4],
            target_difficulty="medium",
        )
        
        # CR 4 = 1100 XP, deadly budget for level 3-3-4 = 1300 XP, so this is deadly
        assert difficulty.difficulty == "deadly"
    
    def test_difficulty_dict_conversion(self):
        difficulty = calculate_encounter_difficulty(
            enemies=[{"cr": 1, "name": "Bugbear"}],
            party_levels=[2, 2, 2],
            target_difficulty="medium",
        )
        
        data = difficulty.to_dict()
        assert "difficulty" in data
        assert "adjusted_xp" in data
        assert "description" in data
        assert data["party_size"] == 3


class TestEncounterBudget:
    """Test encounter budget building."""
    
    def test_build_budget_for_party(self):
        budget = build_encounter_budget(
            party_levels=[3, 3, 4],
            difficulty="medium",
        )
        
        assert budget.party_size == 3
        assert budget.party_level == 3  # Average
        assert budget.easy_budget > 0
        assert budget.medium_budget > 0
        assert budget.hard_budget > 0
        assert budget.deadly_budget > 0
        assert budget.easy_budget < budget.medium_budget < budget.hard_budget < budget.deadly_budget
    
    def test_budget_includes_recommendations(self):
        budget = build_encounter_budget(
            party_levels=[5, 5, 5, 5],
            difficulty="medium",
        )
        
        assert "easy" in budget.recommended_enemies
        assert "medium" in budget.recommended_enemies
        assert "hard" in budget.recommended_enemies
        assert "deadly" in budget.recommended_enemies
        
        # Each should have a list of recommendations
        assert isinstance(budget.recommended_enemies["easy"], list)
    
    def test_budget_for_single_character(self):
        budget = build_encounter_budget(
            party_levels=[1],
            difficulty="medium",
        )
        
        assert budget.party_size == 1
        assert budget.party_level == 1
        assert budget.medium_budget == 50  # Level 1 medium
    
    def test_budget_dict_conversion(self):
        budget = build_encounter_budget(
            party_levels=[2, 3],
            difficulty="hard",
        )
        
        data = budget.to_dict()
        assert "party_size" in data
        assert "party_level" in data
        assert "medium_budget" in data
        assert "recommended_enemies" in data


class TestEnemyTemplates:
    """Test the common enemy templates."""
    
    def test_common_enemies_exist(self):
        assert "Goblin" in COMMON_ENEMIES
        assert "Skeleton" in COMMON_ENEMIES
        assert "Bugbear" in COMMON_ENEMIES
        assert "Ogre" in COMMON_ENEMIES
        assert "Hill Giant" in COMMON_ENEMIES
    
    def test_get_enemy_template(self):
        goblin = get_enemy_template("Goblin")
        assert goblin is not None
        assert goblin.name == "Goblin"
        assert goblin.cr == 0.125
        assert goblin.xp_value == 25
    
    def test_get_nonexistent_template(self):
        template = get_enemy_template("NonexistentMonster")
        assert template is None
    
    def test_list_enemy_templates(self):
        templates = list_enemy_templates()
        assert isinstance(templates, list)
        assert len(templates) > 0
        assert "Goblin" in templates
        assert "Ogre" in templates
    
    def test_get_enemies_by_cr(self):
        cr_one_quarter = get_enemies_by_cr(0.25)
        assert isinstance(cr_one_quarter, list)
        assert all(e.cr == 0.25 for e in cr_one_quarter)
    
    def test_goblin_template_stats(self):
        goblin = get_enemy_template("Goblin")
        assert goblin.armor_class == 15
        assert goblin.hp == 7
        assert goblin.attack_bonus == 4
    
    def test_ogre_template_stats(self):
        ogre = get_enemy_template("Ogre")
        assert ogre.cr == 2
        assert ogre.xp_value == 450
        assert ogre.armor_class == 11
        assert ogre.hp == 59
        assert ogre.attack_bonus == 7


class TestComplexScenarios:
    """Test realistic encounter scenarios."""
    
    def test_goblin_squad_vs_level_one_party(self):
        # 5 goblins (CR 1/8 each) vs 4 level 1 PCs
        # Raw: 5 × 25 = 125 XP
        # Multiplier for 5 enemies: 2.5x
        # Adjusted: 125 × 2.5 = 312.5 ≈ 312 XP
        # Budget for level 1 party of 4, medium: 200 XP
        # This should be deadly
        difficulty = calculate_encounter_difficulty(
            enemies=[
                {"cr": 0.125, "name": "Goblin"} for _ in range(5)
            ],
            party_levels=[1, 1, 1, 1],
            target_difficulty="medium",
        )
        
        assert difficulty.difficulty == "deadly"
    
    def test_bugbear_vs_level_three_party(self):
        # 1 bugbear (CR 1, 200 XP) vs 4 level 3 PCs
        # Budget for level 3 party of 4, medium: 4 × 150 = 600 XP
        # This should be easy
        difficulty = calculate_encounter_difficulty(
            enemies=[{"cr": 1, "name": "Bugbear"}],
            party_levels=[3, 3, 3, 3],
            target_difficulty="medium",
        )
        
        assert difficulty.difficulty == "easy"
    
    def test_ogre_gang_vs_level_five_party(self):
        # 3 ogres (CR 2 each, 450 XP) vs 4 level 5 PCs
        # Raw: 3 × 450 = 1350 XP
        # Multiplier for 3 enemies: 2.0x
        # Adjusted: 1350 × 2.0 = 2700 XP
        # Budget for level 5 party of 4, medium: 4 × 500 = 2000 XP
        # Budget for level 5 party of 4, hard: 4 × 750 = 3000 XP
        # This should be hard
        difficulty = calculate_encounter_difficulty(
            enemies=[
                {"cr": 2, "name": "Ogre"} for _ in range(3)
            ],
            party_levels=[5, 5, 5, 5],
            target_difficulty="medium",
        )
        
        assert difficulty.difficulty == "hard"
    
    def test_single_high_cr_vs_party(self):
        # 1 CR 5 enemy (1800 XP) vs 4 level 4 PCs
        # Budget for level 4 party of 4, medium: 4 × 250 = 1000 XP
        # Budget for level 4 party of 4, deadly: 4 × 500 = 2000 XP
        # This should be hard (but not deadly)
        difficulty = calculate_encounter_difficulty(
            enemies=[{"cr": 5, "name": "Hill Giant"}],
            party_levels=[4, 4, 4, 4],
            target_difficulty="medium",
        )
        
        assert difficulty.difficulty in ["hard", "deadly"]