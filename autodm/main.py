from .player_agent import PlayerAgent
from .character import Character
from .npc import NPC
from .battle import Battle
from .defined_spells import fireball, magic_missile, cure_wounds
from .items import EquipmentItem, healing_potion

def equip_character(character):
    """Equip a character with appropriate weapons and/or spells based on their class and level."""
    if character.chr_class.lower() == "wizard":
        wand = EquipmentItem(name="Wand of the War Mage", item_type="weapon", effects={"damage": "1d4"}, quantity=1, weight=1.0)
        character.equip_item(wand)
        
        # Add spells based on character level
        if character.level >= 1:
            character.add_spell(magic_missile)
        if character.level >= 3:
            character.add_spell(fireball)
        
        # Set spell slots
        character.spell_slots = {
            1: 4 if character.level >= 1 else 0,
            2: 2 if character.level >= 3 else 0,
            3: 2 if character.level >= 5 else 0,
            4: 1 if character.level >= 7 else 0,
            5: 0, 6: 0, 7: 0, 8: 0, 9: 0
        }
    
    elif character.chr_class.lower() == "fighter":
        longsword = EquipmentItem(name="Longsword", item_type="weapon", effects={"damage": "1d8"}, quantity=1, weight=3.0)
        shield = EquipmentItem(name="Shield", item_type="armor", effects={"armor_class": 2}, quantity=1, weight=6.0)
        character.equip_item(longsword)
        character.equip_item(shield)
    elif character.chr_class.lower() == "barbarian":
        greataxe = EquipmentItem(name="Greataxe", item_type="weapon", effects={"damage": "1d12"}, quantity=1, weight=7.0)
        character.equip_item(greataxe)
    elif character.chr_class.lower() == "rogue":
        shortsword = EquipmentItem(name="Shortsword", item_type="weapon", effects={"damage": "1d6"}, quantity=1, weight=2.0)
        dagger = EquipmentItem(name="Dagger", item_type="weapon", effects={"damage": "1d4"}, quantity=2, weight=1.0)
        character.equip_item(shortsword)
        character.equip_item(dagger)

    # Add a healing potion to every character's inventory
    character.add_to_inventory(healing_potion)

def main():
    # Create player characters
    aric = Character.generate("Aric", chr_class="Wizard", chr_race="Human", level=5)
    equip_character(aric)
    player1 = PlayerAgent(aric)

    thorne = Character.generate("Thorne", chr_class="Fighter", chr_race="Dwarf", level=3)
    equip_character(thorne)
    player2 = PlayerAgent(thorne)

    # Create NPCs
    groknak_char = Character.generate("Groknak", chr_class="Barbarian", chr_race="Half-Orc", level=3)
    equip_character(groknak_char)
    groknak = NPC(groknak_char)

    zira_char = Character.generate("Zira", chr_class="Rogue", chr_race="Elf", level=3)
    equip_character(zira_char)
    zira = NPC(zira_char)

    print("Players:")
    for player in [player1, player2]:
        print(f"- {player.character.name}, a level {player.character.level} {player.character.chr_race} {player.character.chr_class}")
        print(f"  Known spells: {', '.join([spell.name for spell in player.character.spells])}")
        print(f"  Spell slots: {player.character.spell_slots}")
        print(f"  Equipped items: {', '.join([item.name for slot in player.character.equipped_items.values() for item in slot if item])}")

    print("\nEnemies:")
    for npc in [groknak, zira]:
        print(f"- {npc.character.name}, a level {npc.character.level} {npc.character.chr_race} {npc.character.chr_class}")
        print(f"  Equipped items: {', '.join([item.name for slot in npc.character.equipped_items.values() for item in slot if item])}")
    
    # Start the battle
    battle = Battle([player1, player2], [groknak, zira])
    battle.start_battle()

if __name__ == "__main__":
    main()