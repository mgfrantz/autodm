#!/usr/bin/env python3
from app.engine.spells import SPELL_REGISTRY
from app.engine.feats import _FEATS
from app.engine.encounters import COMMON_ENEMIES
from collections import defaultdict

print(f'Spells: {len(SPELL_REGISTRY)}')
print(f'Feats: {len(_FEATS)}')
print(f'Enemies: {len(COMMON_ENEMIES)}')

print('\nSpells by level:')
spells_by_level = defaultdict(list)
for spell in SPELL_REGISTRY.values():
    spells_by_level[spell.level].append(spell.name)
for level in sorted(spells_by_level):
    print(f'  Level {level}: {len(spells_by_level[level])} spells')

print('\nEnemies by CR:')
enemies_by_cr = defaultdict(list)
for enemy in COMMON_ENEMIES.values():
    enemies_by_cr[enemy.cr].append(enemy.name)
for cr in sorted(enemies_by_cr.keys()):
    print(f'  CR {cr}: {len(enemies_by_cr[cr])} enemies')

print('\nAll feat names:')
for feat_name in sorted(_FEATS.keys()):
    feat = _FEATS[feat_name]
    print(f'  {feat.name}')