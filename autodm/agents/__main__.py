from .character_agent import Character, CharacterAgent
from ..spells.defined_spells import fireball, cure_wounds
from ..items.weapons import longsword, shortbow


def main():
    character = Character.generate()
    agent = CharacterAgent(character)
    agent.character.equip(longsword)
    agent.character.equip(shortbow)
    fireball.learn(agent.character)
    cure_wounds.learn(agent.character)

    while (message := input("Enter a message (exit to quit): ")) != "exit":
        response = agent.chat(message)
        print(response)


if __name__ == "__main__":
    main()