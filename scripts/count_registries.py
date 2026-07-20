"""Count all content registries for README/PROGRESS drift check.

Run: cd backend && uv run --project .. python ../scripts/count_registries.py
"""
from app.engine.traps import list_traps
from app.engine.spells import SPELL_REGISTRY
from app.engine.tools import TOOL_REGISTRY
from app.engine.feats import list_feats
from app.engine.subclasses import SUBCLASS_REGISTRY
from app.engine.backgrounds import list_backgrounds
from app.engine.alignment import list_alignments
from app.engine.languages import ALL_LANGUAGES
from app.engine.mounts import MOUNT_REGISTRY
from app.engine.legendary import LEGENDARY_CREATURE_REGISTRY
from app.engine.adventures import STARTER_ADVENTURES
from app.engine.encounters import COMMON_ENEMIES


def main() -> None:
    counts = {
        "spells": len(SPELL_REGISTRY),
        "enemies": len(COMMON_ENEMIES),
        "feats": len(list_feats()),
        "tools": len(TOOL_REGISTRY),
        "backgrounds": len(list_backgrounds()),
        "alignments": len(list_alignments()),
        "languages": len(ALL_LANGUAGES),
        "mounts/vehicles": len(MOUNT_REGISTRY),
        "traps": len(list_traps()),
        "subclasses": len(SUBCLASS_REGISTRY),
        "legendary creatures": len(LEGENDARY_CREATURE_REGISTRY),
        "starter adventures": len(STARTER_ADVENTURES),
    }
    width = max(len(k) for k in counts)
    for name, n in counts.items():
        print(f"{name.ljust(width)} : {n}")


if __name__ == "__main__":
    main()
