from .battle import Battle
from ..core.character import Character
from ..agents.npc_agent import NPC
from ..agents.player_agent import PlayerAgent
from ..spells.defined_spells import fireball, cure_wounds, magic_missile
from ..items.weapons import longsword, longbow
from ..core.enums import CharacterClass

def main():
    # Create player characters
    player1 = PlayerAgent(character=Character.generate(chr_class=CharacterClass.WIZARD, name="Player1", level=5))
    player2 = PlayerAgent(character=Character.generate(chr_class=CharacterClass.FIGHTER, name="Player2", level=5))

    # Create NPC characters
    npc1 = NPC(character=Character.generate(chr_class=CharacterClass.WIZARD, name="NPC1", level=5))
    npc2 = NPC(character=Character.generate(chr_class=CharacterClass.FIGHTER, name="NPC2", level=5))

    # Add spells to wizard characters
    player1.character.spells.extend([fireball, magic_missile])
    npc1.character.spells.extend([fireball, magic_missile])

    # Equip characters with weapons
    player2.character.equip(longsword)
    npc2.character.equip(longbow)

    # Create the battle
    battle = Battle([player1, player2], [npc1, npc2])

    # Test out agent functions
    print("Testing get_equipped_weapons")
    print(player1.get_equipped_weapons())
    print("Testing move_to")
    print(player1.move_to(5, 3))

    print("Testing get_character_position")
    print(battle.get_character_position(player1))

    print("Testing get_characters_in_range")
    print(player1.get_characters_in_range('spell', 'Fireball'))

    print("Testing get_map")
    print(player1.show_map())

    print("Testing spells")
    print(player1.cast_spell('Fireball', 'NPC1'))
    
    print("Testing attack")
    player2.move_to(4, 4)
    npc1.move_to(5, 5)
    print(player2.attack(npc1))


    # # Start the battle
    # battle.start_battle()

    # Test the player asking a question
    print("Testing chat")
    print("TEST 1: What spells do I have?")
    print(player1.chat("What spells do I have?"))
    print("TEST 2: What weapons do I have equipped?")
    print(player1.chat("What weapons do I have equipped?"))
    print("TEST 3: I cast fireball at NPC1")
    print(player1.chat("I cast fireball at NPC1"))
    print(npc1.character.current_hp, npc1.character.max_hp)
    print("TEST 4: Show the battle state")
    print(player1.chat("Show the battle state"))
if __name__ == "__main__":
    main()