"""Facts recovered from the original Soma client source.

These are compatibility identifiers, not limitations on the new game.
"""

DIRECTIONS = [
    "south",
    "south_west",
    "west",
    "north_west",
    "north",
    "north_east",
    "east",
    "south_east",
]

ACTION_SLOTS = {
    0: "combat_idle_standard",
    1: "combat_idle_two_handed",
    2: "combat_idle_polearm",
    3: "crossbow_action",
    4: "walk_standard",
    5: "walk_two_handed",
    6: "walk_polearm",
    7: "attack_unarmed",
    8: "attack_one_handed_or_wand",
    9: "attack_two_handed",
    10: "attack_spear",
    11: "attack_bow",
    12: "attack_axe",
    13: "hit_reaction",
    14: "cast",
    15: "die",
    16: "run",
    17: "attack_dual_sword",
    18: "peaceful_idle",
}

LAYERS = ["shadow", "body", "trousers", "boots", "armour", "helmet", "arms_weapon", "shield"]

WEAPON_TYPES = {
    0: "unarmed",
    1: "one_handed_sword",
    2: "two_handed_sword",
    3: "spear",
    4: "bow",
    5: "axe",
    6: "wand",
    7: "crossbow",
    8: "dual_sword",
}
