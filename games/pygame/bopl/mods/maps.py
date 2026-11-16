"""
Example mod. Every .py file in the mods/ folder is loaded automatically at startup.
Copy this file, rename it, and edit to make your own powers.

A power is a class with:
    name, description, cooldown (seconds), color (r, g, b)
    activate(self, player, game, aim)   -> runs when the slot button is pressed
                                           (return False to cancel without using the cooldown)
    update(self, player, game, dt)      -> optional, runs every frame (passives / held abilities)

Useful things:
    player.pos / player.vel / player.hp / player.radius / player.on_ground
    player.add_size(mult, seconds)      player.add_fx("shield" | "stun" | "nograv", seconds)
    game.spawn(Projectile(...))         game.spawn(Zone(...))
    game.add_platform((x, y, w, h), life=seconds)
    game.damage(target, amount, source, impulse_vector)
    game.explosion(pos, radius, damage, knockback, owner)
    game.burst(pos, color)              particles
    game.players / game.platforms / game.entities
    self.held(player)                   True while this power's button is held down
    CONFIG["..."]                       any value from config.json
    MAPS.append({"name": "...", "platforms": [(x, y, w, h), ...]})   add arenas
"""
from bopl import Power, register_power, Projectile, Zone, CONFIG, MAPS, V2, norm


# Example of adding a custom arena:
#MAPS.append({"name": "Narrow Bridge", "platforms": [(240, 480, 800, 20), (80, 300, 140, 20), (1060, 300, 140, 20)]})

MAPS.append({"name": "simplisity", "platforms": [(0,700,1280,20),(590,340,100,20)]})

