from autodm.map.map_grid import Map
from autodm.agents.player_agent import PlayerAgent
from autodm.core.character import Character

def main():
    # Test Map
    battle_map = Map()
    player = PlayerAgent(
        character=Character.generate()
    )
    battle_map.add_or_update_player(x=0, y=0, player=player)
    print(battle_map)
    print(battle_map.positions)

    print("Updating location to (3,3)")
    battle_map.add_or_update_player(x=3, y=3, player=player)
    print(battle_map)
    print(battle_map.positions)

if __name__ == "__main__":
    main()