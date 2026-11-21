#!/usr/bin/env python3
"""The Passport Page of a Country That Isn't There.

Generates /output/entry.png (or $MAKEFUN_OUTPUT_DIR/entry.png): an open
passport spread for the Republic of Meridia -- an island republic that only
exists at low tide. Fully procedural, pure stdlib (no PIL, no network, no
outside files), deterministic: two runs produce byte-identical PNGs.

Layout (1024x720, landscape spread):
  left page  - data page: emblem, portrait silhouette, holder's details,
               machine-readable zone (ICAO 9303 check digits computed).
  right page - visas: three stamps from the neighbouring Kingdom of the
               Tides, all dated after the passport's issue (14 MAR 2024)
               and before its expiry (14 MAR 2034), plus the conditions
               box ("VALID ONLY AT LOW TIDE") and a fee stamp in shells.
"""

import hashlib
import math
import os
import struct
import zlib

W, H = 1024, 720

# ---- palette (one restrained document palette: cream paper, navy ink,
#      sea teal accent, rust-red and violet stamp inks) ----
PAPER = (244, 239, 228)
PAPER_DK = (232, 225, 208)
INK = (27, 58, 92)
INK_SOFT = (58, 88, 120)
TEAL = (23, 110, 108)
TEAL_LT = (214, 232, 228)
RUST = (168, 62, 44)
VIOLET = (96, 74, 138)
GUILLOCHE = (214, 206, 188)
PHOTO_BG = (196, 208, 216)
SILHOUETTE = (52, 74, 96)
GOLD = (176, 138, 62)

OUT = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")


# ---------------------------------------------------------------- PNG ----
def png_bytes(rgb, w, h):
    """Encode an RGB bytearray as a PNG (filter 0 per row, zlib level 9)."""
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", comp) + chunk(b"IEND", b""))


# ------------------------------------------------------------- canvas ----
class Canvas:
    def __init__(self, w, h, bg):
        self.w, self.h = w, h
        self.px = bytearray(w * h * 3)
        self.fill_rect(0, 0, w, h, bg)

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i], self.px[i + 1], self.px[i + 2] = c

    def fill_rect(self, x, y, w, h, c):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        for yy in range(y0, y1):
            base = (yy * self.w + x0) * 3
            for xx in range(x0, x1):
                i = base + (xx - x0) * 3
                self.px[i], self.px[i + 1], self.px[i + 2] = c

    def hline(self, x0, x1, y, c, t=1):
        for t_ in range(t):
            for x in range(min(x0, x1), max(x0, x1) + 1):
                self.set(x, y + t_, c)

    def vline(self, x, y0, y1, c, t=1):
        for t_ in range(t):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                self.set(x + t_, y, c)

    def line(self, x0, y0, x1, y1, c, t=1):
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        x, y = x0, y0
        while True:
            for a in range(t):
                for b in range(t):
                    self.set(x + a, y + b, c)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

    def rect(self, x, y, w, h, c, t=1):
        self.hline(x, x + w - 1, y, c, t)
        self.hline(x, x + w - 1, y + h - 1, c, t)
        self.vline(x, y, y + h - 1, c, t)
        self.vline(x + w - 1, y, y + h - 1, c, t)

    def circle(self, cx, cy, r, c, t=1, fill=False):
        if fill:
            for yy in range(cy - r, cy + r + 1):
                dx = int(math.sqrt(max(0, r * r - (yy - cy) ** 2)))
                self.hline(cx - dx, cx + dx, yy, c)
            return
        x, y, d = 0, r, 3 - 2 * r
        while x <= y:
            for px, py in ((cx + x, cy + y), (cx - x, cy + y),
                           (cx + x, cy - y), (cx - x, cy - y),
                           (cx + y, cy + x), (cx - y, cy + x),
                           (cx + y, cy - x), (cx - y, cy - x)):
                for a in range(t):
                    self.set(px + a, py, c)
            if d < 0:
                d += 4 * x + 6
            else:
                d += 4 * (x - y) + 10
                y -= 1
            x += 1

    def ellipse(self, cx, cy, rx, ry, c, fill=False):
        if fill:
            for yy in range(cy - ry, cy + ry + 1):
                t = (yy - cy) / ry
                dx = int(rx * math.sqrt(max(0.0, 1 - t * t)))
                self.hline(cx - dx, cx + dx, yy, c)
            return
        for deg in range(0, 360):
            a = math.radians(deg)
            self.set(int(cx + rx * math.cos(a)), int(cy + ry * math.sin(a)), c)

    def poly_fill(self, pts, c):
        """Scanline fill of a simple polygon (list of (x, y))."""
        ys = [p[1] for p in pts]
        for y in range(min(ys), max(ys) + 1):
            xs = []
            n = len(pts)
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                if (y0 <= y < y1) or (y1 <= y < y0):
                    xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.hline(int(xs[i]), int(xs[i + 1]), y, c)

    def arc(self, cx, cy, r, a0, a1, c, t=1):
        a = a0
        while a <= a1:
            rad = math.radians(a)
            for k in range(t):
                self.set(int(cx + (r + k) * math.cos(rad)),
                         int(cy + (r + k) * math.sin(rad)), c)
            a += 0.5


# -------------------------------------------------------------- font -----
# 5x7 bitmap font, uppercase + digits + document punctuation. Each glyph is
# 7 rows of 5 characters; '#' is ink, '.' is blank.
FONT = {}
def _g(ch, rows):
    FONT[ch] = rows

_g("A", [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"])
_g("B", ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."])
_g("C", [".####", "#....", "#....", "#....", "#....", "#....", ".####"])
_g("D", ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."])
_g("E", ["#####", "#....", "#....", "####.", "#....", "#....", "#####"])
_g("F", ["#####", "#....", "#....", "####.", "#....", "#....", "#...."])
_g("G", [".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."])
_g("H", ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"])
_g("I", [".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."])
_g("J", ["..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."])
_g("K", ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"])
_g("L", ["#....", "#....", "#....", "#....", "#....", "#....", "#####"])
_g("M", ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"])
_g("N", ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"])
_g("O", [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."])
_g("P", ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."])
_g("Q", [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"])
_g("R", ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"])
_g("S", [".####", "#....", "#....", ".###.", "....#", "....#", "####."])
_g("T", ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."])
_g("U", ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."])
_g("V", ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."])
_g("W", ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"])
_g("X", ["#...#", ".#.#.", "..#..", "..#..", "..#..", ".#.#.", "#...#"])
_g("Y", ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."])
_g("Z", ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"])
_g("0", [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."])
_g("1", ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."])
_g("2", [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"])
_g("3", ["####.", "....#", "....#", ".###.", "....#", "....#", "####."])
_g("4", ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."])
_g("5", ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."])
_g("6", [".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."])
_g("7", ["#####", "....#", "...#.", "...#.", "..#..", "..#..", "..#.."])
_g("8", [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."])
_g("9", [".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."])
_g(" ", [".....", ".....", ".....", ".....", ".....", ".....", "....."])
_g(".", [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."])
_g(",", [".....", ".....", ".....", ".....", ".##..", ".##..", ".#..."])
_g("-", [".....", ".....", ".....", "#####", ".....", ".....", "....."])
_g(":", [".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."])
_g("(", ["...#.", "..#..", ".#...", ".#...", ".#...", "..#..", "...#."])
_g(")", [".#...", "..#..", "...#.", "...#.", "...#.", "..#..", ".#..."])
_g("/", ["....#", "...#.", "...#.", "..#..", ".#...", ".#...", "#...."])
_g("<", ["...#.", "..#..", ".#...", "#....", ".#...", "..#..", "...#."])
_g(">", [".#...", "..#..", "...#.", "....#", "...#.", "..#..", ".#..."])
_g("'", ["..#..", "..#..", ".#...", ".....", ".....", ".....", "....."])
_g("&", [".##..", "#..#.", "#..#.", ".#...", "#.#.#", "#..#.", ".##.#"])
_g("+", [".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."])
_g("*", [".....", ".#.#.", "..#..", "#####", "..#..", ".#.#.", "....."])
_g("!", ["..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."])
_g("=", [".....", ".....", "#####", ".....", "#####", ".....", "....."])

def text_w(s, scale, gap=1):
    return len(s) * (5 + gap) * scale - gap * scale

def draw_text(cv, x, y, s, scale, color, angle=0.0, gap=1):
    """Draw text; (x, y) is the anchor of the first glyph's top-left corner.
    angle rotates the whole string around the anchor (degrees). gap is the
    inter-glyph spacing in glyph pixels (0 = glyphs touch, for the MRZ)."""
    rad = math.radians(angle)
    ca, sa = math.cos(rad), math.sin(rad)
    cx0, cy0 = x, y
    for ch in s:
        glyph = FONT.get(ch, FONT[" "])
        for gy in range(7):
            row = glyph[gy]
            for gx in range(5):
                if row[gx] != "#":
                    continue
                # local pixel block, scaled
                for dy in range(scale):
                    for dx in range(scale):
                        px = (x - cx0) + gx * scale + dx
                        py = gy * scale + dy
                        rx = cx0 + px * ca - py * sa
                        ry = cy0 + px * sa + py * ca
                        cv.set(int(round(rx)), int(round(ry)), color)
        x += (5 + gap) * scale  # advance in unrotated space
    return x


# ------------------------------------------------------------ MRZ -------
def mrz_check(s):
    """ICAO 9303 check digit: values 0-9, A=10..Z=35, '<'=0; weights 7,3,1."""
    total = 0
    for i, ch in enumerate(s):
        if ch == "<":
            v = 0
        elif ch.isdigit():
            v = int(ch)
        else:
            v = ord(ch) - 55  # A=10
        total += v * (7, 3, 1)[i % 3]
    return str(total % 10)


def mrz_lines():
    doc = "MER123456"
    doc_c = mrz_check(doc)
    nat = "MER"
    dob, dob_c = "980602", mrz_check("980602")
    sex = "F"
    exp, exp_c = "340314", mrz_check("340314")
    pers = "<<<<<<<<<<<<<<"
    pers_c = mrz_check(pers)
    composite = mrz_check(doc + doc_c + nat + dob + dob_c + sex + exp + exp_c
                          + pers + pers_c)
    line1 = "P<MERSELKIE<<MARA" + "<" * 27
    line2 = (doc + doc_c + nat + dob + dob_c + sex + exp + exp_c
             + pers + pers_c + composite)
    assert len(line1) == 44 and len(line2) == 44, (len(line1), len(line2))
    return line1, line2


# ---------------------------------------------------------- emblem -----
def draw_emblem(cv, cx, cy, r, ink):
    """Meridia's arms: a rising sun over three waves, one star above."""
    cv.circle(cx, cy, r, ink, t=2)
    cv.circle(cx, cy, r - 5, ink, t=1)
    # sun
    sx, sy, sr = cx, cy - r // 3, r // 4
    cv.circle(sx, sy, sr, ink, fill=True)
    for a in range(0, 360, 30):
        rad = math.radians(a)
        cv.line(int(sx + (sr + 2) * math.cos(rad)),
                int(sy + (sr + 2) * math.sin(rad)),
                int(sx + (sr + 7) * math.cos(rad)),
                int(sy + (sr + 7) * math.sin(rad)), ink, t=1)
    # three waves
    for k in range(3):
        wy = cy + r // 6 + k * (r // 5)
        for x in range(cx - r + 8, cx + r - 8):
            t = (x - (cx - r)) / (2 * r)
            yy = wy + int(4 * math.sin(t * math.pi * 2 + k * 1.1))
            cv.set(x, yy, ink)
            cv.set(x, yy + 1, ink)
    # star above the sun
    star_cx, star_cy, sr2 = cx, cy - r + 10, 7
    pts = []
    for i in range(10):
        ang = math.radians(-90 + i * 36)
        rr = sr2 if i % 2 == 0 else sr2 // 2
        pts.append((int(star_cx + rr * math.cos(ang)),
                    int(star_cy + rr * math.sin(ang))))
    cv.poly_fill(pts, ink)


# --------------------------------------------------------- portrait ----
def draw_portrait(cv, x, y, w, h):
    """Holder's photograph: a head-and-shoulders silhouette of Mara Selkie,
    fisherwoman of Port Lowtide, against a hatched photo ground."""
    cv.fill_rect(x, y, w, h, PHOTO_BG)
    # diagonal hatch, clipped to the photo box (slope -1 lines)
    for d in range(-h, w, 10):
        x_start = max(x, x + d)
        x_end = min(x + w - 1, x + d + h)
        for px in range(x_start, x_end + 1):
            py = y + h - (px - (x + d))
            if y <= py < y + h:
                cv.set(px, py, (178, 192, 202))
    cx, cy = x + w // 2, y + h // 2 - 18
    # shoulders / coat
    cv.poly_fill([(cx - 52, y + h), (cx - 46, cy + 42), (cx - 20, cy + 30),
                  (cx + 20, cy + 30), (cx + 46, cy + 42), (cx + 52, y + h)],
                 SILHOUETTE)
    # neck + head
    cv.fill_rect(cx - 9, cy + 14, 18, 20, SILHOUETTE)
    cv.ellipse(cx, cy, 24, 30, SILHOUETTE, fill=True)
    # hair: swept back, tied low (a fisherwoman's bun)
    cv.ellipse(cx, cy - 8, 26, 22, SILHOUETTE, fill=True)
    cv.circle(cx + 2, cy + 34, 7, SILHOUETTE, fill=True)
    # a single earring, the only jewellery in the picture
    cv.set(cx + 24, cy + 6, GOLD)
    cv.set(cx + 25, cy + 6, GOLD)
    cv.set(cx + 24, cy + 7, GOLD)
    cv.set(cx + 25, cy + 7, GOLD)
    cv.rect(x, y, w, h, INK, t=2)


# ----------------------------------------------------------- stamps ----
def draw_stamp(cv, cx, cy, w, h, angle, color, lines, scale=2):
    """A border-control stamp: double-rule rounded frame, inner ring,
    centred lines of text, all tilted like a hand stamp."""
    rad = math.radians(angle)
    ca, sa = math.cos(rad), math.sin(rad)

    def rot(px, py):
        return (int(round(cx + px * ca - py * sa)),
                int(round(cy + px * sa + py * ca)))

    def rline(p0, p1, t=1):
        a, b = rot(*p0), rot(*p1)
        cv.line(a[0], a[1], b[0], b[1], color, t=t)

    hw, hh = w // 2, h // 2
    for inset in (0, 5):
        rline((-hw + inset, -hh + inset), (hw - inset, -hh + inset), t=2)
        rline((hw - inset, -hh + inset), (hw - inset, hh - inset), t=2)
        rline((hw - inset, hh - inset), (-hw + inset, hh - inset), t=2)
        rline((-hw + inset, hh - inset), (-hw + inset, -hh + inset), t=2)
    # centred text lines (local frame; rotation applied about the centre)
    n = len(lines)
    for i, (txt, sc) in enumerate(lines):
        tw = text_w(txt, sc)
        lx = -tw // 2
        ly = -((n - 1) * 11) + i * 22 - 4 * sc
        draw_text_rot(cv, lx, ly, txt, sc, color, angle, cx, cy)


def draw_text_rot(cv, ax, ay, s, scale, color, angle, rcx, rcy):
    """Draw text rotated `angle` degrees about (rcx, rcy); (ax, ay) is the
    string's top-left anchor in the stamp's unrotated local frame."""
    rad = math.radians(angle)
    ca, sa = math.cos(rad), math.sin(rad)
    off = 0
    for ch in s:
        glyph = FONT.get(ch, FONT[" "])
        for gy in range(7):
            row = glyph[gy]
            for gx in range(5):
                if row[gx] != "#":
                    continue
                for dy in range(scale):
                    for dx in range(scale):
                        px_l = ax + off + gx * scale + dx
                        py_l = ay + gy * scale + dy
                        rx = rcx + px_l * ca - py_l * sa
                        ry = rcy + px_l * sa + py_l * ca
                        cv.set(int(round(rx)), int(round(ry)), color)
        off += 6 * scale
    return off


# ------------------------------------------------------- guilloche -----
def guilloche(cv, x0, y0, x1, y1):
    for k in range(0, (y1 - y0), 14):
        yb = y0 + k
        for x in range(x0, x1):
            yy = yb + int(3 * math.sin((x - x0) * 0.045 + k * 0.7))
            cv.set(x, yy, GUILLOCHE)


# ------------------------------------------------------------ layout ---
def field(cv, x, y, label, value, scale=2, label_color=INK_SOFT, max_x=488):
    draw_text(cv, x, y, label, 1, label_color)
    sc = scale
    while sc > 1 and x + text_w(value, sc) > max_x:
        sc -= 1
    draw_text(cv, x, y + 11, value, sc, INK)
    return y + 11 + 7 * sc + 12


def build():
    cv = Canvas(W, H, PAPER)
    guilloche(cv, 16, 16, 1008, 704)

    # outer frame + spine
    cv.rect(10, 10, W - 20, H - 20, INK, t=2)
    cv.rect(16, 16, W - 32, H - 32, INK, t=1)
    cv.vline(512, 16, 703, INK, t=2)
    cv.vline(514, 16, 703, (200, 190, 168), t=1)

    # ================= LEFT PAGE: data page =================
    draw_emblem(cv, 78, 78, 44, TEAL)
    draw_text(cv, 130, 44, "REPUBLIC OF MERIDIA", 3, INK)
    draw_text(cv, 130, 78, "PASSPORT  *  PASSEPORT", 2, INK_SOFT)
    draw_text(cv, 130, 96, "THE SEA GIVES, THE SEA TAKES", 1, TEAL)
    cv.hline(40, 488, 124, INK, t=1)

    # portrait
    draw_portrait(cv, 40, 142, 150, 190)
    draw_text(cv, 40, 338, "PHOTOGRAPH", 1, INK_SOFT)
    draw_text(cv, 40, 350, "HOLDER", 1, INK_SOFT)

    # personal data, right of the portrait
    fx, fy = 214, 140
    fy = field(cv, fx, fy, "SURNAME / NOM", "SELKIE")
    fy = field(cv, fx, fy, "GIVEN NAMES / PRENOMS", "MARA")
    fy = field(cv, fx, fy, "NATIONALITY / NATIONALITE", "MERIDIAN")
    fy = field(cv, fx, fy, "DATE OF BIRTH / DATE DE NAISSANCE", "02 JUN 1998")
    fy = field(cv, fx, fy, "PLACE OF BIRTH / LIEU DE NAISSANCE", "PORT LOWTIDE")
    fy = field(cv, fx, fy, "SEX / SEXE", "F")
    fy = field(cv, fx, fy, "DATE OF ISSUE / DATE DE DELIVRANCE", "14 MAR 2024")
    fy = field(cv, fx, fy, "DATE OF EXPIRY / DATE D'EXPIRATION", "14 MAR 2034")
    fy = field(cv, fx, fy, "AUTHORITY / AUTORITE", "TIDE OFFICE - LOWTIDE")
    fy = field(cv, fx, fy, "PASSPORT NO.", "MER123456")

    # small tide note under the photo, tying portrait to place
    draw_text(cv, 40, 392, "HOLDER IS A FISHERWOMAN", 1, INK_SOFT)
    draw_text(cv, 40, 404, "OF THE LOW-TIDE FLEET.", 1, INK_SOFT)
    draw_text(cv, 40, 416, "HOME HARBOUR: PORT LOWTIDE.", 1, INK_SOFT)

    # machine-readable zone (ICAO 9303, check digits computed above).
    # Gap 0 keeps the 44-character lines inside the data page:
    # 44 glyphs * 5 px * scale 2 = 440 px, from x=40 to x=480.
    cv.hline(40, 488, 540, INK, t=1)
    l1, l2 = mrz_lines()
    draw_text(cv, 40, 556, l1, 2, INK, gap=0)
    draw_text(cv, 40, 586, l2, 2, INK, gap=0)

    # holder's signature: a quick procedural squiggle, as signed in ink
    sig_x, sig_y = 40, 648
    for px in range(sig_x, sig_x + 150):
        t = (px - sig_x) / 150.0
        py = sig_y + int(5 * math.sin(t * math.pi * 7.3)
                         + 3 * math.sin(t * math.pi * 3.1))
        cv.set(px, py, INK)
        cv.set(px, py + 1, INK)
    cv.hline(sig_x, sig_x + 150, sig_y + 12, INK, t=1)
    draw_text(cv, 40, 668, "SIGNATURE OF HOLDER", 1, INK_SOFT)
    draw_text(cv, 300, 668, "MERIDIA - ISSUED AT LOW TIDE", 1, INK_SOFT)

    # ================= RIGHT PAGE: visas =================
    draw_text(cv, 544, 40, "VISAS", 4, INK)
    draw_text(cv, 544, 74, "ARRIVALS AND DEPARTURES", 2, INK_SOFT)
    cv.hline(544, 984, 104, INK, t=1)

    # Stamp 1: arrived in the neighbouring Kingdom of the Tides
    draw_stamp(cv, 764, 190, 330, 120, -7, TEAL,
               [("ARRIVED", 2), ("SEAHOLM", 3), ("22 MAY 2026", 2)])
    # Stamp 2: departed Seaholm twelve days later
    draw_stamp(cv, 764, 330, 330, 110, 6, RUST,
               [("DEPARTED", 2), ("SEAHOLM", 3), ("03 JUN 2026", 2)])
    # Stamp 3: home again at low tide
    draw_stamp(cv, 764, 462, 330, 110, -5, VIOLET,
               [("ARRIVED", 2), ("PORT LOWTIDE", 2), ("04 JUN 2026", 2)])

    # conditions box: the telling detail of paperwork
    cv.rect(544, 540, 440, 96, INK, t=2)
    draw_text(cv, 560, 552, "CONDITIONS OF ISSUE", 2, RUST)
    draw_text(cv, 560, 578, "THIS PASSPORT IS VALID ONLY AT LOW TIDE.", 1, INK)
    draw_text(cv, 560, 592, "AT HIGH TIDE THE BEARER IS A CITIZEN", 1, INK)
    draw_text(cv, 560, 606, "OF THE SEA, AND NEEDS NO PAPERS.", 1, INK)

    # fee stamp + next tide
    draw_text(cv, 544, 656, "FEE PAID: 12 SHELLS", 2, TEAL)
    draw_text(cv, 544, 680, "NEXT LOW TIDE: 21 NOV 2026 06:42", 1, INK_SOFT)
    draw_text(cv, 830, 680, "NO. MER123456", 1, INK_SOFT)
    return cv


def main():
    cv = build()
    os.makedirs(OUT, exist_ok=True)
    data = png_bytes(cv.px, W, H)
    path = os.path.join(OUT, "entry.png")
    with open(path, "wb") as f:
        f.write(data)
    print("wrote", path, len(data), "bytes",
          "sha256", hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
