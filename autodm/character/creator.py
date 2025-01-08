import random

from ..gameplay.mechanics import (
    AbilityEnum,
    AbilityScore,
    Character,
    Skill,
    SavingThrow,
    Armor,
    Attack,
    DamageTypeEnum,
    SkillEnum,
    ConditionEnum,
    CharacterClass,
    CharacterClassEnum,
    HitDiceType
)

# --- Helper Functions ---

def roll_ability_scores() -> list[int]:
    """Rolls 4d6 and drops the lowest for each ability score."""
    ability_scores = []
    for _ in range(6):
        rolls = [random.randint(1, 6) for _ in range(4)]
        rolls.remove(min(rolls))  # Drop the lowest
        ability_scores.append(sum(rolls))
    return ability_scores

def assign_ability_scores(scores: list[int]) -> dict[AbilityEnum, int]:
    """Assigns rolled scores to abilities based on player choice."""
    print("You rolled the following ability scores:", scores)
    assigned_scores = {}
    for ability in AbilityEnum:
        while True:
            try:
                score = int(input(f"Assign a score to {ability.value}: "))
                if score not in scores:
                    raise ValueError
                scores.remove(score)
                assigned_scores[ability] = score
                break
            except ValueError:
                print("Invalid score. Please choose a score from the list.")
    return assigned_scores

# --- Character Creation Steps ---

def choose_race() -> str:
    """
    Simplified race choice (Basic Rules only).
    In a full implementation, this would affect ability scores, traits, etc.
    """
    races = ["Dwarf", "Elf", "Halfling", "Human"]
    print("Available Races:", races)
    while True:
        race = input("Choose a race: ").title()
        if race in races:
            return race
        print("Invalid race. Please choose from the list.")

def choose_class() -> CharacterClass:
    """
    Guides the user through choosing a class and its initial features.
    """
    classes = {
        "Cleric": CharacterClass(
            name=CharacterClassEnum.CLERIC,
            level=1,
            hit_dice=HitDiceType.D8,
            armor_proficiencies=["light armor", "medium armor", "shields"],
            weapon_proficiencies=["all simple weapons"],
            saving_throw_proficiencies=[AbilityEnum.WISDOM, AbilityEnum.CHARISMA],
            starting_skills=[SkillEnum.HISTORY, SkillEnum.INSIGHT, SkillEnum.MEDICINE, SkillEnum.PERSUASION, SkillEnum.RELIGION],
            num_skills=2,
            equipment=["mace", "scale mail", "light crossbow", "20 bolts", "shield", "holy symbol"],
            features={
                1: "Divine Domain: Life Domain (Grants proficiency with heavy armor and life related spells)",
            }
        ),
        "Fighter": CharacterClass(
            name=CharacterClassEnum.FIGHTER,
            level=1,
            hit_dice=HitDiceType.D10,
            armor_proficiencies=["all armor", "shields"],
            weapon_proficiencies=["simple weapons", "martial weapons"],
            saving_throw_proficiencies=[AbilityEnum.STRENGTH, AbilityEnum.CONSTITUTION],
            starting_skills=[SkillEnum.ACROBATICS, SkillEnum.ANIMAL_HANDLING, SkillEnum.ATHLETICS, SkillEnum.HISTORY, SkillEnum.INSIGHT, SkillEnum.INTIMIDATION, SkillEnum.PERCEPTION, SkillEnum.SURVIVAL],
            num_skills=2,
            equipment=["chain mail", "martial weapon", "shield", "longbow", "20 arrows"],
            features={
                1: "Fighting Style: Archery (+2 bonus to attack rolls you make with ranged weapons), Second Wind (you can use a bonus action to regain hit points equal to 1d10 + your fighter level)",
            }
        ),
        "Rogue": CharacterClass(
            name=CharacterClassEnum.ROGUE,
            level=1,
            hit_dice=HitDiceType.D8,
            armor_proficiencies=["light armor"],
            weapon_proficiencies=["simple weapons", "hand crossbows", "longswords", "rapiers", "shortswords"],
            saving_throw_proficiencies=[AbilityEnum.DEXTERITY, AbilityEnum.INTELLIGENCE],
            starting_skills=[SkillEnum.ACROBATICS, SkillEnum.ATHLETICS, SkillEnum.DECEPTION, SkillEnum.INSIGHT, SkillEnum.INTIMIDATION, SkillEnum.INVESTIGATION, SkillEnum.PERCEPTION, SkillEnum.PERFORMANCE, SkillEnum.PERSUASION, SkillEnum.SLEIGHT_OF_HAND, SkillEnum.STEALTH],
            num_skills=4,
            equipment=["rapier", "shortbow", "20 arrows", "leather armor", "two daggers", "thieves' tools"],
            features={
                1: "Expertise (Choose two of your skill proficiencies, or one skill and thieve's tools. Your proficiency bonus is doubled), Sneak Attack (add 1d6 damage to your attack), Thieves' Cant (you can communicate with other thieves)"
            }
        ),
        "Wizard": CharacterClass(
            name=CharacterClassEnum.WIZARD,
            level=1,
            hit_dice=HitDiceType.D6,
            armor_proficiencies=[],
            weapon_proficiencies=["daggers", "darts", "slings", "quarterstaffs", "light crossbows"],
            saving_throw_proficiencies=[AbilityEnum.INTELLIGENCE, AbilityEnum.WISDOM],
            starting_skills=[SkillEnum.ARCANA, SkillEnum.HISTORY, SkillEnum.INSIGHT, SkillEnum.INVESTIGATION, SkillEnum.MEDICINE, SkillEnum.RELIGION],
            num_skills=2,
            equipment=["quarterstaff", "spellbook"],
            features={
                1: "Arcane Recovery (once per day when you finish a short rest, you can choose to regain expended spell slots of level 1)",
            }
        )
    }

    print("Available Classes:", list(classes.keys()))
    while True:
        class_choice = input("Choose a class: ").title()
        if class_choice in classes:
            selected_class = classes[class_choice]

            print(f"You have chosen the {selected_class.name} class.")
            print("Available skills (choose", selected_class.num_skills, "):", [skill.value for skill in selected_class.starting_skills])

            chosen_skills = []  # Store chosen skills temporarily
            while len(chosen_skills) < selected_class.num_skills:
                skill_choice = input(f"Choose a skill ({len(chosen_skills) + 1}/{selected_class.num_skills}): ").title()
                try:
                    skill_enum = SkillEnum(skill_choice)
                    if skill_enum in selected_class.starting_skills and skill_enum not in chosen_skills:
                        chosen_skills.append(skill_enum)
                    else:
                        print("Invalid skill or skill already chosen. Please choose from the list.")
                except ValueError:
                    print("Invalid skill. Please enter the skill name exactly as it appears in the list.")

            # DO NOT set selected_class.skills here
            return selected_class, chosen_skills # Return chosen skills
        print("Invalid class. Please choose from the list.")

def determine_ability_scores(method: str = "manual") -> list[AbilityScore]:
    """
    Determines ability scores using either the standard array or rolling.
    """
    if method == "roll":
        rolled_scores = roll_ability_scores()
        assigned_scores = assign_ability_scores(rolled_scores)
    else:  # Manual or standard array
        standard_array = [15, 14, 13, 12, 10, 8]
        assigned_scores = assign_ability_scores(standard_array.copy())

    ability_scores = []
    for ability, value in assigned_scores.items():
        ability_scores.append(AbilityScore(ability=ability, value=value, modifier=0))
    return ability_scores

def create_character():
    """
    Guides the user through the character creation process.
    """
    name = input("Enter your character's name: ")
    race = choose_race()

    while True:
        score_method = input("Choose ability score method ('roll' or 'manual'): ").lower()
        if score_method in ["roll", "manual"]:
            break
        print("Invalid method. Please enter 'roll' or 'manual'.")

    ability_scores = determine_ability_scores(score_method)

    character_class, chosen_skills = choose_class()  # Get chosen class and skills

    # Calculate hit points based on class
    constitution_modifier = 0
    for score in ability_scores:
        if score.ability == AbilityEnum.CONSTITUTION:
            constitution_modifier = score.modifier
            break

    hit_points = int(character_class.hit_dice.value[1:]) + constitution_modifier

    # Create attacks based on class
    attacks = []
    if character_class.name == CharacterClassEnum.CLERIC:
        attacks.append(
            Attack(
                name="Mace",
                attack_bonus=ability_scores[0].modifier + 2, # Strength + Proficiency
                damage_dice="1d6",
                damage_bonus=ability_scores[0].modifier, # Strength
                damage_type=DamageTypeEnum.BLUDGEONING
            )
        )
    elif character_class.name == CharacterClassEnum.FIGHTER:
        attacks.append(
            Attack(
                name="Longsword",
                attack_bonus=ability_scores[0].modifier + 2,  # Strength + Proficiency
                damage_dice="1d8",
                damage_bonus=ability_scores[0].modifier,  # Strength
                damage_type=DamageTypeEnum.SLASHING
            )
        )
        attacks.append(
            Attack(
                name="Longbow",
                attack_bonus=ability_scores[1].modifier + 2,  # Dexterity + Proficiency
                damage_dice="1d8",
                damage_bonus=ability_scores[1].modifier,  # Dexterity
                damage_type=DamageTypeEnum.PIERCING
            )
        )
    elif character_class.name == CharacterClassEnum.ROGUE:
        attacks.append(
            Attack(
                name="Rapier",
                attack_bonus=ability_scores[1].modifier + 2,  # Dexterity + Proficiency
                damage_dice="1d8",
                damage_bonus=ability_scores[1].modifier,  # Dexterity
                damage_type=DamageTypeEnum.PIERCING
            )
        )
        attacks.append(
            Attack(
                name="Shortbow",
                attack_bonus=ability_scores[1].modifier + 2,  # Dexterity + Proficiency
                damage_dice="1d6",
                damage_bonus=ability_scores[1].modifier,  # Dexterity
                damage_type=DamageTypeEnum.PIERCING
            )
        )
    elif character_class.name == CharacterClassEnum.WIZARD:
        attacks.append(
            Attack(
                name="Quarterstaff",
                attack_bonus=ability_scores[0].modifier + 2,  # Strength + Proficiency
                damage_dice="1d6",
                damage_bonus=ability_scores[0].modifier,  # Strength
                damage_type=DamageTypeEnum.BLUDGEONING
            )
        )

    # Initialize saving throws based on class proficiencies
    saving_throws = []
    for ability in AbilityEnum:
        is_proficient = ability in character_class.saving_throw_proficiencies
        saving_throws.append(SavingThrow(ability=ability, is_proficient=is_proficient))

    character = Character(
        name=name,
        level=1,
        ability_scores=ability_scores,
        proficiency_bonus=2,
        skills=character_class.choose_skills(chosen_skills),  # Set skills here
        saving_throws=saving_throws,
        armor_class=10,  # Base AC, will be modified by armor
        equipped_armor=None,  # You'd add armor objects here
        hit_points=hit_points,
        max_hit_points=hit_points,
        conditions=[],
        attacks=attacks,
        character_class=character_class
    )

    print("\nCharacter created successfully!")
    print(character.model_dump_json(indent=2))

    # Example of leveling up
    input("Press Enter to level up...")
    character.level_up()
    print("\nCharacter after leveling up:")
    print(character.model_dump_json(indent=2))

if __name__ == "__main__":
    create_character()