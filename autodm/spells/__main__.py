from ..core.enums import CharacterClass, SpellSchool
from .base_spell import Spell
from .attack_spell import AttackSpell
from .healing_spell import HealingSpell
from ..core.character import Character
from ..agents.character_agent import CharacterAgent


if __name__ == "__main__":
    caster = CharacterAgent(character=Character.generate(chr_class=CharacterClass.WIZARD))
    target = CharacterAgent(character=Character.generate(chr_class=CharacterClass.FIGHTER))
    spell = AttackSpell(
        name="Fireball",
        level=3,
        school=SpellSchool.EVOCATION,
        casting_time=1,
        range=150,
        components="V, S, M (a tiny ball of bat guano and sulfur)",
        duration="Instantaneous",
        description="A bright streak flashes from your pointing finger to a point you choose within range and then blossoms with a low roar into an explosion of flame.",
        attack_type="ranged",
        damage="1d6",
        classes=["Sorcerer", "Wizard"]
    )

    print("Target HP ", target.character.current_hp)
    result = spell.cast(caster.character, target.character)
    print("Result: ", result)
    print("Target HP ", target.character.current_hp)