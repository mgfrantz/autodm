from autodm.items.weapons import MeleeWeapon, RangedWeapon

if __name__ == "__main__":
    # Test generating weapons
    print("\nGenerating a melee weapon:")
    print(MeleeWeapon.generate())

    print("\nGenerating a ranged weapon:")
    print(RangedWeapon.generate())

    print("\nGenerating a specific weapon:")
    print(MeleeWeapon.generate("Generate a legendary two-handed sword with fire damage."))