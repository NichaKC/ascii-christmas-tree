"""
ASCII Christmas Tree — a rotating 3D Christmas tree drawn with ASCII characters.
Sequence: the tree grows bottom-up -> gold garland -> baubles -> twinkling lights
          -> gifts -> star on top -> "MERRY CHRISTMAS 2026" (with snow falling throughout).

Install:  pip install pygame numpy
Run:      python christmas_tree.py
Keys:     Space pause/resume · R restart · S screenshot · Esc quit
"""
import math
import time

import numpy as np
import pygame

# ---------------------------------------------------------------- window
TITLE = "ASCII Christmas Tree"
CW, CH, FONT_PX = 9, 14, 15          # character cell size (px)
COLS, ROWS = 88, 74                  # grid size in cells
W, H = COLS * CW, ROWS * CH
MONO = "consolas,menlo,dejavusansmono,couriernew,monospace"
HINT = "Space pause · R restart · S screenshot · Esc quit"
FPS = 30

# ---------------------------------------------------------------- scene
GROUND, Y0, Y1 = 0.0, 0.32, 2.05     # ground, bottom of foliage, tree top
R_BASE = 0.70                        # foliage radius at the base
CAM_D, CAM_Y, SCALE = 4.4, 1.0, 1600
SPIN = 0.32                          # rad/s
MESSAGE = "MERRY CHRISTMAS 2026"

# timeline (seconds)
T_GROW = (0.2, 6.0)
T_GARLAND = (5.5, 8.5)
T_BALLS = (7.5, 10.0)
T_LIGHTS = (9.0, 11.5)
T_GIFTS = (10.5, 12.5)
T_STAR = 12.5
T_MSG = 13.5

# colours
GREEN = np.array([0.10, 0.62, 0.20])
DARK_GREEN = np.array([0.03, 0.18, 0.06])
WHITE = np.array([0.95, 0.97, 1.00])
GOLD = np.array([1.00, 0.78, 0.22])
TINSEL = np.array([1.00, 0.86, 0.45])
RED = np.array([0.90, 0.12, 0.12])
BAUBLE_GOLD = np.array([1.00, 0.70, 0.15])
SILVER = np.array([0.80, 0.82, 0.88])
BLUE_BOX = np.array([0.18, 0.30, 0.95])
GREEN_BOX = np.array([0.15, 0.65, 0.25])
BROWN = np.array([0.42, 0.25, 0.12])
WARM = np.array([1.00, 0.80, 0.35])
DIM = np.array([96, 104, 122])
ACCENT = np.array([255, 196, 90])

# character ramp per object kind (dark -> bright)
RAMPS = {
    "needle": ".:-=+*xvXW&%#",
    "inner":  ".:",
    "trunk":  ".:=#H",
    "garland": "-~=*",
    "ball":   "o0O8@",
    "light":  "oO@",
    "gift":   ".:+xX#",
    "ribbon": "+xX#",
}
KINDS = list(RAMPS)
EMISSIVE = {"light", "garland"}
TAU = 2 * math.pi


def envelope(y):
    """Foliage radius at height y (a cone that narrows towards the top)."""
    u = np.clip((np.asarray(y) - Y0) / (Y1 - Y0), 0, 1)
    return R_BASE * (1 - u) ** 1.05


def grow_time(y):
    u = np.clip((np.asarray(y) - GROUND) / (Y1 - GROUND), 0, 1)
    return T_GROW[0] + (T_GROW[1] - T_GROW[0]) * u


def fib_sphere(n):
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    th = math.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(th) * np.sin(phi), np.cos(phi), np.sin(th) * np.sin(phi)], 1)


def unit(v):
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9)


class Parts:
    """Collects every 3D point of the scene: position, normal, colour, kind, appear time."""

    def __init__(self):
        self.chunks = []

    def add(self, p, nrm, col, kind, t0, phase=0.0, pop=None):
        p = np.asarray(p, float)
        n = len(p)
        self.chunks.append(dict(
            p=p,
            n=unit(np.broadcast_to(np.asarray(nrm, float), (n, 3)).copy()),
            c=np.broadcast_to(np.asarray(col, float), (n, 3)).copy(),
            k=np.full(n, KINDS.index(kind)),
            t0=np.broadcast_to(np.asarray(t0, float), (n,)).copy(),
            ph=np.broadcast_to(np.asarray(phase, float), (n,)).copy(),
            pop=np.full(n, pop is not None),
            ctr=np.broadcast_to(np.asarray(pop if pop is not None else (0, 0, 0), float), (n, 3)).copy()))

    def done(self):
        return {key: np.concatenate([c[key] for c in self.chunks]) for key in self.chunks[0]}


def build():
    rng = np.random.default_rng(7)
    q = Parts()
    tips = []

    # needles: whorls of drooping branches, denser and longer at the bottom
    for y in np.linspace(Y0 + 0.02, Y1 - 0.06, 24):
        u = (y - Y0) / (Y1 - Y0)
        R = envelope(y) + 0.05
        nb = int(6 + 12 * (1 - u))
        for b in range(nb):
            a = TAU * (b + 0.5 * rng.random()) / nb + y * 7
            L = R * rng.uniform(0.85, 1.08)
            n = int(25 + 270 * L)
            s = rng.random(n) ** 0.65
            d = np.array([math.cos(a), 0, math.sin(a)])
            side = np.array([-math.sin(a), 0, math.cos(a)])
            spread = (0.025 + 0.09 * s) * rng.normal(0, 1, n)
            sl = s * L
            p = d * sl[:, None] + side * spread[:, None]
            p[:, 1] = y + 0.06 - 0.20 * sl ** 2 + 0.012 * rng.normal(0, 1, n)
            nrm = d * 0.75 + np.array([0, 0.55, 0]) + 0.3 * rng.normal(0, 1, (n, 3))
            snow = (s > 0.55) & (rng.random(n) < 0.07)
            green = GREEN * rng.uniform(0.75, 1.15, (n, 1)) + np.array([0, 0.05, 0]) * rng.normal(0, 1, (n, 1))
            col = np.where(snow[:, None], WHITE, green)
            q.add(p, nrm, col, "needle", grow_time(p[:, 1]) + 0.25 * s)
            tl = 0.93 * L
            tips.append(d * tl + [0, y + 0.06 - 0.20 * tl ** 2, 0])

    # dark inner cone so nothing shows through the branches
    m = 6000
    y = Y0 + (Y1 - Y0) * rng.random(m) ** 1.3
    phi = rng.random(m) * TAU
    r = envelope(y) * 0.55
    p = np.stack([np.cos(phi) * r, y, np.sin(phi) * r], 1)
    q.add(p, np.stack([np.cos(phi), np.full(m, .3), np.sin(phi)], 1), DARK_GREEN, "inner", grow_time(y))

    # trunk
    m = 1500
    y = GROUND + rng.random(m) * (Y0 + 0.1 - GROUND)
    phi = rng.random(m) * TAU
    nrm = np.stack([np.cos(phi), np.zeros(m), np.sin(phi)], 1)
    q.add(nrm * 0.08 + np.stack([np.zeros(m), y, np.zeros(m)], 1), nrm, BROWN, "trunk", grow_time(y))

    # garland: a gold spiral around the tree, drooping in swags
    u = np.linspace(0, 1, 2600)
    turns = 3.6
    yg = Y0 + 0.15 + (Y1 - Y0 - 0.45) * u
    ag = TAU * turns * u + 0.9
    swag = -0.07 * np.abs(np.sin(ag * 2.5))
    rg = envelope(yg) + 0.07
    line = np.stack([np.cos(ag) * rg, yg + swag, np.sin(ag) * rg], 1)
    for _ in range(4):
        jit = line + 0.012 * rng.normal(0, 1, line.shape)
        nrm = np.stack([np.cos(ag), np.full_like(u, 0.3), np.sin(ag)], 1)
        q.add(jit, nrm, TINSEL, "garland", T_GARLAND[0] + u * (T_GARLAND[1] - T_GARLAND[0]),
              phase=rng.random(len(u)) * TAU)

    # baubles: mostly red, some gold and silver
    sphere = fib_sphere(160)
    for k in range(34):
        uu = (k + rng.random()) / 34
        yb = Y0 + 0.08 + uu * (Y1 - Y0 - 0.38)
        a = k * 2.39996 + rng.random() * 0.4
        c = np.array([math.cos(a), 0, math.sin(a)]) * envelope(yb) * 0.95 + [0, yb - 0.03, 0]
        rad = 0.058 + 0.032 * (1 - uu)
        col = [RED, RED, BAUBLE_GOLD, SILVER][k % 4]
        q.add(c + sphere * rad, sphere, col, "ball",
              T_BALLS[0] + rng.random() * (T_BALLS[1] - T_BALLS[0]), pop=c)

    # fairy lights on the branch tips (they twinkle)
    tips = np.array(tips)
    pick = rng.choice(len(tips), min(170, len(tips)), replace=False)
    bulb = fib_sphere(16)
    t_on = T_LIGHTS[0] + rng.random(len(pick)) * (T_LIGHTS[1] - T_LIGHTS[0])
    for c, t0 in zip(tips[pick], t_on):
        col = WARM if rng.random() < 0.8 else np.array([1.0, 0.95, 0.85])
        q.add(c + bulb * 0.03, bulb, col, "light", t0, phase=rng.random() * TAU)

    # gifts: (angle, distance, width, height, depth, rotation, box colour, ribbon colour)
    gifts = [(0.3, 1.05, 0.22, 0.18, 0.20, 0.4, RED, GOLD),
             (1.5, 1.10, 0.26, 0.13, 0.20, 1.0, GOLD, RED),
             (2.6, 0.95, 0.20, 0.24, 0.20, 0.5, RED, WHITE),
             (3.7, 1.10, 0.18, 0.22, 0.18, 0.2, BLUE_BOX, GOLD),
             (4.7, 1.05, 0.22, 0.16, 0.22, 0.1, GREEN_BOX, RED),
             (5.6, 1.12, 0.17, 0.15, 0.17, 0.7, RED, WHITE)]
    for g, (ang, dist, w, h, d, rot, body, rib) in enumerate(gifts):
        m = int(9000 * (w * d + 2 * h * (w + d)))
        areas = np.array([w * d, h * d, h * d, h * w, h * w])
        face = rng.choice(5, m, p=areas / areas.sum())
        fa, fb = rng.random(m) - 0.5, rng.random(m) - 0.5
        lx = np.select([face == 0, face == 1, face == 2], [fa * w, np.full(m, w / 2), np.full(m, -w / 2)], fa * w)
        ly = np.select([face == 0], [np.full(m, h)], (fb + 0.5) * h)
        lz = np.select([face == 0, face <= 2, face == 3], [fb * d, fa * d, np.full(m, d / 2)], np.full(m, -d / 2))
        nl = np.select([face[:, None] == 0, face[:, None] == 1, face[:, None] == 2, face[:, None] == 3],
                       [[0, 1, 0], [1, 0, 0], [-1, 0, 0], [0, 0, 1]], [0, 0, -1])
        ribbon = (np.abs(lx) < w * 0.09) | (np.abs(lz) < d * 0.09)
        cr, sr = math.cos(rot), math.sin(rot)
        rot_m = np.array([[cr, 0, -sr], [0, 1, 0], [sr, 0, cr]])
        centre = np.array([math.cos(ang) * dist * R_BASE, GROUND, math.sin(ang) * dist * R_BASE])
        p = np.stack([lx, ly, lz], 1) @ rot_m.T + centre
        nl = nl @ rot_m.T
        t0 = T_GIFTS[0] + g * (T_GIFTS[1] - T_GIFTS[0]) / len(gifts)
        q.add(p[~ribbon], nl[~ribbon], body, "gift", t0, pop=centre)
        q.add(p[ribbon], nl[ribbon], rib, "ribbon", t0, pop=centre)

    return q.done()


class Renderer:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode((W, H))
        self.font = pygame.font.SysFont(MONO, FONT_PX)
        self.hud = pygame.font.SysFont(MONO, 12)
        # glyph atlas: characters 32..126 pre-rendered as (CH, CW) brightness masks
        atlas = []
        for code in range(32, 127):
            s = pygame.Surface((CW, CH))
            g = self.font.render(chr(code), True, (255, 255, 255))
            s.blit(g, ((CW - g.get_width()) // 2, (CH - g.get_height()) // 2))
            atlas.append(pygame.surfarray.array3d(s)[:, :, 0].T)
        self.atlas = np.stack(atlas).astype(np.float32) / 255.0
        self.art = pygame.Surface((W, H))
        self.scene = build()
        rng = np.random.default_rng(3)
        self.bg = rng.random((ROWS, COLS)) < 0.06                 # faint background stars
        n = 240
        self.snow = np.stack([rng.random(n) * COLS, rng.random(n) * ROWS,
                              rng.uniform(2, 7, n), rng.random(n) * TAU], 1)
        self.ramps = [np.frombuffer(RAMPS[k].encode(), np.uint8) for k in KINDS]

    # ---------------------------------------------------------- frame
    def frame(self, t, dt):
        char = np.full((ROWS, COLS), 32, np.uint8)
        col = np.zeros((ROWS, COLS, 3), np.float32)
        info = {"rotation": math.degrees(t * SPIN), "lights": 0, "letters": 0}

        # background + falling snow
        char[self.bg] = ord(".")
        col[self.bg] = (0.16, 0.18, 0.24)
        s = self.snow
        s[:, 1] += s[:, 2] * dt
        s[:, 0] += 0.6 * np.sin(t + s[:, 3]) * dt
        wrap = s[:, 1] >= ROWS
        s[wrap, 1] -= ROWS
        s[:, 0] %= COLS
        r, c = s[:, 1].astype(int), s[:, 0].astype(int)
        char[r, c] = np.where(s[:, 2] > 5, ord("*"), np.where(s[:, 2] > 3.5, ord("+"), ord(".")))
        col[r, c] = (0.75, 0.80, 0.90)

        self.draw_tree(t, char, col, info)
        if t > T_STAR:
            self.draw_star(t, char, col)
        if t > T_MSG:
            self.draw_message(t, char, col, info)

        # compose the image: glyph mask * cell colour, all cells at once with numpy
        img = self.atlas[char.astype(int) - 32][..., None] * col[:, :, None, None, :]
        img = img.transpose(1, 3, 0, 2, 4).reshape(W, H, 3)
        pygame.surfarray.blit_array(self.art, np.clip(img * 255, 0, 255).astype(np.uint8))
        self.screen.blit(self.art, (0, 0))
        self.draw_hud(info)

    def project(self, p, t):
        """Rotate the scene around the Y axis and apply a perspective projection to pixels."""
        a = t * SPIN
        ca, sa = math.cos(a), math.sin(a)
        x = p[:, 0] * ca - p[:, 2] * sa
        z = p[:, 0] * sa + p[:, 2] * ca
        depth = CAM_D + z
        px = W / 2 + x / depth * SCALE
        py = H * 0.48 - (p[:, 1] - CAM_Y) / depth * SCALE
        return px, py, depth, (ca, sa)

    def draw_tree(self, t, char, col, info):
        S = self.scene
        vis = t >= S["t0"]
        if not vis.any():
            return
        p, nrm, k = S["p"][vis], S["n"][vis], S["k"][vis]
        age = t - S["t0"][vis]
        # "pop-in" objects (baubles, gifts) scale up from their centre with a small overshoot
        pop = S["pop"][vis]
        if pop.any():
            u = np.clip(age / 0.35, 0, 1)
            sc = (0.1 + 0.9 * u + 0.15 * np.sin(u * math.pi))[:, None]
            ctr = S["ctr"][vis]
            p = np.where(pop[:, None], ctr + (p - ctr) * sc, p)

        px, py, depth, (ca, sa) = self.project(p, t)
        cc, rr = (px // CW).astype(int), (py // CH).astype(int)
        ok = (cc >= 0) & (cc < COLS) & (rr >= 0) & (rr < ROWS)
        # bias lights slightly towards the camera so they win close depth ties
        depth = depth - 0.04 * (k == KINDS.index("light"))
        # z-buffer: sort by (cell, depth) and keep the nearest point in each cell
        idx = np.where(ok, rr * COLS + cc, -1)
        order = np.lexsort((depth, idx))
        idx_s = idx[order]
        first = np.r_[True, idx_s[1:] != idx_s[:-1]] & (idx_s >= 0)
        sel = order[first]

        # Lambert shading (normals rotated into camera space)
        n = nrm[sel]
        nx = n[:, 0] * ca - n[:, 2] * sa
        nz = n[:, 0] * sa + n[:, 2] * ca
        L = np.array([-0.45, 0.6, -0.65]); L /= np.linalg.norm(L)
        lam = np.clip(nx * L[0] + n[:, 1] * L[1] + nz * L[2], 0, 1)
        b = 0.40 + 0.60 * lam
        ks = k[sel]
        ph = S["ph"][vis][sel]
        is_light = ks == KINDS.index("light")
        is_gar = ks == KINDS.index("garland")
        b = np.where(is_light, 0.55 + 0.45 * np.sin(t * 3.1 + ph * 3) ** 2, b)
        b = np.where(is_gar, 0.55 + 0.45 * lam + 0.25 * np.sin(t * 4 + ph), b)
        b = np.clip(b * (1.25 - 0.12 * (depth[sel] - CAM_D)), 0, 1)

        colr = S["c"][vis][sel] * b[:, None]
        # the freshly grown edge flashes white like snow
        fresh = np.clip(1 - age[sel] / 0.35, 0, 1)[:, None]
        colr = colr * (1 - fresh) + WHITE * fresh
        colr = np.where(is_light[:, None], colr * 1.25, colr)

        # pick a character from the kind's ramp according to brightness
        chars = np.empty(len(sel), np.uint8)
        for ki, ramp in enumerate(self.ramps):
            m = ks == ki
            if m.any():
                chars[m] = ramp[np.minimum((b[m] * len(ramp)).astype(int), len(ramp) - 1)]
        chars = np.where(fresh[:, 0] > 0.3, ord("="), chars)

        cell = idx[sel]
        char.flat[cell] = chars
        col.reshape(-1, 3)[cell] = np.clip(colr, 0, 1)
        info["lights"] = int(len(np.unique(S["t0"][vis][S["k"][vis] == KINDS.index("light")])))

    def draw_star(self, t, char, col):
        # five-pointed star on top: bursts white with long rays, then settles to gold
        px, py, _, _ = self.project(np.array([[0, Y1 + 0.10, 0]]), t)
        cx, cy = px[0] / CW, py[0] / CH
        e = t - T_STAR
        flash = float(np.clip(1 - e / 1.0, 0, 1) ** 2)
        size = 4.5 * min(1, e / 0.4)
        reach = size * (1 + 2.2 * flash)
        rows, cols = np.mgrid[0:ROWS, 0:COLS]
        dx, dy = (cols + 0.5 - cx), (rows + 0.5 - cy) * CH / CW
        rad = np.hypot(dx, dy) / 1.6
        ang = np.arctan2(dy, dx) + math.pi / 2
        star = rad < size * (0.45 + 0.55 * np.cos(2.5 * ang) ** 8)
        rays = (rad < reach) & (np.abs(np.sin(4 * ang)) < 0.12) & (flash > 0)
        glow = 0.8 + 0.2 * math.sin(t * 5)
        base = GOLD * (1 - flash) + WHITE * flash
        char[rays] = ord("+")
        col[rays] = WHITE * flash
        char[star] = ord("*")
        col[star] = np.clip(base * glow * 1.2, 0, 1)
        char[star & (rad < size * 0.35)] = ord("@")

    def draw_message(self, t, char, col, info):
        # type the message out letter by letter, cycling red / gold / green
        text = " ".join(MESSAGE)
        shown = min(len(text), int((t - T_MSG) * 14))
        row, x0 = ROWS - 5, (COLS - len(text)) // 2
        for i, ch in enumerate(text[:shown]):
            if ch != " ":
                tint = (RED, GOLD, GREEN_BOX)[(i // 2 + int(t * 1.5)) % 3]
                char[row, x0 + i] = ord(ch)
                col[row, x0 + i] = tint * (0.85 + 0.15 * math.sin(t * 5 + i))
        info["letters"] = sum(c != " " for c in text[:shown])

    def draw_hud(self, info):
        lines = [f"{TITLE}  ·  rotation {info['rotation'] % 360:6.1f}°  ·  lights {info['lights']}"
                 f"  ·  letters {info['letters']}", HINT]
        for i, s in enumerate(lines):
            g = self.hud.render(s, True, tuple(DIM))
            self.screen.blit(g, (8, H - 30 + i * 14))


def main():
    R = Renderer()
    clock = pygame.time.Clock()
    t, paused, running = 0.0, False, True
    while running:
        dt = clock.tick(FPS) / 1000
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_SPACE:
                    paused = not paused
                elif e.key == pygame.K_r:
                    t = 0.0
                elif e.key == pygame.K_s:
                    name = f"tree_{int(time.time())}.png"
                    pygame.image.save(R.screen, name)
                    print("saved", name)
        if not paused:
            t += dt
            R.frame(t, dt)
            pygame.display.flip()
    pygame.quit()


if __name__ == "__main__":
    main()
