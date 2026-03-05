"""
glyph_anchors.py — PER-GLYPH ANCHOR POINT SYSTEM
==================================================
Each letter has named anchor points where decorations attach.
Coordinates are in the same space as font_skeletons.py (CAP=80, BASE=560, EM=700).

Anchor types:
  top_center    — apex of the letter (top of A, I, T)
  top_left      — top of left stem
  top_right     — top of right stem  
  base_left     — bottom of left stem (at baseline)
  base_right    — bottom of right stem
  base_center   — center of baseline
  bowl_top      — topmost point of circular bowl
  bowl_right    — rightmost point of bowl
  bowl_left     — leftmost point of bowl
  crossbar      — center of horizontal crossbar
  terminal_top  — top open end (C, G, J, S)
  terminal_bot  — bottom open end
  ascender      — top of ascender (b, d, f, h, k, l)
  descender     — bottom of descender (g, j, p, q, y)
"""

from font_skeletons import CAP, XH, BASE, DESC

# Standard advance width (can vary by letter but this is our default)
ADV = 520
CX  = ADV // 2
L   = 44
R   = ADV - 44

# ── ANCHOR DEFINITIONS ─────────────────────────────────
# Each entry: list of (anchor_type, x, y) tuples
# Multiple anchors of same type = decoration repeated

ANCHORS = {
    # ── UPPERCASE ──────────────────────────────────────
    'A': [
        ('top_center',  CX,      CAP),
        ('base_left',   L+30,    BASE),
        ('base_right',  R-30,    BASE),
        ('crossbar',    CX,      (CAP+BASE)//2),
    ],
    'B': [
        ('top_left',    L+26,    CAP),
        ('base_left',   L+26,    BASE),
        ('bowl_right',  R-10,    (CAP+BASE)//2 - 20),
        ('bowl_right',  R-10,    BASE - 60),
    ],
    'C': [
        ('terminal_top',  R-40,  CAP + 60),
        ('terminal_bot',  R-40,  BASE - 60),
        ('bowl_left',     L+10,  (CAP+BASE)//2),
    ],
    'D': [
        ('top_left',    L+26,    CAP),
        ('base_left',   L+26,    BASE),
        ('bowl_right',  R-10,    (CAP+BASE)//2),
    ],
    'E': [
        ('top_left',    L+26,    CAP),
        ('base_left',   L+26,    BASE),
        ('crossbar',    L+ADV//3+10, (CAP+BASE)//2),
    ],
    'F': [
        ('top_left',    L+26,    CAP),
        ('base_left',   L+26,    BASE),
        ('crossbar',    L+ADV//3+10, (CAP+BASE)//2),
    ],
    'G': [
        ('terminal_top',  R-40,  CAP + 60),
        ('bowl_left',     L+10,  (CAP+BASE)//2),
        ('base_right',    CX+20, BASE),
    ],
    'H': [
        ('top_left',    L+26,    CAP),
        ('top_right',   R-26,    CAP),
        ('base_left',   L+26,    BASE),
        ('base_right',  R-26,    BASE),
        ('crossbar',    CX,      (CAP+BASE)//2),
    ],
    'I': [
        ('top_center',  CX,      CAP),
        ('base_center', CX,      BASE),
    ],
    'J': [
        ('top_right',   R-26,    CAP),
        ('base_center', L+80,    BASE),
    ],
    'K': [
        ('top_left',    L+26,    CAP),
        ('top_right',   R-10,    CAP),
        ('base_left',   L+26,    BASE),
        ('base_right',  R-10,    BASE),
    ],
    'L': [
        ('top_left',    L+26,    CAP),
        ('base_right',  R-20,    BASE),
    ],
    'M': [
        ('top_left',    L+26,    CAP),
        ('top_right',   R-26,    CAP),
        ('base_left',   L+26,    BASE),
        ('base_right',  R-26,    BASE),
        ('top_center',  CX,      (CAP+BASE)//2+20),
    ],
    'N': [
        ('top_left',    L+26,    CAP),
        ('top_right',   R-26,    CAP),
        ('base_left',   L+26,    BASE),
        ('base_right',  R-26,    BASE),
    ],
    'O': [
        ('bowl_top',    CX,      CAP + 10),
        ('base_center', CX,      BASE - 10),
        ('bowl_right',  R-10,    (CAP+BASE)//2),
        ('bowl_left',   L+10,    (CAP+BASE)//2),
    ],
    'P': [
        ('top_left',    L+26,    CAP),
        ('base_left',   L+26,    BASE),
        ('bowl_right',  R-10,    (CAP+BASE)//2 - 30),
    ],
    'Q': [
        ('bowl_top',    CX,      CAP + 10),
        ('bowl_right',  R-10,    (CAP+BASE)//2),
        ('base_right',  R-10,    BASE + 40),
    ],
    'R': [
        ('top_left',    L+26,    CAP),
        ('base_left',   L+26,    BASE),
        ('base_right',  R-10,    BASE),
        ('bowl_right',  R-10,    (CAP+BASE)//2 - 30),
    ],
    'S': [
        ('terminal_top',  CX+40, CAP + 30),
        ('terminal_bot',  CX-40, BASE - 30),
    ],
    'T': [
        ('top_left',    L+10,    CAP),
        ('top_right',   R-10,    CAP),
        ('base_center', CX,      BASE),
    ],
    'U': [
        ('top_left',    L+26,    CAP),
        ('top_right',   R-26,    CAP),
        ('base_center', CX,      BASE),
    ],
    'V': [
        ('top_left',    L+10,    CAP),
        ('top_right',   R-10,    CAP),
        ('base_center', CX,      BASE),
    ],
    'W': [
        ('top_left',    L+10,    CAP),
        ('top_right',   R-10,    CAP),
        ('base_left',   L+ADV//4, BASE),
        ('base_right',  R-ADV//4, BASE),
        ('top_center',  CX,      (CAP+BASE)//2+20),
    ],
    'X': [
        ('top_left',    L+10,    CAP),
        ('top_right',   R-10,    CAP),
        ('base_left',   L+10,    BASE),
        ('base_right',  R-10,    BASE),
    ],
    'Y': [
        ('top_left',    L+10,    CAP),
        ('top_right',   R-10,    CAP),
        ('base_center', CX,      BASE),
    ],
    'Z': [
        ('top_left',    L+10,    CAP),
        ('top_right',   R-10,    CAP),
        ('base_left',   L+10,    BASE),
        ('base_right',  R-10,    BASE),
    ],

    # ── LOWERCASE ──────────────────────────────────────
    'a': [('top_center',  CX,     XH),   ('base_right', R-26, BASE)],
    'b': [('ascender',    L+26,   CAP),  ('base_left',  L+26, BASE), ('bowl_right', R-10, (XH+BASE)//2)],
    'c': [('terminal_top', R-30,  XH+40), ('terminal_bot', R-30, BASE-40)],
    'd': [('ascender',    R-26,   CAP),  ('base_right', R-26, BASE), ('bowl_left', L+10, (XH+BASE)//2)],
    'e': [('top_center',  CX,     XH),   ('terminal_top', R-20, (XH+BASE)//2+10)],
    'f': [('top_center',  CX,     CAP+30), ('base_center', CX, BASE), ('crossbar', CX, XH)],
    'g': [('top_center',  CX,     XH),   ('descender',  CX, DESC)],
    'h': [('ascender',    L+26,   CAP),  ('base_left',  L+26, BASE), ('base_right', R-26, BASE)],
    'i': [('top_center',  CX,     XH-60), ('base_center', CX, BASE)],
    'j': [('top_center',  CX+10,  XH-60), ('descender', CX-30, DESC)],
    'k': [('ascender',    L+26,   CAP),  ('base_left',  L+26, BASE), ('base_right', R-10, BASE)],
    'l': [('top_center',  CX,     CAP),  ('base_center', CX, BASE)],
    'm': [('top_left',    L+26,   XH),   ('base_left', L+26, BASE), ('base_right', R-26, BASE)],
    'n': [('top_left',    L+26,   XH),   ('base_left', L+26, BASE), ('base_right', R-26, BASE)],
    'o': [('bowl_top',    CX,     XH+10), ('base_center', CX, BASE-10)],
    'p': [('top_left',    L+26,   XH),   ('descender',  L+26, DESC), ('bowl_right', R-10, (XH+BASE)//2)],
    'q': [('top_right',   R-26,   XH),   ('descender',  R-26, DESC), ('bowl_left', L+10, (XH+BASE)//2)],
    'r': [('top_left',    L+26,   XH),   ('base_left',  L+26, BASE), ('terminal_top', R-30, XH+30)],
    's': [('terminal_top', CX+30,  XH+20), ('terminal_bot', CX-30, BASE-20)],
    't': [('top_center',  CX,     CAP+40), ('base_center', CX, BASE), ('crossbar', CX, XH)],
    'u': [('top_left',    L+26,   XH),   ('top_right',  R-26, XH), ('base_center', CX, BASE)],
    'v': [('top_left',    L+10,   XH),   ('top_right',  R-10, XH), ('base_center', CX, BASE)],
    'w': [('top_left',    L+10,   XH),   ('top_right',  R-10, XH), ('base_center', CX, BASE)],
    'x': [('top_left',    L+10,   XH),   ('top_right',  R-10, XH), ('base_left', L+10, BASE), ('base_right', R-10, BASE)],
    'y': [('top_left',    L+10,   XH),   ('top_right',  R-10, XH), ('descender',  CX-10, DESC)],
    'z': [('top_left',    L+10,   XH),   ('top_right',  R-10, XH), ('base_left', L+10, BASE), ('base_right', R-10, BASE)],

    # ── DIGITS ─────────────────────────────────────────
    '0': [('bowl_top', CX, CAP+10), ('base_center', CX, BASE-10)],
    '1': [('top_center', CX, CAP), ('base_center', CX, BASE)],
    '2': [('top_right', R-20, CAP+40), ('base_left', L+10, BASE), ('base_right', R-10, BASE)],
    '3': [('top_right', R-20, CAP+40), ('base_right', R-20, BASE-40)],
    '4': [('top_left', L+10, CAP), ('crossbar', CX, (CAP+BASE)*55//100), ('base_right', R-20, BASE)],
    '5': [('top_left', L+10, CAP), ('top_right', R-10, CAP), ('base_right', R-20, BASE-40)],
    '6': [('top_right', R-30, CAP+50), ('bowl_right', R-10, (XH+BASE)//2)],
    '7': [('top_left', L+10, CAP), ('top_right', R-10, CAP), ('base_left', L+20, BASE)],
    '8': [('bowl_top', CX, CAP+10), ('crossbar', CX, (CAP+BASE)//2), ('base_center', CX, BASE-10)],
    '9': [('bowl_top', CX, CAP+10), ('base_right', R-26, BASE)],
}


def get_anchors(char: str) -> list:
    """
    Get all anchor points for a character.
    Returns: list of (anchor_type, x, y) tuples
    """
    return ANCHORS.get(char, [('top_center', CX, CAP), ('base_center', CX, BASE)])


def get_anchors_by_type(char: str, anchor_type: str) -> list:
    """
    Get anchors of a specific type for a character.
    Returns: list of (x, y) tuples
    """
    return [(x, y) for atype, x, y in get_anchors(char) if atype == anchor_type]


def get_anchor_types(char: str) -> set:
    """Get all available anchor types for a character."""
    return {atype for atype, x, y in get_anchors(char)}
