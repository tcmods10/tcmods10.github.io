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



@register_power
class BigSpike(Power):
    name, description, cooldown, color = "BIG Spike", "Fast, straight, painful.", 4.0, (255, 0, 255)

    def activate(self, p, game, aim):
        game.spawn(Projectile(p, self.muzzle(p, aim), aim * 1100, radius=12, damage=36, knockback=700,
                              life=0.6, color=self.color, shape="spike"))
