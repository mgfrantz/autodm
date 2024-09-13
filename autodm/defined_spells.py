from .spells import AttackSpell, HealingSpell, Spell, SpellSchool

fireball = AttackSpell(
    name="Fireball",
    level=1,
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

cure_wounds = HealingSpell(
    name="Cure Wounds",
    level=1,
    school=SpellSchool.EVOCATION,
    casting_time=1,
    range=5,
    healing_amount='1d6',
    components="V, S",
    duration="Instantaneous",
    description="A creature you touch regains a number of hit points equal to 1d8 + your spellcasting ability modifier.",
    classes=["Bard", "Cleric", "Paladin"]
)

magic_missile = AttackSpell(
    name="Magic Missile",
    level=1,
    school=SpellSchool.EVOCATION,
    casting_time=1,
    range=120,
    components="V, S",
    duration="Instantaneous",
    description="You create three glowing darts of magical force. Each dart hits a creature of your choice that you can see within range.",
    attack_type="ranged",
    damage="1d4+1",
    classes=["Sorcerer", "Wizard"]
)

shield = Spell(
    name="Shield",
    level=1,
    school=SpellSchool.ABJURATION,
    casting_time=1,
    range=5,
    components="V, S",
    duration="1 round",
    description="An invisible barrier of magical force appears and protects you.",
    attack_type="none",
    classes=["Sorcerer", "Wizard"]
)