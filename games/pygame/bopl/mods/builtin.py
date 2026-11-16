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



# ---- built-in powers --------------------------------------------------------
@register_power
class Dash(Power):
    name, description, cooldown, color = "Dash", "Burst of speed in your aim direction.", 2.5, (255, 220, 90)

    def activate(self, p, game, aim):
        p.vel = aim * 950
        p.add_fx("nograv", 0.14)
        game.burst(p.pos, self.color, 14, 300, 0.4, direction=-aim, spread=1.0)


@register_power
class Blink(Power):
    name, description, cooldown, color = "Blink", "Teleport a short way forward.", 4.0, (200, 140, 255)

    def activate(self, p, game, aim):
        game.burst(p.pos, self.color, 20, 250, 0.4)
        for d in range(260, -1, -20):
            np_ = p.pos + aim * d
            if not game.circle_blocked(np_, p.radius):
                p.pos = np_
                break
        game.burst(p.pos, self.color, 20, 250, 0.4)


@register_power
class Grow(Power):
    name, description, cooldown, color = "Grow", "Get huge: heavier, tougher to launch.", 10.0, (255, 140, 80)

    def activate(self, p, game, aim):
        p.add_size(1.9, 6.0)
        game.burst(p.pos, self.color, 20, 300, 0.5)


@register_power
class ShrinkRay(Power):
    name, description, cooldown, color = "Shrink Ray", "Shrinks an enemy for a few seconds.", 7.0, (120, 255, 200)

    def activate(self, p, game, aim):
        game.spawn(Projectile(p, self.muzzle(p, aim), aim * 1200, radius=7, damage=0, knockback=0, life=1.2,
                              color=self.color, on_hit=lambda g, pr, t: t.add_size(0.5, 6.0)))


@register_power
class Rock(Power):
    name, description, cooldown, color = "Rock", "Lob a heavy boulder.", 5.0, (150, 140, 125)

    def activate(self, p, game, aim):
        game.spawn(Projectile(p, self.muzzle(p, aim, 24), aim * 520 + V2(0, -120), radius=22, damage=22,
                              knockback=950, gravity=850, life=5, color=self.color))


@register_power
class Spike(Power):
    name, description, cooldown, color = "Spike", "Fast, straight, painful.", 2.0, (255, 100, 100)

    def activate(self, p, game, aim):
        game.spawn(Projectile(p, self.muzzle(p, aim), aim * 1100, radius=6, damage=18, knockback=350,
                              life=1.2, color=self.color, shape="spike"))


@register_power
class Gust(Power):
    name, description, cooldown, color = "Gust", "Cone of wind that shoves enemies and bullets.", 4.0, (170, 230, 255)

    def activate(self, p, game, aim):
        origin = self.muzzle(p, aim, 0)
        for t in game.players:
            if t is p or not t.alive:
                continue
            d = t.pos - origin
            dist = d.length()
            if 0 < dist < 380 and aim.dot(d / dist) > 0.7:
                game.damage(t, 0, p, aim * 1200 * (1 - dist / 460))
        for e in game.entities:
            if isinstance(e, Projectile) and e.owner is not p:
                d = e.pos - origin
                dist = d.length()
                if 0 < dist < 380 and aim.dot(d / dist) > 0.7:
                    e.vel += aim * 700
        game.burst(origin, self.color, 30, 600, 0.5, direction=aim, spread=0.9)



@register_power
class BlackHole(Power):
    name, description, cooldown, color = "Black Hole", "Pulls everything toward it for a few seconds.", 20.0, (170, 90, 255)

    def activate(self, p, game, aim):
        def make(g, pr):
            def tick(z, g2, dt):
                for t in g2.players:
                    if not t.alive:
                        continue
                    d = z.pos - t.pos
                    dist = d.length()
                    if dist < z.radius:
                        # Amplified pull multiplier for insane strength
                        pull = 8000 * (1 - dist / z.radius) * (0.4 if t is z.owner else 1)
                        t.vel += norm(d) * pull * dt
                        if dist < 35 and t is not z.owner:
                            g2.damage(t, 35 * dt, z.owner, V2())
                for e in g2.entities:
                    if isinstance(e, Projectile) and not e.stuck:
                        d = z.pos - e.pos
                        if d.length() < z.radius:
                            # Amplified projectile pull multiplier
                            e.vel += norm(d) * 6000 * dt
            g.spawn(Zone(pr.owner, pr.pos, 210, 4.0, tick, self.color))
        game.spawn(Projectile(p, self.muzzle(p, aim), aim * 520, radius=12, damage=0, knockback=0, life=0.7,
                            color=self.color, pierce=True, on_end=make))



@register_power
class PlatformPower(Power):
    name, description, cooldown, color = "Platform", "Conjure a temporary platform. Aim down to save yourself.", 6.0, (130, 190, 255)

    def activate(self, p, game, aim):
        c = p.pos + aim * (p.radius + 85)
        game.add_platform((int(c.x - 75), int(c.y - 8), 150, 16), life=6.0, color=(110, 170, 240))
        game.burst(c, self.color, 16, 200, 0.4)


@register_power
class Grenade(Power):
    name, description, cooldown, color = "Grenade", "Bouncy bomb that explodes after a moment.", 5.0, (255, 170, 50)

    def activate(self, p, game, aim):
        boom = lambda g, pr: g.explosion(pr.pos, 125, 25, 1000, pr.owner)
        game.spawn(Projectile(p, self.muzzle(p, aim, 10), aim * 650 + V2(0, -150), radius=10, damage=0,
                              knockback=0, gravity=1000, bounce=0.6, life=1.8, color=self.color, on_end=boom))


@register_power
class Mine(Power):
    name, description, cooldown, color = "Mine", "Toss a mine that sticks and detonates near enemies.", 6.0, (255, 90, 160)

    def activate(self, p, game, aim):
        boom = lambda g, pr: g.explosion(pr.pos, 115, 30, 1100, pr.owner, (255, 90, 160))
        game.spawn(Projectile(p, self.muzzle(p, aim, 8), aim * 260, radius=9, damage=0, knockback=0,
                              gravity=1200, sticky=True, arm_time=0.8, proximity=75, life=25,
                              color=self.color, on_end=boom, trail=False))






@register_power
class Shield(Power):
    name, description, cooldown, color = "Shield", "Briefly block damage and reflect projectiles.", 8.0, (150, 220, 255)

    def activate(self, p, game, aim):
        p.add_fx("shield", 2.0)


@register_power
class Slam(Power):
    name, description, cooldown, color = "Slam", "Dive down hard and shockwave on landing.", 6.0, (255, 120, 60)

    def __init__(self):
        super().__init__()
        self.active, self.t = False, 0.0

    def on_round_start(self, player, game):
        self.active = False

    def activate(self, p, game, aim):
        p.vel = V2(0, 1500)
        self.active, self.t = True, 0.0

    def update(self, p, game, dt):
        if not self.active:
            return
        self.t += dt
        if p.on_ground or self.t > 2.0:
            self.active = False
            if p.on_ground:
                game.explosion(p.pos + V2(0, p.radius), 150, 15, 750, p, self.color, hurt_owner=False)


@register_power
class Heal(Power):
    name, description, cooldown, color = "Heal", "Restore 30 health.", 14.0, (110, 255, 130)

    def activate(self, p, game, aim):
        if p.hp >= p.max_hp:
            return False
        p.hp = min(p.max_hp, p.hp + 30)
        game.burst(p.pos, self.color, 20, 200, 0.6)




# Example of adding a custom arena:
#MAPS.append({"name": "Narrow Bridge", "platforms": [(240, 480, 800, 20), (80, 300, 140, 20), (1060, 300, 140, 20)]})

