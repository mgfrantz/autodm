from ..character.creator import create_character
from ..character.models import Character, AbilityEnum, AbilityScore
from ..map import GameMap, SizeEnum, calculate_distance

# Create some characters
strength = AbilityScore(ability=AbilityEnum.STRENGTH, value=16, modifier=0)
dexterity = AbilityScore(ability=AbilityEnum.DEXTERITY, value=14, modifier=0)
constitution = AbilityScore(ability=AbilityEnum.CONSTITUTION, value=15, modifier=0)
intelligence = AbilityScore(ability=AbilityEnum.INTELLIGENCE, value=8, modifier=0)
wisdom = AbilityScore(ability=AbilityEnum.WISDOM, value=10, modifier=0)
charisma = AbilityScore(ability=AbilityEnum.CHARISMA, value=12, modifier=0)

character1 = Character(
    name="Alice",
    level=1,
    ability_scores=[strength, dexterity, constitution, intelligence, wisdom, charisma],
    proficiency_bonus=2,
    armor_class=10,
    hit_points=10,
    max_hit_points=10,
    character_class=None,
    speed=25
)

character2 = Character(
    name="Bob",
    level=1,
    ability_scores=[strength, dexterity, constitution, intelligence, wisdom, charisma],
    proficiency_bonus=2,
    armor_class=10,
    hit_points=20,
    max_hit_points=20,
    character_class=None,
    speed=30
)

character3 = Character(
    name="Grog",
    level=1,
    ability_scores=[strength, dexterity, constitution, intelligence, wisdom, charisma],
    proficiency_bonus=2,
    armor_class=10,
    hit_points=20,
    max_hit_points=20,
    character_class=None,
    speed=30
)

# Create a map
game_map = GameMap(size_x=20, size_y=15)

# Add characters to the map
game_map.add_character(character1, 5, 5)
game_map.add_character(character2, 10, 10)
game_map.add_character(character3, 1, 1, size=SizeEnum.LARGE)

# Render the map
print(game_map.render())