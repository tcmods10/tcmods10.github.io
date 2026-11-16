#!/usr/bin/env python3
"""
BOPL-STYLE BRAWLER  (original code, pygame)
===========================================
Run:      pip install pygame-ce   then   python bopl.py
Browser:  PyScript -- serve this folder (python -m http.server) and open index.html
Config:   config.json (auto-created on first run) -> slots, players, physics, bindings
Mods:     drop .py files into the  mods/  folder (see mods/example_powers.py)

Everything a modder needs is importable with:  from bopl import *
"""
import sys, os, json, math, random, importlib.util, traceback, asyncio
from pathlib import Path
import pygame
from pygame import Vector2 as V2

# Lets mods do "from bopl import ..." even when this file is run as a script.
sys.modules.setdefault("bopl", sys.modules[__name__])

WEB = sys.platform == "emscripten"      # running under PyScript / Pyodide in a browser
try:
    BASE = Path(__file__).resolve().parent
except NameError:                        # PyScript runs the main script without __file__
    BASE = Path.cwd()
if WEB:
    from js import navigator as _js_navigator
CONFIG_PATH = BASE / "config.json"
MODS_DIR = BASE / "mods"
W, H = 1280, 720            # logical resolution (window scales to fit)

# ----------------------------------------------------------------------------
# CONFIG  (edit config.json, not this)
# ----------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "max_players": 4,                 # how many players can join (limited by devices available)
    "min_players": 2,                 # set to 1 to test alone
    "power_slots": 3,                 # abilities per player
    "draft_choices": 3,               # options offered per pick
    "redraft_slots_per_round": 1,     # slots re-picked between rounds (set = power_slots for full redraft)
    "rounds_to_win": 3,
    "player_max_hp": 100,
    "air_jumps": 1,
    "gravity": 1500,
    "move_speed": 300,
    "jump_speed": 640,
    "bot_difficulty": 0.6,            # computer player skill, 0.0 (clumsy) to 1.0 (sharp)
    "bots_fill_to": 0,                # auto-add computer players until this many players at match start
    "cooldown_scale": 1.0,            # multiply every cooldown (0.5 = twice as fast)
    "low_hp_knockback_bonus": 0.8,    # low-health players fly further
    "fullscreen": False,
    "fps": 60,
    "enabled_powers": [],             # empty = every power; otherwise only these names
    "disabled_powers": [],            # names to ban
    "controller": {
        "deadzone": 0.25,
        "jump_button": 0,             # A
        "start_button": 7,            # Start
        "back_button": 6,             # Back/Select (leave lobby)
        "slot_buttons": [2, 1, 3, 5, 4, "a5", "a4"],   # X B Y RB LB RT LT  ("aN" = axis N as trigger)
        "move_axes": [0, 1],
        "aim_axes": [2, 3]            # right stick (Linux xbox pads often use [3, 4])
    },
    "keyboards": [
        {"name": "Keyboard WASD", "left": "a", "right": "d", "up": "w", "down": "s",
         "jump": "space", "start": "return", "back": "backspace",
         "slots": ["j", "k", "l", "u", "i", "o", "p"]},
        {"name": "Keyboard Arrows", "left": "left", "right": "right", "up": "up", "down": "down",
         "jump": "right ctrl", "start": "return", "back": "backspace",
         "slots": [",", ".", "/", "m", "n", "'", ";"]}
    ]
}


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                user = json.load(f)
            for k, v in user.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        except Exception as e:
            print("[config] could not read config.json, using defaults:", e)
    else:
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
        except OSError:
            pass
    return cfg


CONFIG = load_config()

# ----------------------------------------------------------------------------
# SMALL HELPERS
# ----------------------------------------------------------------------------
PLAYER_COLORS = [(255, 90, 90), (80, 170, 255), (110, 230, 120), (255, 210, 70),
                 (200, 120, 255), (255, 150, 60), (80, 230, 220), (255, 130, 200)]


def clamp(x, a, b):
    return max(a, min(b, x))


def norm(v, default=(0, -1)):
    l = v.length()
    return V2(default) if l < 1e-6 else v / l


def darker(c, k=0.6):
    return tuple(int(x * k) for x in c)


def lighter(c, k=0.4):
    return tuple(int(x + (255 - x) * k) for x in c)


_fonts = {}


def font(size):
    if size not in _fonts:
        _fonts[size] = pygame.font.Font(None, size)
    return _fonts[size]


def draw_text(surf, s, size, pos, color=(255, 255, 255), center=True, shadow=True):
    f = font(size)
    img = f.render(s, True, color)
    r = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
    if shadow:
        surf.blit(f.render(s, True, (0, 0, 0)), r.move(2, 2))
    surf.blit(img, r)
    return r


def wrap(s, size, width):
    f, lines, cur = font(size), [], ""
    for w in s.split():
        t = (cur + " " + w).strip()
        if f.size(t)[0] <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def resolve_circle_rect(pos, r, rect):
    """Returns (push_normal, penetration) if circle overlaps rect, else None."""
    cx = clamp(pos.x, rect.left, rect.right)
    cy = clamp(pos.y, rect.top, rect.bottom)
    dx, dy = pos.x - cx, pos.y - cy
    d2 = dx * dx + dy * dy
    if d2 >= r * r:
        return None
    if d2 > 1e-9:
        d = math.sqrt(d2)
        return V2(dx / d, dy / d), r - d
    dl, dr = pos.x - rect.left, rect.right - pos.x
    dt, db = pos.y - rect.top, rect.bottom - pos.y
    m = min(dl, dr, dt, db)
    if m == dt:
        n = V2(0, -1)
    elif m == db:
        n = V2(0, 1)
    elif m == dl:
        n = V2(-1, 0)
    else:
        n = V2(1, 0)
    return n, m + r


# ----------------------------------------------------------------------------
# MAPS   (mods can MAPS.append({...}))     platform = (x, y, w, h)
# ----------------------------------------------------------------------------
MAPS = [
    {"name": "Floating Isle", "platforms": [(340, 520, 600, 40), (100, 380, 220, 24),
                                            (960, 380, 220, 24), (520, 260, 240, 24)]},
    {"name": "Twin Cliffs", "platforms": [(60, 540, 380, 50), (840, 540, 380, 50), (540, 430, 200, 22),
                                          (160, 300, 200, 22), (920, 300, 200, 22), (540, 200, 200, 22)]},
    {"name": "Stepping Stones", "platforms": [(80, 560, 200, 26), (360, 480, 200, 26), (640, 400, 200, 26),
                                              (920, 320, 200, 26), (400, 250, 200, 26), (160, 330, 160, 26)]},
    {"name": "Arena", "platforms": [(200, 560, 880, 40), (120, 400, 180, 22), (980, 400, 180, 22),
                                    (450, 360, 380, 22), (540, 200, 200, 22)]},
]

# ----------------------------------------------------------------------------
# INPUT  (keyboard + controllers share one interface)
# ----------------------------------------------------------------------------


def _neutral():
    return dict(mx=0.0, my=0.0, ax=0.0, ay=0.0, jump=False, start=False, back=False,
                slots=[False] * CONFIG["power_slots"])


class InputDevice:
    is_bot = False

    def __init__(self, name):
        self.name = name
        S = CONFIG["power_slots"]
        self.move = V2()
        self.aim_vec = V2()          # zero = "no aim input, use facing"
        self.jump = self.jump_p = False
        self.start_p = self.back_p = False
        self.slot = [False] * S
        self.slot_p = [False] * S
        self.nav_p = 0               # -1 / +1 on the frame the stick/keys are pushed (menus)
        self._start = self._back = False
        self._nav = 0

    def _read(self):
        return _neutral()

    def update(self):
        r = self._read()
        self.jump_p = r["jump"] and not self.jump
        self.jump = r["jump"]
        self.start_p = r["start"] and not self._start
        self._start = r["start"]
        self.back_p = r["back"] and not self._back
        self._back = r["back"]
        self.slot_p = [s and not o for s, o in zip(r["slots"], self.slot)]
        self.slot = r["slots"]
        self.move = V2(r["mx"], r["my"])
        self.aim_vec = V2(r["ax"], r["ay"])
        nav = 1 if r["mx"] > 0.6 else -1 if r["mx"] < -0.6 else 0
        self.nav_p = nav if nav != self._nav else 0
        self._nav = nav


class KeyboardDevice(InputDevice):
    def __init__(self, scheme):
        super().__init__(scheme.get("name", "Keyboard"))

        def code(n):
            try:
                return pygame.key.key_code(n)
            except Exception:
                print("[input] unknown key name:", n)
                return None
        self.k = {a: code(scheme[a]) for a in ("left", "right", "up", "down", "jump", "start", "back") if a in scheme}
        self.slot_keys = [code(n) for n in scheme.get("slots", [])]
        self.scheme = scheme

    def _read(self):
        keys = pygame.key.get_pressed()
        d = lambda k: bool(k is not None and keys[k])
        x = d(self.k.get("right")) - d(self.k.get("left"))
        y = d(self.k.get("down")) - d(self.k.get("up"))
        S = CONFIG["power_slots"]
        slots = [d(self.slot_keys[i]) if i < len(self.slot_keys) else False for i in range(S)]
        return dict(mx=float(x), my=float(y), ax=float(x), ay=float(y), jump=d(self.k.get("jump")),
                    start=d(self.k.get("start")), back=d(self.k.get("back")), slots=slots)


class TouchDevice(InputDevice):
    """On-screen buttons triggered by mouse clicks / finger taps.
    Only exists (and is only read) after 'Add touch player' is clicked in the lobby."""

    def __init__(self, game):
        super().__init__("Touch screen")
        self.game = game
        self.down = set()
        b = 84
        self.buttons = {
            "up": pygame.Rect(112, 440, b, b), "left": pygame.Rect(20, 532, b, b),
            "down": pygame.Rect(112, 532, b, b), "right": pygame.Rect(204, 532, b, b),
            "jump": pygame.Rect(W - 130, 520, 110, 110),
            "back": pygame.Rect(W - 215, 10, 100, 40), "start": pygame.Rect(W - 110, 10, 100, 40)}
        for i in range(CONFIG["power_slots"]):
            row, col = divmod(i, 4)
            self.buttons[f"slot{i}"] = pygame.Rect(W - 20 - (col + 1) * 70 - col * 8, 430 - row * 78, 70, 70)

    def _read(self):
        pts = list(self.game.pointers.values())
        d = self.down = {n for n, r in self.buttons.items() if any(r.collidepoint(p) for p in pts)}
        x = ("right" in d) - ("left" in d)
        y = ("down" in d) - ("up" in d)
        return dict(mx=float(x), my=float(y), ax=float(x), ay=float(y), jump="jump" in d,
                    start="start" in d, back="back" in d,
                    slots=[f"slot{i}" in d for i in range(CONFIG["power_slots"])])


class WebJoy:
    """Browser Gamepad API wrapped to look like a pygame Joystick (SDL's browser gamepad support is unreliable).
    Browser 'standard' layout is translated to the Xbox/Windows layout the default config uses:
    Back/Start = buttons 6/7, triggers = axes 4/5 (a4 = LT, a5 = RT), d-pad = hat."""

    def __init__(self, pad):
        self.pad = pad
        self.index = pad.index

    def _std(self):
        return str(self.pad.mapping) == "standard"

    def get_name(self):
        return str(self.pad.id)

    def get_instance_id(self):
        return self.index

    def get_axis(self, i):
        if self._std() and i in (4, 5):
            return float(self.pad.buttons[i + 2].value) * 2 - 1      # trigger button -> -1..1 like SDL
        return float(self.pad.axes[i])

    def get_button(self, i):
        if self._std() and i in (6, 7):
            i += 2                                                   # Back/Start live at 8/9 in the browser
        if "057e" in self.get_name().lower() and i < 4:
            i = (1, 0, 3, 2)[i]                                      # Nintendo pads: browser reports by position, config by label
        return bool(self.pad.buttons[i].pressed)

    def get_numhats(self):
        return 1 if self._std() else 0

    def get_hat(self, n):
        b = self.pad.buttons
        return (int(b[15].pressed) - int(b[14].pressed), int(b[12].pressed) - int(b[13].pressed))


class JoyDevice(InputDevice):
    def __init__(self, joy):
        super().__init__(joy.get_name())
        self.joy = joy
        self.instance_id = joy.get_instance_id()

    def _btn(self, spec):
        try:
            if spec is None:
                return False
            if isinstance(spec, str) and spec.startswith("a"):
                return self.joy.get_axis(int(spec[1:])) > 0.3
            return bool(self.joy.get_button(int(spec)))
        except Exception as ex:
            if WEB and not getattr(self, "_warned", False):
                self._warned = True
                print("[input] controller read error:", repr(ex))
            return False

    def _read(self):
        if self.joy is None:
            return _neutral()
        c = CONFIG["controller"]
        dz = c["deadzone"]

        def ax(i):
            try:
                v = self.joy.get_axis(i)
            except Exception:
                return 0.0
            return 0.0 if abs(v) < dz else v
        mx, my = ax(c["move_axes"][0]), ax(c["move_axes"][1])
        try:
            if self.joy.get_numhats() > 0:
                hx, hy = self.joy.get_hat(0)
                if hx:
                    mx = float(hx)
                if hy:
                    my = float(-hy)
        except Exception:
            pass
        ax_, ay_ = ax(c["aim_axes"][0]), ax(c["aim_axes"][1])
        if abs(ax_) + abs(ay_) < 0.01 and V2(mx, my).length() > 0.5:
            ax_, ay_ = mx, my
        sb = c["slot_buttons"]
        slots = [self._btn(sb[i]) if i < len(sb) else False for i in range(CONFIG["power_slots"])]
        return dict(mx=mx, my=my, ax=ax_, ay=ay_, jump=self._btn(c["jump_button"]),
                    start=self._btn(c["start_button"]), back=self._btn(c["back_button"]), slots=slots)


class BotDevice(InputDevice):
    """Computer player. It produces the same input a human device would, so powers
    and mods need no changes. Difficulty: config 'bot_difficulty'."""
    is_bot = True

    def __init__(self):
        super().__init__("Computer")
        self.game = self.player = None
        self.jump_timer = self.jump_cd = 0.0
        self.noise, self.noise_t = 0.0, 0.0
        self.strafe, self.strafe_t = 1, 0.0

    @staticmethod
    def choose(opts):
        """Pick a power index during the draft (prefers attacking powers)."""
        return max(range(len(opts)),
                   key=lambda i: random.random() + (1.0 if getattr(opts[i], "bot_hint", "attack") == "attack" else 0.3))

    def _support_below(self, x, y, r):
        best = None
        for pl in self.game.platforms:
            rc = pl.rect
            if rc.left - r * 0.5 <= x <= rc.right + r * 0.5 and rc.top >= y - r:
                if best is None or rc.top < best:
                    best = rc.top
        return best

    def _nearest_platform(self, pos):
        best, bd = None, 1e9
        for pl in self.game.platforms:
            rc = pl.rect
            d = (V2(clamp(pos.x, rc.left, rc.right), clamp(pos.y, rc.top, rc.bottom)) - pos).length()
            if d < bd:
                best, bd = pl, d
        return best

    def _read(self):
        r = _neutral()
        g, me = self.game, self.player
        if g is None or me is None or not me.alive or g.state not in ("play", "round_end") or g.countdown > 0:
            self.jump_timer = 0.0
            return r
        dt = getattr(g, "dt", 1 / 60)
        diff = clamp(CONFIG["bot_difficulty"], 0.0, 1.0)
        self.jump_cd -= dt
        self.noise_t -= dt
        self.strafe_t -= dt
        if self.noise_t <= 0:
            self.noise, self.noise_t = random.uniform(-1, 1) * (1 - diff) * 0.45, 0.4
        if self.strafe_t <= 0:
            self.strafe, self.strafe_t = random.choice((-1, 1)), random.uniform(0.6, 1.6)

        pos = me.pos
        enemies = [p for p in g.players if p.alive and p is not me]
        target = min(enemies, key=lambda e: (e.pos - pos).length()) if enemies else None
        dist_t = (target.pos - pos).length() if target else 1e9
        recovering = self._support_below(pos.x, pos.y, me.radius) is None
        rec_depth, mx, aim, want_jump = 0.0, 0.0, V2(me.facing, 0), False

        if recovering:
            pl = self._nearest_platform(pos)
            if pl:
                rc = pl.rect
                tx = clamp(pos.x, rc.left + 20, rc.right - 20)
                if abs(tx - pos.x) < 8:
                    tx = rc.x + rc.w / 2
                mx = 1.0 if tx > pos.x + 6 else -1.0 if tx < pos.x - 6 else 0.0
                aim = norm(V2(tx, rc.top) - pos)
                rec_depth = pos.y - rc.top
                want_jump = me.vel.y > 0 and self.jump_cd <= 0 and (me.air_left > 0 or me.coyote > 0)
        elif target:
            d = target.pos - pos
            dirx = 1 if d.x > 0 else -1
            if dist_t > 220:
                mx = float(dirx)
            elif dist_t < 120:
                mx = -float(dirx)
            else:
                mx = self.strafe * 0.6
            if mx != 0 and me.on_ground:
                ahead = pos.x + (1 if mx > 0 else -1) * (me.radius + 30)
                if self._support_below(ahead, pos.y, me.radius) is None:
                    if target.pos.y > pos.y + 100:
                        pass                      # enemy is below: drop down after them
                    elif target.pos.y < pos.y + 50 and self.jump_cd <= 0:
                        want_jump = True          # hop the gap
                    else:
                        mx = 0.0
            if target.pos.y < pos.y - 70 and me.on_ground and self.jump_cd <= 0:
                want_jump = True
            if (not me.on_ground and target.pos.y < pos.y - 40 and me.vel.y > 50
                    and me.air_left > 0 and self.jump_cd <= 0):
                want_jump = True
            aim = norm(target.pos + target.vel * 0.2 - pos).rotate(math.degrees(self.noise))

        # powers
        threat = any(isinstance(e, Projectile) and e.owner is not me and (e.pos - pos).length() < 230
                     and e.vel.dot(pos - e.pos) > 0 for e in g.entities)
        for i, pw in enumerate(me.slots[:len(r["slots"])]):
            if pw is None or pw.cd_left > 0:
                continue
            hint = getattr(pw, "bot_hint", "attack")
            if hint == "recover":
                press = recovering and (rec_depth > 40 or me.air_left == 0)
            elif hint == "defend":
                press = threat or dist_t < 110
            elif hint == "heal":
                press = me.hp < me.max_hp * 0.6 and not recovering
            elif hint == "buff":
                press = target is not None and dist_t < 450 and not recovering
            else:
                press = (not recovering and target is not None and dist_t < getattr(pw, "bot_range", 700)
                         and random.random() < (0.4 + 0.6 * diff) * dt * 2.5)
            if press:
                r["slots"][i] = True

        # jump (needs a fresh press each time, so release first if it was held)
        if want_jump:
            if self.jump:
                r["jump"], self.jump_timer = False, 0.0
            else:
                r["jump"], self.jump_timer, self.jump_cd = True, 0.28, 0.35
        elif self.jump_timer > 0:
            r["jump"] = True
            self.jump_timer -= dt

        r["mx"], r["ax"], r["ay"] = mx, aim.x, aim.y
        return r


# ----------------------------------------------------------------------------
# WORLD OBJECTS
# ----------------------------------------------------------------------------
class Platform:
    def __init__(self, rect, life=None, color=(74, 86, 120)):
        self.rect = pygame.Rect(rect)
        self.life = life            # None = permanent
        self.color = color

    def update(self, dt):
        if self.life is not None:
            self.life -= dt

    @property
    def expired(self):
        return self.life is not None and self.life <= 0

    def draw(self, surf):
        if self.life is not None and self.life < 1.5 and int(self.life * 10) % 2 == 0:
            return
        pygame.draw.rect(surf, self.color, self.rect, border_radius=8)
        pygame.draw.rect(surf, lighter(self.color, 0.35),
                         (self.rect.x, self.rect.y, self.rect.w, min(6, self.rect.h)), border_radius=8)


class Entity:
    alive = True

    def update(self, game, dt):
        pass

    def draw(self, surf):
        pass


class Zone(Entity):
    """Area effect. tick(zone, game, dt) is called every frame while alive."""

    def __init__(self, owner, pos, radius, life, tick=None, color=(180, 80, 255), expand=False):
        self.owner, self.pos, self.radius, self.life = owner, V2(pos), radius, life
        self.tick, self.color, self.expand, self.t = tick, color, expand, 0.0

    def update(self, game, dt):
        self.t += dt
        if self.tick:
            self.tick(self, game, dt)
        if self.t >= self.life:
            self.alive = False

    def draw(self, surf):
        k = clamp(self.t / self.life, 0, 1)
        r = int(self.radius * (0.3 + 0.7 * k)) if self.expand else int(self.radius)
        if r < 2:
            return
        s = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        c = (r + 2, r + 2)
        if self.expand:
            pygame.draw.circle(s, (*self.color, int(170 * (1 - k))), c, r, 5)
        else:
            pygame.draw.circle(s, (*darker(self.color, 0.4), 80), c, r)
            pygame.draw.circle(s, (*self.color, 140), c, r, 3)
            pygame.draw.circle(s, (*self.color, 160), c, int(r * (0.35 + 0.1 * math.sin(self.t * 12))), 3)
            pygame.draw.circle(s, (0, 0, 0, 230), c, max(4, r // 8))
        surf.blit(s, (self.pos.x - r - 2, self.pos.y - r - 2))


class Projectile(Entity):
    """
    Generic projectile. Most powers just configure one of these.
      damage/knockback : applied on hit      gravity : px/s^2 downward
      bounce           : >0 bounces off platforms (0 = dies on contact)
      sticky           : sticks to platforms (mines)
      proximity/arm_time: explodes (kills itself) when an enemy comes within range
      pierce           : keep flying after hitting a player
      on_hit(game, proj, player)  /  on_end(game, proj)   callbacks
      shape            : "circle" | "spike"
    """

    def __init__(self, owner, pos, vel, radius=8, damage=10, knockback=400, gravity=0.0, life=3.0,
                 color=(255, 255, 255), bounce=0.0, pierce=False, sticky=False, proximity=0,
                 arm_time=0.0, on_hit=None, on_end=None, shape="circle", trail=True):
        self.owner, self.pos, self.vel = owner, V2(pos), V2(vel)
        self.radius, self.damage, self.knockback = radius, damage, knockback
        self.gravity, self.life, self.color, self.bounce = gravity, life, color, bounce
        self.pierce, self.sticky, self.proximity, self.arm_time = pierce, sticky, proximity, arm_time
        self.on_hit, self.on_end, self.shape, self.trail = on_hit, on_end, shape, trail
        self.age, self.stuck, self.hit_set, self.reflectable = 0.0, False, set(), True

    def update(self, game, dt):
        self.age += dt
        if not self.stuck:
            self.vel.y += self.gravity * dt
            self.pos += self.vel * dt
            for pl in game.platforms:
                res = resolve_circle_rect(self.pos, self.radius, pl.rect)
                if not res:
                    continue
                n, pen = res
                if self.sticky:
                    self.pos += n * pen
                    self.vel = V2()
                    self.stuck = True
                elif self.bounce > 0:
                    self.pos += n * pen
                    vn = self.vel.dot(n)
                    if vn < 0:
                        self.vel -= n * vn * (1 + self.bounce)
                else:
                    self.kill(game)
                    return
        if self.trail and not self.stuck and random.random() < 0.5:
            game.burst(self.pos, self.color, 1, 25, 0.25, 3)
        for p in game.players:
            if not p.alive or p is self.owner or p in self.hit_set:
                continue
            if (p.pos - self.pos).length() < p.radius + self.radius:
                if p.has("shield") and self.reflectable:
                    self.vel = -self.vel
                    self.owner = p
                    self.hit_set.clear()
                    game.burst(self.pos, (150, 220, 255), 8, 200, 0.3)
                    continue
                self.hit_set.add(p)
                self.hit_player(game, p)
                if not self.alive:
                    return
        if self.proximity and self.age >= self.arm_time:
            for p in game.players:
                if p.alive and p is not self.owner and (p.pos - self.pos).length() < self.proximity + p.radius:
                    self.kill(game)
                    return
        self.life -= dt
        if self.life <= 0:
            self.kill(game)
        elif self.pos.x < -300 or self.pos.x > W + 300 or self.pos.y > H + 300 or self.pos.y < -900:
            self.alive = False

    def hit_player(self, game, p):
        direction = norm(self.vel, (p.pos - self.pos)) if self.vel.length() > 1 else norm(p.pos - self.pos)
        if self.damage or self.knockback:
            game.damage(p, self.damage, self.owner, direction * self.knockback)
        if self.on_hit:
            self.on_hit(game, self, p)
        if not self.pierce:
            self.kill(game)

    def kill(self, game):
        if not self.alive:
            return
        self.alive = False
        if self.on_end:
            self.on_end(game, self)

    def draw(self, surf):
        p = (int(self.pos.x), int(self.pos.y))
        if self.shape == "spike":
            d = norm(self.vel, (1, 0))
            tail = self.pos - d * self.radius * 4
            pygame.draw.line(surf, self.color, tail, self.pos, max(2, int(self.radius * 0.9)))
            pygame.draw.circle(surf, (255, 255, 255), p, max(2, int(self.radius * 0.6)))
        else:
            pygame.draw.circle(surf, self.color, p, int(self.radius))
            pygame.draw.circle(surf, darker(self.color), p, int(self.radius), 2)
            if self.proximity and self.age >= self.arm_time and int(self.age * 4) % 2 == 0:
                pygame.draw.circle(surf, (255, 60, 60), p, max(2, int(self.radius * 0.4)))


# ----------------------------------------------------------------------------
# POWERS  (the modding API)
# ----------------------------------------------------------------------------
POWERS = {}


def register_power(cls):
    """Class decorator: makes a Power available in the draft."""
    if not getattr(cls, "name", None):
        cls.name = cls.__name__
    POWERS[cls.name] = cls
    return cls


class Power:
    name = None
    description = ""
    cooldown = 3.0
    color = (200, 200, 200)
    # Optional hints so computer players know how to use a power (mods can ignore these):
    #   bot_hint: "attack" (aim at enemy; default) | "recover" (use when falling off the map)
    #             "defend" (use when threatened) | "heal" (use when hurt) | "buff" (use near enemies)
    bot_hint = "attack"
    bot_range = 700     # for "attack": only fire when an enemy is within this many px

    def __init__(self):
        self.cd_left = 0.0
        self.slot_index = 0

    def activate(self, player, game, aim):
        """Called when the slot button is pressed and off cooldown.
        Return False to cancel (cooldown not spent). aim = unit V2."""
        raise NotImplementedError

    def update(self, player, game, dt):
        """Called every frame while the owner is alive (passives, held abilities...)."""

    def on_round_start(self, player, game):
        pass

    # helpers for mod authors
    def held(self, player):
        d = player.device
        return self.slot_index < len(d.slot) and d.slot[self.slot_index]

    def muzzle(self, player, aim, extra=8):
        return player.pos + aim * (player.radius + extra)


def available_powers():
    names = CONFIG["enabled_powers"] or list(POWERS)
    return [POWERS[n] for n in names if n in POWERS and n not in CONFIG["disabled_powers"]]


# ----------------------------------------------------------------------------
# PLAYER
# ----------------------------------------------------------------------------
class Player:
    BASE_RADIUS = 22

    def __init__(self, idx, device):
        self.device = device
        self.wins = 0
        self.slots = []
        self.draft_queue, self.draft_i, self.draft_opts, self.cursor, self.draft_done = [], 0, [], 0, False
        self.bot_timer = 0.0
        self.set_index(idx)
        self.reset()

    def set_index(self, idx):
        self.idx = idx
        self.color = PLAYER_COLORS[idx % len(PLAYER_COLORS)]
        self.name = f"P{idx + 1}"

    def reset(self, pos=(0, 0)):
        self.pos, self.vel = V2(pos), V2()
        self.max_hp = CONFIG["player_max_hp"]
        self.hp, self.alive = self.max_hp, True
        self.fx, self.size_fx = {}, []
        self.cur_scale = 1.0
        self.on_ground = False
        self.coyote = self.jump_buf = self.flash = 0.0
        self.air_left = CONFIG["air_jumps"]
        self.jumping = False
        self.facing, self.aim = 1, V2(1, 0)

    # ---- status helpers (usable from mods) ----
    def has(self, name):
        return self.fx.get(name, 0) > 0

    def add_fx(self, name, t):
        self.fx[name] = max(self.fx.get(name, 0), t)

    def add_size(self, mult, t):
        self.size_fx.append([mult, t])

    @property
    def size_mult(self):
        m = 1.0
        for mult, _ in self.size_fx:
            m *= mult
        return clamp(m, 0.35, 3.5)

    @property
    def radius(self):
        return self.BASE_RADIUS * self.cur_scale

    @property
    def mass(self):
        return self.cur_scale ** 2

    # ---- per-frame ----
    def update(self, game, dt, can_act):
        dev = self.device
        for k in list(self.fx):
            self.fx[k] -= dt
            if self.fx[k] <= 0:
                del self.fx[k]
        self.size_fx = [[m, t - dt] for m, t in self.size_fx if t - dt > 0]
        self.cur_scale += (self.size_mult - self.cur_scale) * min(1.0, dt * 8)
        self.flash = max(0.0, self.flash - dt)
        for pw in self.slots:
            pw.cd_left = max(0.0, pw.cd_left - dt)
            pw.update(self, game, dt)

        stunned = self.has("stun") or not can_act
        mx = dev.move.x
        if abs(mx) > 0.25:
            self.facing = 1 if mx > 0 else -1
        self.aim = norm(dev.aim_vec) if dev.aim_vec.length_squared() > 0.01 else V2(self.facing, 0)

        # horizontal movement
        speed = CONFIG["move_speed"] * clamp(1.2 - 0.2 * self.cur_scale, 0.8, 1.3)
        target = 0.0 if stunned else mx * speed
        vx = self.vel.x
        if abs(vx) > speed * 1.05 and (target == 0 or vx * target > 0):
            drag = 1200 if self.on_ground else 900
            vx -= math.copysign(min(drag * dt, abs(vx) - speed), vx)
        else:
            step = (2600 if self.on_ground else 1500) * dt
            vx += clamp(target - vx, -step, step)
        self.vel.x = vx

        # jumping
        self.jump_buf = 0.12 if (dev.jump_p and not stunned) else self.jump_buf - dt
        if self.jump_buf > 0 and not stunned:
            if self.coyote > 0:
                self.vel.y = -CONFIG["jump_speed"]
                self.coyote, self.jump_buf, self.jumping = 0.0, 0.0, True
            elif self.air_left > 0:
                self.vel.y = -CONFIG["jump_speed"] * 0.9
                self.air_left -= 1
                self.jump_buf, self.jumping = 0.0, True
                game.burst(self.pos + V2(0, self.radius), self.color, 8, 150, 0.3)
        if self.jumping and not dev.jump and self.vel.y < -150:
            self.vel.y *= 0.5
            self.jumping = False
        if self.vel.y >= 0:
            self.jumping = False

        # abilities
        if not stunned:
            for i, pw in enumerate(self.slots):
                if i < len(dev.slot_p) and dev.slot_p[i] and pw.cd_left <= 0:
                    if pw.activate(self, game, V2(self.aim)) is not False:
                        pw.cd_left = pw.cooldown * CONFIG["cooldown_scale"]

        # physics
        if not self.has("nograv"):
            self.vel.y = min(self.vel.y + CONFIG["gravity"] * dt, 1600)
        self.pos += self.vel * dt
        self.on_ground = False
        for pl in game.platforms:
            res = resolve_circle_rect(self.pos, self.radius, pl.rect)
            if res:
                n, pen = res
                self.pos += n * pen
                vn = self.vel.dot(n)
                if vn < 0:
                    self.vel -= n * vn * (1.35 if -vn > 600 else 1.0)
                if n.y < -0.5:
                    self.on_ground = True
        if self.on_ground:
            self.coyote = 0.1
            self.air_left = CONFIG["air_jumps"]
        else:
            self.coyote -= dt

    def draw(self, surf):
        r = self.radius
        p = (int(self.pos.x), int(self.pos.y))
        col = (255, 255, 255) if self.flash > 0 else self.color
        pygame.draw.circle(surf, col, p, int(r))
        pygame.draw.circle(surf, darker(self.color, 0.5), p, int(r), 3)
        for sx in (-0.3, 0.45):
            ex = self.pos.x + self.facing * r * 0.2 + sx * r
            ey = self.pos.y - r * 0.2
            pygame.draw.circle(surf, (255, 255, 255), (int(ex), int(ey)), max(2, int(r * 0.26)))
            pygame.draw.circle(surf, (20, 20, 30), (int(ex + self.aim.x * r * 0.1), int(ey + self.aim.y * r * 0.1)),
                               max(1, int(r * 0.12)))
        d = self.pos + self.aim * (r + 12)
        pygame.draw.circle(surf, lighter(self.color, 0.5), (int(d.x), int(d.y)), 4)
        if self.has("shield"):
            pygame.draw.circle(surf, (150, 220, 255), p, int(r + 7), 3)
        bw = 46
        bx, by = self.pos.x - bw / 2, self.pos.y - r - 16
        pygame.draw.rect(surf, (30, 30, 40), (bx - 1, by - 1, bw + 2, 8))
        pygame.draw.rect(surf, (90, 230, 110), (bx, by, bw * clamp(self.hp / self.max_hp, 0, 1), 6))
        draw_text(surf, self.name, 20, (self.pos.x, by - 10), self.color)


# ----------------------------------------------------------------------------
# MODS
# ----------------------------------------------------------------------------
LOADED_MODS = []


def load_mods():
    MODS_DIR.mkdir(exist_ok=True)
    for path in sorted(MODS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"bopl_mod_{path.stem}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            LOADED_MODS.append(path.name)
        except Exception:
            print(f"[mods] failed to load {path.name}:")
            traceback.print_exc()


# ----------------------------------------------------------------------------
# GAME
# ----------------------------------------------------------------------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Bopl-style Brawler")
        flags = pygame.SCALED | pygame.RESIZABLE
        if CONFIG["fullscreen"]:
            flags |= pygame.FULLSCREEN
        try:
            self.screen = pygame.display.set_mode((W, H), flags)
        except pygame.error:
            self.screen = pygame.display.set_mode((W, H))
        self.clock = pygame.time.Clock()
        self.running = True
        self.dt = 1 / 60
        self.state = "lobby"
        self.players, self.platforms, self.entities, self.particles = [], [], [], []
        self.round_no, self.countdown, self.end_timer, self.winner = 0, 0.0, 0.0, None
        self.cur_map, self.last_map = None, None
        self.kb_devices = [KeyboardDevice(s) for s in CONFIG["keyboards"]]
        self.joy_devices = {}
        self.touch_dev = None                  # created by the lobby's "Add touch player" button
        self.pointers = {}                     # active mouse / finger positions (only tracked for the touch player)
        self.touch_btn = pygame.Rect(W - 260, H - 58, 244, 46)
        self._touch_toggled = 0
        if not WEB:
            for i in range(pygame.joystick.get_count()):
                self.add_joystick(i)
        self.bg = pygame.Surface((W, H))
        for y in range(H):
            k = y / H
            pygame.draw.line(self.bg, (int(18 + 22 * k), int(20 + 18 * k), int(40 + 30 * k)), (0, y), (W, y))

    @property
    def devices(self):
        return self.kb_devices + list(self.joy_devices.values()) + ([self.touch_dev] if self.touch_dev else [])

    def toggle_touch(self):
        if pygame.time.get_ticks() - self._touch_toggled < 400:      # a tap can arrive as finger + mouse events
            return
        self._touch_toggled = pygame.time.get_ticks()
        if self.touch_dev:
            owner = next((p for p in self.players if p.device is self.touch_dev), None)
            if owner:
                self.players.remove(owner)
                for i, p in enumerate(self.players):
                    p.set_index(i)
            self.touch_dev = None
            self.pointers.clear()
        elif len(self.players) < CONFIG["max_players"]:
            self.touch_dev = TouchDevice(self)
            self.players.append(Player(len(self.players), self.touch_dev))

    def pointer_event(self, key, pos, down=None):
        """down=True/False for press/release, None for movement."""
        if down and self.state == "lobby" and self.touch_btn.collidepoint(pos):
            self.toggle_touch()
        if not self.touch_dev:
            return
        if down is False:
            self.pointers.pop(key, None)
        elif down or key in self.pointers:
            self.pointers[key] = pos

    def add_joystick(self, index):
        try:
            joy = pygame.joystick.Joystick(index)
            joy.init()
            iid = joy.get_instance_id()
            if iid not in self.joy_devices:
                self.joy_devices[iid] = JoyDevice(joy)
                print("[input] controller connected:", joy.get_name())
        except pygame.error:
            pass

    def poll_web_pads(self):
        """Browser only: browsers expose pads after the first button press, so poll every frame."""
        try:
            pads = _js_navigator.getGamepads()
            seen = set()
            for i in range(int(pads.length)):
                p = pads[i]
                if p is None or not p.connected:
                    continue
                seen.add(p.index)
                dev = self.joy_devices.get(p.index)
                if dev is None:
                    self.joy_devices[p.index] = JoyDevice(WebJoy(p))
                    print("[input] controller connected:", p.id)
                else:
                    dev.joy.pad = p
            for iid in list(self.joy_devices):
                if iid not in seen:
                    dev = self.joy_devices.pop(iid)
                    dev.joy = None
                    print("[input] controller disconnected:", dev.name)
        except Exception:
            pass

    # ---- API used by powers --------------------------------------------------
    def spawn(self, entity):
        self.entities.append(entity)
        return entity

    def add_platform(self, rect, life=None, color=(74, 86, 120)):
        pl = Platform(rect, life, color)
        self.platforms.append(pl)
        return pl

    def circle_blocked(self, pos, r):
        return any(resolve_circle_rect(pos, r, pl.rect) for pl in self.platforms)

    def burst(self, pos, color, n=12, speed=250, life=0.5, size=4, direction=None, spread=math.tau):
        for _ in range(n):
            ang = random.uniform(0, math.tau) if direction is None else \
                math.atan2(direction.y, direction.x) + random.uniform(-spread / 2, spread / 2)
            sp = random.uniform(0.3, 1.0) * speed
            lf = life * random.uniform(0.6, 1.0)
            self.particles.append([pos.x, pos.y, math.cos(ang) * sp, math.sin(ang) * sp, lf, lf, color, size])

    def damage(self, target, amount, source=None, impulse=V2()):
        if not target.alive or target.has("shield"):
            return
        if amount:
            target.hp -= amount
        if amount >= 1 or impulse.length() > 50:
            target.flash = 0.12
            self.burst(target.pos, target.color, 6, 200, 0.3)
        frac = clamp(target.hp / target.max_hp, 0, 1)
        bonus = 1 + (1 - frac) * CONFIG["low_hp_knockback_bonus"]
        target.vel += impulse * bonus / max(0.4, target.cur_scale)
        if target.hp <= 0:
            self.kill_player(target)

    def explosion(self, pos, radius, damage, knockback, owner=None, color=(255, 180, 60), hurt_owner=True):
        for p in self.players:
            if not p.alive or (p is owner and not hurt_owner):
                continue
            d = p.pos - pos
            dist = d.length()
            reach = radius + p.radius
            if dist < reach:
                f = max(0.2, 1 - dist / reach)
                mult = 0.6 if p is owner else 1.0
                self.damage(p, damage * f * mult, owner, norm(d) * knockback * f * mult)
        self.burst(pos, color, 30, 500, 0.6, 5)
        self.spawn(Zone(owner, pos, radius, 0.3, None, color, expand=True))

    def kill_player(self, p):
        if p.alive:
            p.alive = False
            self.burst(p.pos, p.color, 40, 550, 0.9, 6)
            self.spawn(Zone(None, p.pos, 90, 0.4, None, p.color, expand=True))

    # ---- state machine -------------------------------------------------------
    def reset_to_lobby(self):
        self.state = "lobby"
        for p in self.players:
            p.wins, p.slots = 0, []
        self.round_no = 0

    def start_match(self):
        for p in self.players:
            p.wins, p.slots = 0, []
        self.round_no = 0
        self.start_draft()

    def start_draft(self):
        if not available_powers():
            print("[error] no powers available (check enabled_powers / disabled_powers)")
            self.reset_to_lobby()
            return
        self.state = "draft"
        S = CONFIG["power_slots"]
        for p in self.players:
            if len(p.slots) != S:
                p.slots = [None] * S
                p.draft_queue = list(range(S))
            else:
                p.draft_queue = random.sample(range(S), min(CONFIG["redraft_slots_per_round"], S))
            p.draft_i, p.draft_done = 0, not p.draft_queue
            self.new_options(p)

    def new_options(self, p):
        if p.draft_done:
            return
        have = {pw.name for pw in p.slots if pw}
        pool = [c for c in available_powers() if c.name not in have] or available_powers()
        p.draft_opts = random.sample(pool, min(CONFIG["draft_choices"], len(pool)))
        p.cursor = 0
        p.bot_timer = random.uniform(0.5, 1.4)

    def pick(self, p, index):
        slot = p.draft_queue[p.draft_i]
        pw = p.draft_opts[index]()
        pw.slot_index = slot
        p.slots[slot] = pw
        p.draft_i += 1
        if p.draft_i >= len(p.draft_queue):
            p.draft_done = True
        else:
            self.new_options(p)

    def update_draft(self, dt):
        for p in self.players:
            if p.draft_done:
                continue
            dev = p.device
            if dev.is_bot:
                p.bot_timer -= dt
                if p.bot_timer <= 0:
                    self.pick(p, dev.choose(p.draft_opts))
                continue
            if dev.nav_p:
                p.cursor = (p.cursor + dev.nav_p) % len(p.draft_opts)
            if dev.jump_p:
                self.pick(p, p.cursor)
        if all(p.draft_done for p in self.players):
            self.start_round()

    def spawn_points(self, n):
        tops = sorted((pl.rect for pl in self.platforms if pl.rect.w >= 60), key=lambda r: r.x)
        total = sum(r.w for r in tops)
        pts = []
        for k in range(n):
            t = (k + 0.5) / n * total
            for r in tops:
                if t <= r.w:
                    pts.append((r.x + t, r.y))
                    break
                t -= r.w
        random.shuffle(pts)
        return pts

    def start_round(self):
        self.round_no += 1
        choices = [m for m in MAPS if m is not self.last_map] or MAPS
        self.cur_map = random.choice(choices)
        self.last_map = self.cur_map
        self.platforms = [Platform(r) for r in self.cur_map["platforms"]]
        self.entities, self.particles = [], []
        pts = self.spawn_points(len(self.players))
        for p, (x, y) in zip(self.players, pts):
            p.reset((x, y - p.BASE_RADIUS - 2))
            for pw in p.slots:
                pw.cd_left = 0.5
                pw.on_round_start(p, self)
        self.countdown, self.winner = 1.2, None
        self.state = "play"

    def update_play(self, dt):
        if self.countdown > 0:
            self.countdown -= dt
        can_act = self.countdown <= 0
        for p in self.players:
            if p.alive:
                p.update(self, dt, can_act)
        self.player_collisions()
        for e in self.entities:
            e.update(self, dt)
        self.entities = [e for e in self.entities if e.alive]
        for pl in self.platforms:
            pl.update(dt)
        self.platforms = [pl for pl in self.platforms if not pl.expired]
        for pt in self.particles:
            pt[0] += pt[2] * dt
            pt[1] += pt[3] * dt
            pt[2] *= 0.97
            pt[3] *= 0.97
            pt[4] -= dt
        self.particles = [pt for pt in self.particles if pt[4] > 0]
        for p in self.players:
            if p.alive and (p.pos.y > H + 250 or p.pos.x < -250 or p.pos.x > W + 250 or p.pos.y < -700):
                self.kill_player(p)
        if self.state == "play":
            alive = [p for p in self.players if p.alive]
            if len(alive) <= (1 if len(self.players) > 1 else 0):
                self.winner = alive[0] if alive else None
                if self.winner:
                    self.winner.wins += 1
                self.end_timer = 2.5
                self.state = "round_end"

    def update_round_end(self, dt):
        self.update_play_world_only(dt)
        self.end_timer -= dt
        if self.end_timer <= 0:
            if self.winner and self.winner.wins >= CONFIG["rounds_to_win"]:
                self.state = "match_end"
            else:
                self.start_draft()

    def update_play_world_only(self, dt):
        st = self.state
        self.state = "round_end_internal"
        self.update_play(dt)
        self.state = st

    def update_match_end(self, dt):
        if any(p.device.start_p or p.device.jump_p for p in self.players):
            self.reset_to_lobby()

    def player_collisions(self):
        ps = [p for p in self.players if p.alive]
        for i in range(len(ps)):
            for j in range(i + 1, len(ps)):
                a, b = ps[i], ps[j]
                d = b.pos - a.pos
                dist = d.length()
                min_d = a.radius + b.radius
                if dist >= min_d:
                    continue
                n = norm(d, (1, 0)) if dist > 1e-4 else V2(1, 0)
                ma, mb = a.mass, b.mass
                ov = min_d - dist
                a.pos -= n * ov * mb / (ma + mb)
                b.pos += n * ov * ma / (ma + mb)
                rv = (b.vel - a.vel).dot(n)
                if rv < 0:
                    j_ = -(1 + 0.6) * rv / (1 / ma + 1 / mb)
                    a.vel -= n * j_ / ma
                    b.vel += n * j_ / mb

    def update_lobby(self, dt):
        for d in self.devices:
            owner = next((p for p in self.players if p.device is d), None)
            if owner is None:
                if d.jump_p and len(self.players) < CONFIG["max_players"]:
                    self.players.append(Player(len(self.players), d))
            elif d.back_p:
                self.players.remove(owner)
                for i, p in enumerate(self.players):
                    p.set_index(i)
        if any(p.device.start_p for p in self.players):
            self.try_start()

    def add_bot(self):
        if len(self.players) >= CONFIG["max_players"]:
            return
        dev = BotDevice()
        p = Player(len(self.players), dev)
        dev.game, dev.player = self, p
        self.players.append(p)

    def remove_bot(self):
        for p in reversed(self.players):
            if p.device.is_bot:
                self.players.remove(p)
                break
        for i, p in enumerate(self.players):
            p.set_index(i)

    def try_start(self):
        if self.state == "lobby":
            while len(self.players) < CONFIG["bots_fill_to"] and len(self.players) < CONFIG["max_players"]:
                self.add_bot()
        if len(self.players) >= CONFIG["min_players"]:
            self.start_match()

    # ---- events / loop -------------------------------------------------------
    def handle_event(self, e):
        if e.type == pygame.QUIT:
            self.running = False
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                if self.state == "lobby":
                    self.running = WEB      # can't close a browser tab from inside it
                else:
                    self.reset_to_lobby()
            elif e.key == pygame.K_F11:
                pygame.display.toggle_fullscreen()
            elif e.key == pygame.K_RETURN and self.state == "lobby":
                self.try_start()
            elif e.key == pygame.K_F2 and self.state == "lobby":
                self.add_bot()
            elif e.key == pygame.K_F3 and self.state == "lobby":
                self.remove_bot()
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.pointer_event("mouse", e.pos, True)
        elif e.type == pygame.MOUSEMOTION:
            self.pointer_event("mouse", e.pos)
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self.pointer_event("mouse", e.pos, False)
        elif e.type in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
            self.pointer_event(("finger", e.finger_id), (e.x * W, e.y * H),
                               True if e.type == pygame.FINGERDOWN else False if e.type == pygame.FINGERUP else None)
        elif e.type == pygame.JOYDEVICEADDED and not WEB:
            self.add_joystick(e.device_index)
        elif e.type == pygame.JOYDEVICEREMOVED and not WEB:
            dev = self.joy_devices.pop(e.instance_id, None)
            if dev:
                dev.joy = None
                print("[input] controller disconnected:", dev.name)

    async def run(self):
        while self.running:
            dt = min(self.clock.tick(0 if WEB else CONFIG["fps"]) / 1000.0, 1 / 30)
            for e in pygame.event.get():
                self.handle_event(e)
            self.dt = dt
            if WEB:
                self.poll_web_pads()
            for d in self.devices:
                d.update()
            for p in self.players:
                if p.device.is_bot:
                    p.device.update()
            getattr(self, "update_" + self.state)(dt)
            self.draw()
            pygame.display.flip()
            await asyncio.sleep(1 / CONFIG["fps"] if WEB else 0)   # hand control back to the browser
        pygame.quit()

    # ---- drawing -------------------------------------------------------------
    def draw_icon(self, rect, pw, show_cd=True):
        pygame.draw.rect(self.screen, darker(pw.color, 0.45), rect, border_radius=8)
        pygame.draw.rect(self.screen, pw.color, rect, 3, border_radius=8)
        label = "".join(w[0] for w in pw.name.split())[:3].upper() if " " in pw.name else pw.name[:3].upper()
        draw_text(self.screen, label, max(16, int(rect.w * 0.45)), rect.center)
        if show_cd and getattr(pw, "cd_left", 0) > 0:
            total = max(0.01, pw.cooldown * CONFIG["cooldown_scale"])
            h = int(rect.h * clamp(pw.cd_left / total, 0, 1))
            s = pygame.Surface((rect.w, h), pygame.SRCALPHA)
            s.fill((0, 0, 0, 160))
            self.screen.blit(s, (rect.x, rect.y))

    def draw_hud(self):
        n = len(self.players)
        if not n:
            return
        pw_ = W / n
        S = CONFIG["power_slots"]
        for i, p in enumerate(self.players):
            x0 = i * pw_
            draw_text(self.screen, p.name + ("" if p.alive else "  (out)"), 26, (x0 + 20, H - 92), p.color, center=False)
            pygame.draw.rect(self.screen, (30, 30, 40), (x0 + 20, H - 70, pw_ - 40, 12), border_radius=4)
            pygame.draw.rect(self.screen, (90, 230, 110),
                             (x0 + 20, H - 70, (pw_ - 40) * clamp(p.hp / p.max_hp, 0, 1), 12), border_radius=4)
            size = int(min(46, (pw_ - 40) / max(1, S) - 6))
            for k, pw in enumerate(p.slots):
                if pw:
                    self.draw_icon(pygame.Rect(x0 + 20 + k * (size + 6), H - 52, size, size), pw)
        # win dots
        for i, p in enumerate(self.players):
            x = W / 2 - n * 70 / 2 + i * 70 + 35
            draw_text(self.screen, p.name, 22, (x, 18), p.color)
            for w in range(CONFIG["rounds_to_win"]):
                pygame.draw.circle(self.screen, p.color, (int(x - 14 + w * 14), 40), 5, 0 if w < p.wins else 2)

    def draw(self):
        s = self.screen
        s.blit(self.bg, (0, 0))
        getattr(self, "draw_" + self.state)()
        if self.touch_dev:
            self.draw_touch()

    def draw_touch(self):
        dev = self.touch_dev
        owner = next((p for p in self.players if p.device is dev), None)
        labels = {"up": "^", "down": "v", "left": "<", "right": ">", "jump": "JUMP", "back": "BACK", "start": "START"}
        for name, r in dev.buttons.items():
            on = name in dev.down
            pw = None
            if name.startswith("slot") and owner:
                i = int(name[4:])
                pw = owner.slots[i] if i < len(owner.slots) else None
            ov = pygame.Surface(r.size, pygame.SRCALPHA)
            ov.fill((255, 255, 255, 110 if on else 45))
            self.screen.blit(ov, r)
            pygame.draw.rect(self.screen, (255, 255, 255), r, 2, border_radius=10)
            if pw:
                self.draw_icon(r.inflate(-8, -8), pw)
            else:
                label = labels.get(name) or str(int(name[4:]) + 1)        # slot buttons show their number
                draw_text(self.screen, label, 24 if name in ("back", "start", "jump") else 36, r.center)

    def draw_world(self):
        s = self.screen
        for pl in self.platforms:
            pl.draw(s)
        for e in self.entities:
            e.draw(s)
        for p in self.players:
            if p.alive:
                p.draw(s)
        for x, y, vx, vy, life, mx, col, size in self.particles:
            r = max(1, int(size * life / mx))
            pygame.draw.circle(s, col, (int(x), int(y)), r)

    def draw_play(self):
        self.draw_world()
        self.draw_hud()
        if self.countdown > 0:
            draw_text(self.screen, f"Round {self.round_no}  -  {self.cur_map['name']}", 54, (W / 2, 120))
            draw_text(self.screen, "GET READY", 36, (W / 2, 170))

    def draw_round_end(self):
        self.draw_world()
        self.draw_hud()
        msg = f"{self.winner.name} wins the round!" if self.winner else "Draw!"
        draw_text(self.screen, msg, 80, (W / 2, H / 2 - 40), self.winner.color if self.winner else (255, 255, 255))

    def draw_match_end(self):
        self.draw_world()
        self.draw_hud()
        draw_text(self.screen, f"{self.winner.name} WINS THE MATCH!", 96, (W / 2, H / 2 - 40), self.winner.color)
        draw_text(self.screen, "Press Start / Jump to return to the lobby", 34, (W / 2, H / 2 + 30))

    def draw_draft(self):
        s = self.screen
        n = len(self.players)
        pw_ = W / n
        draw_text(s, f"CHOOSE YOUR POWERS  -  round {self.round_no + 1}", 44, (W / 2, 40))
        draw_text(s, "Left/Right to browse, Jump to pick", 26, (W / 2, 76), (200, 200, 210))
        for i, p in enumerate(self.players):
            x0 = i * pw_
            draw_text(s, p.name, 40, (x0 + pw_ / 2, 125), p.color)
            if p.draft_done:
                draw_text(s, "READY!", 48, (x0 + pw_ / 2, 300), (120, 255, 140))
            else:
                slot = p.draft_queue[p.draft_i]
                draw_text(s, f"Slot {slot + 1}   ({p.draft_i + 1}/{len(p.draft_queue)})", 28, (x0 + pw_ / 2, 160), (210, 210, 220))
                cw, ch = pw_ - 30, 104
                for k, cls in enumerate(p.draft_opts):
                    r = pygame.Rect(x0 + 15, 190 + k * (ch + 10), cw, ch)
                    pygame.draw.rect(s, darker(cls.color, 0.35), r, border_radius=10)
                    pygame.draw.rect(s, (255, 255, 255) if k == p.cursor else darker(cls.color, 0.8), r,
                                     5 if k == p.cursor else 2, border_radius=10)
                    draw_text(s, cls.name, 34, (r.x + 14, r.y + 10), cls.color, center=False)
                    for li, line in enumerate(wrap(cls.description, 22, cw - 28)[:3]):
                        draw_text(s, line, 22, (r.x + 14, r.y + 44 + li * 20), (230, 230, 235), center=False, shadow=False)
            size = int(min(52, (pw_ - 40) / max(1, CONFIG["power_slots"]) - 6))
            for k, pw in enumerate(p.slots):
                r = pygame.Rect(x0 + 20 + k * (size + 6), H - 90, size, size)
                if pw:
                    self.draw_icon(r, pw, show_cd=False)
                else:
                    pygame.draw.rect(s, (70, 70, 85), r, 2, border_radius=8)

    def draw_lobby(self):
        s = self.screen
        draw_text(s, "BOPL-STYLE BRAWLER", 100, (W / 2, 90), (255, 220, 90))
        S = CONFIG["power_slots"]
        info = (f"{S} power slots  |  up to {CONFIG['max_players']} players  |  first to {CONFIG['rounds_to_win']} rounds  |  "
                f"{len(available_powers())} powers loaded" + (f"  |  mods: {', '.join(LOADED_MODS)}" if LOADED_MODS else ""))
        draw_text(s, info, 24, (W / 2, 150), (190, 190, 205))
        n = CONFIG["max_players"]
        y, rh = 200, min(62, int(330 / max(1, n)))
        for i in range(n):
            r = pygame.Rect(W / 2 - 330, y + i * rh, 660, rh - 10)
            if i < len(self.players):
                p = self.players[i]
                pygame.draw.rect(s, darker(p.color, 0.45), r, border_radius=10)
                pygame.draw.rect(s, p.color, r, 3, border_radius=10)
                pygame.draw.circle(s, p.color, (r.x + 30, r.centery), 16)
                draw_text(s, f"{p.name}   {p.device.name}", 30, (r.x + 62, r.centery), center=False)
            else:
                pygame.draw.rect(s, (60, 62, 80), r, 2, border_radius=10)
                draw_text(s, "waiting...", 26, r.center, (110, 112, 130))
        y2 = 200 + n * rh + 14
        draw_text(s, "JOIN: press JUMP on a controller (A) or keyboard.   LEAVE: Back / Backspace.", 26, (W / 2, y2), (230, 230, 240))
        for k, sch in enumerate(CONFIG["keyboards"]):
            line = f"{sch['name']}: move {sch['left']}/{sch['right']}/{sch['up']}/{sch['down']}  jump {sch['jump']}  powers {' '.join(sch['slots'][:S])}"
            draw_text(s, line, 21, (W / 2, y2 + 30 + k * 22), (170, 175, 195))
        draw_text(s, f"Controllers detected: {len(self.joy_devices)}   (stick = move + aim, A = jump, X/B/Y/bumpers/triggers = powers)",
                  21, (W / 2, y2 + 30 + len(CONFIG['keyboards']) * 22), (170, 175, 195))
        draw_text(s, "F2: add computer player    F3: remove computer player", 21,
                  (W / 2, y2 + 52 + len(CONFIG['keyboards']) * 22), (170, 175, 195))
        r = self.touch_btn
        pygame.draw.rect(s, (60, 62, 80), r, border_radius=10)
        pygame.draw.rect(s, (255, 255, 255) if self.touch_dev else (150, 155, 180), r, 2, border_radius=10)
        draw_text(s, "Remove touch player" if self.touch_dev else "+ Add touch player", 26, r.center)
        ready = len(self.players) >= CONFIG["min_players"]
        draw_text(s, "Press START / ENTER to begin" if ready else f"Need {CONFIG['min_players']} players to start",
                  40, (W / 2, H - 28), (120, 255, 140) if ready else (255, 150, 120))


async def main():
    pygame.init()
    load_mods()
    await Game().run()


if __name__ == "__main__":
    try:
        asyncio.get_running_loop().create_task(main())   # PyScript already has an event loop
    except RuntimeError:
        asyncio.run(main())                              # plain desktop Python
