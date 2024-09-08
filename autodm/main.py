from .npc import NPC
from .player_agent import PlayerAgent
from .character import Character
from .items import EquipmentItem
from .spells import Spell, SpellSchool, fireball, magic_missile, shield, cure_wounds  # Import Spell and SpellSchool

def main():
    # Create player character
    player_character = Character.generate("Aric")
    player_character.chr_class = "Wizard"
    player_character.chr_race = "Human"
    player_character.level = 5

    # Equip Aric with a wand
    wand = EquipmentItem(name="Wand of the War Mage", item_type="weapon", effects={"damage": "1d6"}, quantity=1, weight=1.0)
    player_character.equip_item(wand)

    # Give Aric some spells
    player_character.add_spell(fireball)
    player_character.add_spell(magic_missile)
    player_character.add_spell(shield)
    player_character.add_spell(cure_wounds)

    # Set up spell slots (adjust as needed)
    player_character.spell_slots = {1: 4, 2: 3, 3: 2, 4: 1, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}

    player_agent = PlayerAgent(player_character)

    # Create NPC
    npc = NPC.generate("Groknak", "Barbarian", "Half-Orc", level=3)

    print(f"You are {player_character.name}, a level {player_character.level} {player_character.chr_race} {player_character.chr_class}.")
    print(f"You are equipped with a {wand.name}.")
    print(f"You know the following spells: {', '.join([spell.name for spell in player_character.spells])}")
    print(f"You encounter {npc.name}, a level {npc.level} {npc.chr_race} {npc.chr_class}.")
    print("\nType your actions or dialogue in plain text. Type 'exit' to end the session.")
    print("\nAvailable commands:")
    print("- check_equipment: View your equipped items")
    print("- check_hp: Check your current hit points")
    print("- check_skills: View your skill modifiers")
    print("- check_status: Get a full status report")
    print("- check_inventory: View your inventory")
    print("- check_spells: List your known spells")
    print("- check_attributes: View your attribute scores")

    while True:
        user_input = input("\nWhat would you like to do? ").strip()
        if user_input.lower() == 'exit':
            print("Ending session. Goodbye!")
            break

        player_response = player_agent.interpret_action(user_input)
        print(f"\nNarrator (Player): {player_response}")

        if "casts" in player_response:
            spell_name = player_response.split("casts")[1].split()[0]
            target = player_response.split("at")[-1].strip() if "at" in player_response else "themselves"
            spell_effect = describe_spell_effect(spell_name, target, player_character.name)
            print(f"\nNarrator: {spell_effect}")
        elif player_response.startswith(f"{player_character.name} says:"):
            # If the player is speaking, get the NPC's response
            npc_response = npc.converse(player_response.split(":", 1)[1].strip())
            print(f"\nNarrator (NPC): {npc_response}")
        else:
            # Check if the action is a social action directed at the NPC
            social_actions = ["intimidate", "persuade", "deceive"]
            for action in social_actions:
                if action in player_response.lower():
                    npc_reaction = npc.react_to_social_action(action, player_character.name)
                    print(f"\nNarrator (NPC Reaction): {npc_reaction}")
                    break

def describe_spell_effect(spell_name: str, target: str, caster_name: str) -> str:
    """Describe the effect of a spell based on its name."""
    spell_effects = {
        "Fireball": f"A bright streak flashes from {caster_name}'s finger toward {target}, "
                    f"exploding into a fiery ball. {target} is engulfed in flames, taking significant damage.",
        "Magic Missile": f"Three glowing darts of magical force spring from {caster_name}'s hand, "
                         f"unerringly striking {target}.",
        "Shield": f"An invisible barrier of magical force appears around {caster_name}, "
                  f"protecting them from attacks.",
        "Cure Wounds": f"{caster_name} touches {target}, and a surge of positive energy "
                       f"washes over them, healing their wounds."
    }
    return spell_effects.get(spell_name, f"The {spell_name} spell is cast, affecting {target}.")

if __name__ == "__main__":
    main()