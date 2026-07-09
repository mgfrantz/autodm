"""
Tests for the afflictions engine (diseases and poisons).
"""

import pytest
from app.engine.afflictions import (
    Affliction, AfflictionType, AfflictionStage, AfflictionEffect,
    ActiveAffliction, AfflictionStatus,
    AfflictionAdvanceResult, AfflictionSaveResult,
    EffectType,
    register_affliction, get_affliction, list_afflictions,
    affliction_summary, get_affliction_effects_for_combat,
    affliction_effects_breakdown,
    AFFLICTION_REGISTRY
)


class TestAfflictionEffect:
    """Test AfflictionEffect dataclass."""
    
    def test_effect_creation(self):
        effect = AfflictionEffect(
            type=EffectType.DAMAGE,
            value=5,
            description="5 poison damage"
        )
        assert effect.type == EffectType.DAMAGE
        assert effect.value == 5
        assert effect.description == "5 poison damage"
    
    def test_effect_serialization(self):
        effect = AfflictionEffect(
            type=EffectType.CONDITION,
            value="poisoned",
            description="Poisoned condition"
        )
        data = effect.to_dict()
        assert data["type"] == "condition"
        assert data["value"] == "poisoned"
        assert data["description"] == "Poisoned condition"
        
        # Round-trip
        restored = AfflictionEffect.from_dict(data)
        assert restored.type == effect.type
        assert restored.value == effect.value
        assert restored.description == effect.description


class TestAfflictionStage:
    """Test AfflictionStage dataclass."""
    
    def test_stage_creation(self):
        effects = [
            AfflictionEffect(EffectType.DAMAGE, value=5, description="5 damage"),
            AfflictionEffect(EffectType.CONDITION, value="poisoned", description="Poisoned")
        ]
        stage = AfflictionStage(
            name="Early",
            effects=effects,
            duration_days=3,
            save_dc=13
        )
        assert stage.name == "Early"
        assert len(stage.effects) == 2
        assert stage.duration_days == 3
        assert stage.save_dc == 13
    
    def test_stage_serialization(self):
        effects = [AfflictionEffect(EffectType.DAMAGE, value=10, description="10 damage")]
        stage = AfflictionStage(
            name="Terminal",
            effects=effects,
            duration_days=None,
            save_dc=15
        )
        data = stage.to_dict()
        assert data["name"] == "Terminal"
        assert len(data["effects"]) == 1
        assert data["duration_days"] is None
        assert data["save_dc"] == 15
        
        restored = AfflictionStage.from_dict(data)
        assert restored.name == stage.name
        assert len(restored.effects) == len(stage.effects)


class TestAffliction:
    """Test Affliction dataclass."""
    
    def test_affliction_creation(self):
        stages = [
            AfflictionStage(
                name="Incubation",
                effects=[AfflictionEffect(EffectType.NARRATIVE, description="Onset")],
                duration_days=2,
                save_dc=11
            ),
            AfflictionStage(
                name="Advanced",
                effects=[AfflictionEffect(EffectType.DAMAGE, value=5, description="5 damage")],
                duration_days=5,
                save_dc=13
            )
        ]
        
        affliction = Affliction(
            id="test_disease",
            name="Test Disease",
            type=AfflictionType.DISEASE,
            description="A test disease",
            stages=stages,
            onset_days=1,
            save_ability="constitution"
        )
        
        assert affliction.id == "test_disease"
        assert affliction.name == "Test Disease"
        assert affliction.type == AfflictionType.DISEASE
        assert len(affliction.stages) == 2
        assert affliction.onset_days == 1
        assert affliction.save_ability == "constitution"
    
    def test_affliction_serialization(self):
        stages = [
            AfflictionStage(
                name="Early",
                effects=[AfflictionEffect(EffectType.DAMAGE, value=5)],
                duration_days=3
            )
        ]
        
        affliction = Affliction(
            id="test",
            name="Test",
            type=AfflictionType.POISON,
            description="Test",
            stages=stages,
            onset_days=0
        )
        
        data = affliction.to_dict()
        assert data["id"] == "test"
        assert data["type"] == "poison"
        assert len(data["stages"]) == 1
        
        restored = Affliction.from_dict(data)
        assert restored.id == affliction.id
        assert restored.type == affliction.type


class TestActiveAffliction:
    """Test ActiveAffliction dataclass."""
    
    def setup_method(self):
        """Set up a test affliction."""
        self.stages = [
            AfflictionStage(
                name="Incubation",
                effects=[AfflictionEffect(EffectType.NARRATIVE, description="Onset")],
                duration_days=2,
                save_dc=11
            ),
            AfflictionStage(
                name="Advanced",
                effects=[AfflictionEffect(EffectType.DAMAGE, value=5, description="5 damage")],
                duration_days=5,
                save_dc=13
            )
        ]
        
        self.affliction = Affliction(
            id="test_disease",
            name="Test Disease",
            type=AfflictionType.DISEASE,
            description="A test disease",
            stages=self.stages,
            onset_days=1,
            save_ability="constitution"
        )
    
    def test_active_creation(self):
        active = ActiveAffliction(
            affliction_id="test_disease",
            affliction=self.affliction,
            stage_index=-1,  # Start in onset
            days_in_stage=0,
            days_since_onset=0,
            cured=False
        )
        
        assert active.affliction_id == "test_disease"
        assert active.is_onset is True
        assert active.cured is False
        assert active.is_finished is False
    
    def test_onset_period(self):
        active = ActiveAffliction(
            affliction_id="test_disease",
            affliction=self.affliction,
            stage_index=-1,
            days_in_stage=0,
            days_since_onset=0
        )
        
        # Day 1: Exit onset, enter first stage (onset_days=1, so after 1 day we enter first stage)
        result = active.advance_day()
        assert result.changed is True
        assert result.previous_stage == -1
        assert result.new_stage == 0
        assert active.days_since_onset == 1
        assert active.stage_index == 0
        assert active.is_onset is False
    
    def test_stage_progression(self):
        active = ActiveAffliction(
            affliction_id="test_disease",
            affliction=self.affliction,
            stage_index=0,  # Start in first stage
            days_in_stage=0,
            days_since_onset=2
        )
        
        # Day 1 in stage
        result = active.advance_day()
        assert result.changed is False
        assert active.days_in_stage == 1
        
        # Day 2 in stage - duration_days=2, so this advances to next stage
        result = active.advance_day()
        assert result.changed is True
        assert result.previous_stage == 0
        assert result.new_stage == 1
        assert active.days_in_stage == 0
        assert active.stage_index == 1
    
    def test_save_attempt(self):
        active = ActiveAffliction(
            affliction_id="test_disease",
            affliction=self.affliction,
            stage_index=0,
            days_in_stage=1,
            days_since_onset=2
        )
        
        # Successful save
        result = active.attempt_save(roll=15, modifier=0, treat=False)
        assert result.success is True
        assert result.dc == 11
        assert result.total == 15
        assert active.cured is True
        
        # Reset for next test
        active.cured = False
        active.stage_index = 0
        
        # Failed save
        result = active.attempt_save(roll=5, modifier=0, treat=False)
        assert result.success is False
        assert result.total == 5
        assert active.cured is False
        
        # Failed save with treatment (no advantage in this simple model)
        result = active.attempt_save(roll=8, modifier=0, treat=True)
        assert result.success is False
        assert result.treated is True
    
    def test_no_save_available(self):
        # Create an affliction with no save DC
        no_save_stage = AfflictionStage(
            name="Effect",
            effects=[AfflictionEffect(EffectType.DAMAGE, value=5)],
            duration_days=3,
            save_dc=None
        )
        
        affliction = Affliction(
            id="no_save",
            name="No Save",
            type=AfflictionType.POISON,
            description="No save available",
            stages=[no_save_stage],
            onset_days=0
        )
        
        active = ActiveAffliction(
            affliction_id="no_save",
            affliction=affliction,
            stage_index=0,
            days_in_stage=0,
            days_since_onset=0
        )
        
        result = active.attempt_save(roll=15, modifier=2, treat=False)
        assert result.success is False
        assert result.dc == 0
        assert "no save available" in result.narrative.lower()
    
    def test_get_active_effects(self):
        active = ActiveAffliction(
            affliction_id="test_disease",
            affliction=self.affliction,
            stage_index=0,
            days_in_stage=1,
            days_since_onset=2
        )
        
        effects = active.get_active_effects()
        assert len(effects) == 1
        assert effects[0].type == EffectType.NARRATIVE
        
        # During onset, no effects
        active.stage_index = -1
        effects = active.get_active_effects()
        assert len(effects) == 0


class TestAfflictionStatus:
    """Test AfflictionStatus container."""
    
    def setup_method(self):
        """Set up test afflictions."""
        self.disease = Affliction(
            id="test_disease",
            name="Test Disease",
            type=AfflictionType.DISEASE,
            description="A test",
            stages=[
                AfflictionStage(
                    name="Early",
                    effects=[AfflictionEffect(EffectType.DAMAGE, value=5)],
                    duration_days=3,
                    save_dc=11
                )
            ],
            onset_days=1
        )
        
        self.poison = Affliction(
            id="test_poison",
            name="Test Poison",
            type=AfflictionType.POISON,
            description="A test poison",
            stages=[
                AfflictionStage(
                    name="Effect",
                    effects=[AfflictionEffect(EffectType.DAMAGE, value=10)],
                    duration_days=1,
                    save_dc=13
                )
            ],
            onset_days=0
        )
    
    def test_add_affliction(self):
        status = AfflictionStatus()
        assert status.has_afflictions is False
        
        active = status.add_affliction(self.disease)
        assert active.affliction_id == "test_disease"
        assert status.has_afflictions is True
        assert len(status.active) == 1
    
    def test_get_by_id(self):
        status = AfflictionStatus()
        status.add_affliction(self.disease)
        
        found = status.get_by_id("test_disease")
        assert found is not None
        assert found.affliction.name == "Test Disease"
        
        not_found = status.get_by_id("nonexistent")
        assert not_found is None
    
    def test_advance_multiple_afflictions(self):
        status = AfflictionStatus()
        status.add_affliction(self.disease)
        status.add_affliction(self.poison)
        
        # Advance 2 days
        results = status.advance_days(2)
        
        # Disease: still in onset (1 day onset)
        # Poison: entered first stage
        # Should have some results
        assert len(results) > 0
    
    def test_remove_cured(self):
        status = AfflictionStatus()
        active = status.add_affliction(self.poison)
        
        assert len(status.active) == 1
        
        # Mark as cured
        active.cured = True
        
        status.remove_cured()
        assert len(status.active) == 0
    
    def test_get_all_active_effects(self):
        status = AfflictionStatus()
        status.add_affliction(self.disease)
        status.add_affliction(self.poison)
        
        # Advance past onset for both
        status.advance_days(2)
        
        effects = status.get_all_active_effects()
        # Both should have damage effects now
        damage_effects = [e for e in effects if e.type == EffectType.DAMAGE]
        assert len(damage_effects) >= 1
    
    def test_serialization(self):
        status = AfflictionStatus()
        status.add_affliction(self.disease)
        
        data = status.to_dict()
        assert "active" in data
        assert len(data["active"]) == 1
        
        restored = AfflictionStatus.from_dict(data)
        assert len(restored.active) == 1
        assert restored.active[0].affliction_id == "test_disease"


class TestAfflictionRegistry:
    """Test affliction registry."""
    
    def test_register_and_get(self):
        affliction = Affliction(
            id="registry_test",
            name="Registry Test",
            type=AfflictionType.DISEASE,
            description="Test",
            stages=[],
            onset_days=0
        )
        
        register_affliction(affliction)
        
        found = get_affliction("registry_test")
        assert found is not None
        assert found.name == "Registry Test"
    
    def test_list_all(self):
        all_afflictions = list_afflictions()
        assert len(all_afflictions) > 0
    
    def test_list_by_type(self):
        diseases = list_afflictions(AfflictionType.DISEASE)
        poisons = list_afflictions(AfflictionType.POISON)
        
        assert len(diseases) > 0
        assert len(poisons) > 0
        
        # All should have correct type
        for disease in diseases:
            assert disease.type == AfflictionType.DISEASE
        for poison in poisons:
            assert poison.type == AfflictionType.POISON
    
    def test_known_afflictions(self):
        """Test that the known DMG afflictions are registered."""
        # Check for some known diseases
        cackle_fever = get_affliction("cackle_fever")
        assert cackle_fever is not None
        assert cackle_fever.name == "Cackle Fever"
        assert cackle_fever.type == AfflictionType.DISEASE
        
        # Check for some known poisons
        purple_worm = get_affliction("purple_worm_poison")
        assert purple_worm is not None
        assert purple_worm.name == "Purple Worm Poison"
        assert purple_worm.type == AfflictionType.POISON


class TestDMContextHelpers:
    """Test helpers for DM context and UI."""
    
    def setup_method(self):
        """Set up a test affliction."""
        self.stages = [
            AfflictionStage(
                name="Early",
                effects=[
                    AfflictionEffect(EffectType.DAMAGE, value=5, description="5 damage"),
                    AfflictionEffect(EffectType.DISADVANTAGE_SAVES, description="Disadvantage on saves")
                ],
                duration_days=3,
                save_dc=11
            )
        ]
        
        self.affliction = Affliction(
            id="test",
            name="Test",
            type=AfflictionType.DISEASE,
            description="Test",
            stages=self.stages,
            onset_days=1,
            save_ability="constitution"
        )
    
    def test_affliction_summary(self):
        active = ActiveAffliction(
            affliction_id="test",
            affliction=self.affliction,
            stage_index=-1,
            days_in_stage=0,
            days_since_onset=0
        )
        
        summary = affliction_summary(active)
        assert "Test" in summary
        assert "onset" in summary.lower()
        
        # Advance past onset
        active.advance_day()
        active.advance_day()
        
        summary = affliction_summary(active)
        assert "Test" in summary
        assert "Early" in summary
    
    def test_get_combat_effects(self):
        status = AfflictionStatus()
        active = status.add_affliction(self.affliction)
        
        # Advance past onset
        status.advance_days(2)
        
        effects = get_affliction_effects_for_combat(status)
        assert effects["disadvantage_saves"] is True
    
    def test_effects_breakdown(self):
        status = AfflictionStatus()
        status.add_affliction(self.affliction)
        
        # Advance past onset
        status.advance_days(2)
        
        breakdown = affliction_effects_breakdown(status)
        assert len(breakdown) == 1
        assert breakdown[0]["affliction_name"] == "Test"
        assert breakdown[0]["stage_name"] == "Early"
        assert len(breakdown[0]["effects"]) == 2


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_affliction_with_no_stages(self):
        affliction = Affliction(
            id="no_stages",
            name="No Stages",
            type=AfflictionType.POISON,
            description="No stages",
            stages=[],
            onset_days=0
        )
        
        active = ActiveAffliction(
            affliction_id="no_stages",
            affliction=affliction,
            stage_index=-1,
            days_in_stage=0,
            days_since_onset=0
        )
        
        # Advance past onset - should not crash
        result = active.advance_day()
        assert active.days_since_onset == 1
        
        # Advance again - exits onset but has no stage
        result = active.advance_day()
        assert active.stage_index == 0  # Would point to first non-existent stage
        assert active.current_stage is None
        assert len(active.get_active_effects()) == 0
    
    def test_affliction_with_no_onset(self):
        affliction = Affliction(
            id="no_onset",
            name="No Onset",
            type=AfflictionType.POISON,
            description="Immediate",
            stages=[
                AfflictionStage(
                    name="Effect",
                    effects=[AfflictionEffect(EffectType.DAMAGE, value=10)],
                    duration_days=1,
                    save_dc=13
                )
            ],
            onset_days=0
        )
        
        active = ActiveAffliction(
            affliction_id="no_onset",
            affliction=affliction,
            stage_index=-1,
            days_in_stage=0,
            days_since_onset=0
        )
        
        # Should not be in onset
        assert active.is_onset is False
        assert active.current_stage is None  # -1 points before first stage
        
        # Advance to first stage
        result = active.advance_day()
        assert result.changed is True
        assert active.stage_index == 0
        assert active.current_stage is not None
    
    def test_indefinite_stage_duration(self):
        affliction = Affliction(
            id="indefinite",
            name="Indefinite",
            type=AfflictionType.DISEASE,
            description="Lasts until cured",
            stages=[
                AfflictionStage(
                    name="Chronic",
                    effects=[AfflictionEffect(EffectType.DISADVANTAGE_CHECKS)],
                    duration_days=None,  # Indefinite
                    save_dc=15
                )
            ],
            onset_days=0
        )
        
        active = ActiveAffliction(
            affliction_id="indefinite",
            affliction=affliction,
            stage_index=0,
            days_in_stage=0,
            days_since_onset=0
        )
        
        # Advance many days - should stay in same stage
        for _ in range(10):
            result = active.advance_day()
            assert result.changed is False
            assert active.stage_index == 0
        
        # Save to cure
        result = active.attempt_save(roll=20, modifier=0, treat=False)
        assert result.success is True
        assert active.cured is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])