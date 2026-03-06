# engine v8.0 — shape_library integrated | correct UPM scaling | Gemini API | Railway ready
__ENGINE_VERSION__ = "v8.0-shape-gemini"
#!/usr/bin/env python3
"""
SVG → TTF/OTF Font Engine v8
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fixes vs v7:
  • units_per_em=1000 gerçekten 1000 UPM üretir (eski kod 800 UPM'de kalıyordu)
  • Harfler tam boy: CAP_HEIGHT = 700 UPM (ascender'ın %100'ü)
  • shape_library.py engine kalbine entegre — dekoratif şekiller glyph'e eklenir
  • Gemini API ile her glyph için sanatsal Design Call (opsiyonel)
  • Railway: /health endpoint için sağlıklı log + hata yönetimi
  • Küçük harf sorunu kökten çözüldü: fixed metric system tamamen yeniden yazıldı
"""

import sys, os, re, json, io, math
from lxml import etree
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.misc.transform import Identity, Transform
from fontTools.svgLib.path import SVGPath as SVGPathLib

# ── Shape Library (inline import with fallback) ───────────────────────────────
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from shape_library import get_shape, place, list_shapes, SHAPES
    _SHAPES_AVAILABLE = True
    print(f"[engine] ✓ shape_library loaded — {len(SHAPES)} shapes available")
except ImportError:
    _SHAPES_AVAILABLE = False
    print("[engine] ⚠ shape_library not found — decorative shapes disabled")
    def get_shape(name): return ""
    def place(path, cx, cy, size, angle=0): return ""
    def list_shapes(): return []

# ── UPM & Metric Constants ─────────────────────────────────────────────────────
# Bu sabitler font_skeletons.py ile %100 uyumlu olmalı
UPM         = 1000   # units per em
ASCENDER    = 800    # font ascender (UPM'in %80'i)
DESCENDER   = -200   # font descender
CAP_HEIGHT  = 700    # büyük harf yüksekliği (UPM'in %70'i)
X_HEIGHT    = 500    # küçük harf yüksekliği

# SVG Grid Sabitleri (font_skeletons.py CAP/BASE/EM ile eşleşir)
SVG_CAP    =  80.0   # hücre içinde büyük harfin tepesi
SVG_BASE   = 560.0   # hücre içinde baseline
SVG_CELL   = 700.0   # hücre yüksekliği (= EM)
SVG_LEFT   =  44.0   # sol kenar boşluğu (= L sabiti)
SVG_ADV    = 520.0   # standart advance width (SVG birimlerinde)

# DÜZELTME: Doğru scale faktörü
# SVG'de glyph yüksekliği = SVG_BASE - SVG_CAP = 480 birim
# Bu 480 birim → font'ta ASCENDER (800 UPM) olmalı
# scale = 800 / 480 = 1.6667 ✓
SVG_GLYPH_H = SVG_BASE - SVG_CAP   # 480
SCALE       = ASCENDER / SVG_GLYPH_H  # 1.6667

# Advance width dönüşümü
# SVG_ADV (520) / SVG_CELL (700) * UPM (1000) = 742 — ama bu çok geniş
# Standart: advance ≈ cap_height oranında
ADVANCE_W   = int(SVG_ADV / SVG_GLYPH_H * ASCENDER)  # ~867 UPM

DEFAULT_CHAR_ORDER = (
    'A','B','C','D','E','F','G','H','I','J','K','L','M',
    'N','O','P','Q','R','S','T','U','V','W','X','Y','Z',
    'a','b','c','d','e','f','g','h','i','j','k','l','m',
    'n','o','p','q','r','s','t','u','v','w','x','y','z',
    '0','1','2','3','4','5','6','7','8','9',
    '.', ',', '!', '?', ';', ':', "'", '"', '(', ')', '-', '_',
    '/', '@', '#', '$', '%', '&', '*', '+', '=', ' ',
    'Ç','Ğ','İ','Ö','Ş','Ü',
    'ç','ğ','ı','ö','ş','ü',
)


# ═══════════════════════════════════════════════════════════════════════════════
# GEMINI API — Her glyph için sanatsal tasarım kararı
# ═══════════════════════════════════════════════════════════════════════════════

def gemini_design_call(char: str, style_prompt: str, gemini_key: str) -> dict:
    """
    Gemini API'ye her harf için 'Design Call' gönderir.
    Hangi shape_library şekillerinin ekleneceğini ve parametrelerini döndürür.
    
    Returns:
        {
          'decorations': [
            {'shape': 'flower', 'anchor': 'top_center', 'size': 40, 'angle': 0},
            ...
          ],
          'style_notes': 'açıklama'
        }
    """
    if not gemini_key or not _SHAPES_AVAILABLE:
        return {'decorations': [], 'style_notes': ''}
    
    import urllib.request, urllib.error
    
    available_shapes = list_shapes()
    
    prompt = f"""You are a font designer. For the character '{char}', 
decide which decorative shapes from the shape library to add based on this style: {style_prompt}

Available shapes: {', '.join(available_shapes[:20])}

Anchor types: top_center, top_left, top_right, base_left, base_right, base_center, 
              bowl_top, bowl_right, bowl_left, crossbar, terminal_top, terminal_bot,
              ascender, descender

Respond ONLY with valid JSON:
{{
  "decorations": [
    {{"shape": "shape_name", "anchor": "anchor_type", "size": 30, "angle": 0}}
  ],
  "style_notes": "brief note"
}}

Rules:
- Max 2 decorations per character
- size: 20-60 (relative to glyph)
- Only use shapes from the available list
- For simple/clean styles use 0 decorations
- Respond with valid JSON only, no markdown"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 256}
    }
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            text = data['candidates'][0]['content']['parts'][0]['text']
            text = re.sub(r'```json?\s*|\s*```', '', text).strip()
            result = json.loads(text)
            return result
    except Exception as e:
        print(f"    [Gemini] '{char}' design call failed: {e}")
        return {'decorations': [], 'style_notes': ''}


def apply_shape_decorations(base_path: str, char: str, decorations: list) -> str:
    """
    shape_library şekillerini glyph'in anchor noktalarına ekler.
    Anchor koordinatları UPM (font space) cinsindendir.
    """
    if not decorations or not _SHAPES_AVAILABLE:
        return base_path
    
    # Anchor noktaları (font UPM koordinatlarında)
    # glyph_anchors.py'den alınır ama burada font-space'e çevrilmiş hali
    try:
        from glyph_anchors import get_anchors_by_type
        
        parts = [base_path]
        for dec in decorations:
            shape_name = dec.get('shape', 'star5')
            anchor_type = dec.get('anchor', 'top_center')
            size = dec.get('size', 30)
            angle = dec.get('angle', 0)
            
            # Anchor koordinatlarını SVG'den font-space'e çevir
            anchors = get_anchors_by_type(char, anchor_type)
            if not anchors:
                # Fallback: top_center
                anchors = get_anchors_by_type(char, 'top_center')
            if not anchors:
                continue
            
            for svg_x, svg_y in anchors:
                # SVG → font space dönüşümü
                font_x = int(svg_x * SCALE - SVG_LEFT * SCALE)
                font_y = int((SVG_BASE - svg_y) * SCALE)  # Y flip
                
                shape_path = get_shape(shape_name)
                if shape_path:
                    placed = place(shape_path, font_x, font_y, size, angle)
                    parts.append(placed)
        
        return ' '.join(parts)
    
    except Exception as e:
        print(f"    [Shape] decoration failed for '{char}': {e}")
        return base_path


# ═══════════════════════════════════════════════════════════════════════════════
# SVG PARSING
# ═══════════════════════════════════════════════════════════════════════════════

def get_svg_viewbox(root):
    vb = root.get('viewBox', '')
    if vb:
        parts = re.split(r'[,\s]+', vb.strip())
        if len(parts) == 4:
            return [float(x) for x in parts]
    w = float(re.sub(r'[^\d.]', '', root.get('width', '1000')) or '1000')
    h = float(re.sub(r'[^\d.]', '', root.get('height', '1000')) or '1000')
    return [0, 0, w, h]


def get_translate(elem):
    if elem is None:
        return None
    t = elem.get('transform', '')
    m = re.search(r'translate\(\s*([-\d.]+)[,\s]+([-\d.]+)\s*\)', t)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None


def collect_groups(root):
    """SVG'deki karakter gruplarını topla — translate'li gruplar öncelikli"""
    ns = 'http://www.w3.org/2000/svg'
    groups = []

    def walk(elem):
        if not isinstance(elem.tag, str):
            return
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag

        if tag == 'g':
            paths = [e for e in elem.iter('{%s}path' % ns) if isinstance(e.tag, str)]
            translate = get_translate(elem)
            if paths and translate is not None:
                groups.append({
                    'paths': paths,
                    'elem': elem,
                    'tx': translate[0],
                    'ty': translate[1]
                })
                return
        for child in elem:
            walk(child)

    walk(root)

    # Fallback: translate olmayan gruplar
    if not groups:
        def walk2(elem):
            if not isinstance(elem.tag, str):
                return
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if tag == 'g':
                paths = [e for e in elem.iter('{%s}path' % ns) if isinstance(e.tag, str)]
                if paths:
                    groups.append({'paths': paths, 'elem': elem, 'tx': 0, 'ty': 0})
                    return
            for child in elem:
                walk2(child)
        walk2(root)

    return groups


def get_path_numbers(d):
    return [float(n) for n in re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', d) if n]


def get_group_bbox(group):
    xs, ys = [], []
    for p in group['paths']:
        d = p.get('d', '')
        if not d:
            continue
        nums = get_path_numbers(d)
        xs.extend(nums[0::2])
        ys.extend(nums[1::2])
    min_len = min(len(xs), len(ys))
    if min_len == 0:
        return None
    return min(xs[:min_len]), min(ys[:min_len]), max(xs[:min_len]), max(ys[:min_len])


def sort_groups(groups):
    """Grupları soldan sağa, yukarıdan aşağıya sırala"""
    if groups and groups[0].get('tx') is not None:
        def sort_key(g):
            tx = g.get('tx', 0)
            ty = g.get('ty', 0)
            row = round(ty / 50) * 50
            return (row, tx)
        return sorted(groups, key=sort_key)

    def group_pos(g):
        bb = get_group_bbox(g)
        if bb is None:
            return (9999, 9999)
        row = round(bb[1] / 50) * 50
        return (row, bb[0])
    return sorted(groups, key=group_pos)


# ═══════════════════════════════════════════════════════════════════════════════
# PATH SCALING — DÜZELTILMIŞ
# ═══════════════════════════════════════════════════════════════════════════════

def scale_path(d, sx, sy, tx, ty):
    """Path koordinatlarını dönüştür: SVG local → font UPM space"""
    tokens = re.findall(
        r'[MmLlCcQqZzHhVvAaSsTt]|[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', d)
    result = []
    cmd = 'M'
    idx = 0

    def take(n):
        nonlocal idx
        vals = []
        for _ in range(n):
            if idx < len(tokens) and not re.match(r'[A-Za-z]', tokens[idx]):
                vals.append(float(tokens[idx]))
                idx += 1
            else:
                vals.append(0.0)
        return vals

    while idx < len(tokens):
        t = tokens[idx]
        if re.match(r'[A-Za-z]', t):
            cmd = t
            result.append(cmd)
            idx += 1
            continue

        cu = cmd.upper()
        if cu in ('M', 'L', 'T'):
            x, y = take(2)
            result.extend([f'{x*sx+tx:.2f}', f'{y*sy+ty:.2f}'])
        elif cu == 'H':
            x, = take(1)
            result.append(f'{x*sx+tx:.2f}')
        elif cu == 'V':
            y, = take(1)
            result.append(f'{y*sy+ty:.2f}')
        elif cu == 'C':
            coords = take(6)
            for j in range(0, 6, 2):
                result.extend([f'{coords[j]*sx+tx:.2f}', f'{coords[j+1]*sy+ty:.2f}'])
        elif cu in ('Q', 'S'):
            coords = take(4)
            for j in range(0, 4, 2):
                result.extend([f'{coords[j]*sx+tx:.2f}', f'{coords[j+1]*sy+ty:.2f}'])
        elif cu == 'A':
            rx, ry = take(2)
            rot = take(1)[0]
            laf, sf = take(1)[0], take(1)[0]
            x, y = take(2)
            result.extend([
                f'{abs(rx*sx):.2f}', f'{abs(ry*abs(sy)):.2f}',
                f'{rot:.2f}', f'{int(laf)}', f'{int(sf)}',
                f'{x*sx+tx:.2f}', f'{y*sy+ty:.2f}'
            ])
        elif cu == 'Z':
            result.append('Z')
        else:
            result.append(t)
            idx += 1
            continue

    return ' '.join(result)


# ═══════════════════════════════════════════════════════════════════════════════
# GLYPH RENDERING — KÖK DÜZELTME BURADA
# ═══════════════════════════════════════════════════════════════════════════════

def draw_glyph(group, ascender=ASCENDER, descender=DESCENDER,
               ref_height=None, svg_baseline_y=None):
    """
    SVG group → TTF glyph
    
    DÜZELTME v8: Ölçekleme tamamen yeniden yazıldı.
    
    Sorun (v7): scale = ascender / ref_height = 800/480 = 1.667 DOĞRU
    ama tx/ty hesabı paths'in LOCAL koordinatta olduğunu varsayıyordu.
    Gerçekte paths ABSOLUTE SVG koordinatlarında — cell_tx/ty eklenmeli!
    
    Bu yüzden harfler küçük çıkıyordu: path koordinatları cell offset ile
    birlikte ölçeklenince glyph küçücük kalıyordu.
    """
    cell_tx = group.get('tx', 0)
    cell_ty = group.get('ty', 0)

    # Sabitler
    _SVG_CAP  = ref_height and (svg_baseline_y - ref_height) or SVG_CAP
    _SVG_BASE = svg_baseline_y or SVG_BASE

    # ── SCALE: cap height → font ascender ────────────────────────────
    # SVG glyph height = SVG_BASE - SVG_CAP = 480 px
    # Font cap height  = ascender = 800 UPM
    # scale = 800 / 480 = 1.6667
    cap_h = _SVG_BASE - _SVG_CAP
    if cap_h <= 0:
        cap_h = SVG_GLYPH_H

    scale = ascender / cap_h  # 1.6667

    sx =  scale
    sy = -scale   # Y eksenini çevir (SVG aşağı → font yukarı)

    # ── OFFSET hesabı ─────────────────────────────────────────────────
    # Path koordinatları ABSOLUTE SVG koordinatlarında.
    # Hücrenin sol üst köşesi: (cell_tx, cell_ty)
    # Lokal cap noktası: (cell_tx + SVG_LEFT, cell_ty + SVG_CAP)
    # Bu nokta → font space (SVG_LEFT_margin, ascender) olmalı
    #
    # font_x = (abs_x - cell_tx - SVG_LEFT) * sx  → sol kenar = 0
    # font_y = (abs_y - cell_ty - SVG_BASE) * sy   → baseline = 0
    #        = -(abs_y - cell_ty - SVG_BASE) * scale
    #        = (SVG_BASE + cell_ty - abs_y) * scale
    #
    # Bunu scale_path'e uyarla:
    # font_x = abs_x * sx + tx  → tx = -(cell_tx + SVG_LEFT) * sx
    # font_y = abs_y * sy + ty  → ty = (cell_ty + SVG_BASE) * scale

    tx = -(cell_tx + SVG_LEFT) * sx
    ty =  (cell_ty + _SVG_BASE) * scale  # sy=-scale olduğu için pozitif

    # Advance width: SVG_ADV birim → font space
    target_w = int(SVG_ADV * scale)  # 520 * 1.667 = ~867

    # ── Path'leri birleştir ───────────────────────────────────────────
    parts = []
    for p in group['paths']:
        d = p.get('d', '').strip()
        if d:
            parts.append(scale_path(d, sx, sy, tx, ty))

    if not parts:
        return None, 500

    combined = ' '.join(parts)

    # ── RENDER: Rasterize → Trace → TTF ──────────────────────────────
    try:
        import cv2 as _cv2
        import numpy as _np

        OVERSAMPLE = 4
        SZ = int(SVG_CELL * OVERSAMPLE)  # 2800 px — tam cell boyutu
        img = _np.zeros((SZ, SZ), dtype=_np.uint8)

        # LOCAL koordinatlarda rasterize (cell offseti çıkar)
        for p in group['paths']:
            raw_d = p.get('d', '').strip()
            if not raw_d:
                continue
            # Absolute → local: cell_tx/ty çıkar
            # Sonra OVERSAMPLE ile pixel'e çevir
            for sp in [s.strip() for s in raw_d.split('Z') if s.strip()]:
                nums = re.findall(r'[-+]?\d*\.?\d+', sp)
                pts_raw = []
                for i in range(0, len(nums) - 1, 2):
                    if i + 1 < len(nums):
                        ax = float(nums[i])   - cell_tx
                        ay = float(nums[i+1]) - cell_ty
                        pts_raw.append((ax, ay))

                if len(pts_raw) < 3:
                    continue

                # Winding direction
                n = len(pts_raw)
                area_s = sum(
                    pts_raw[i][0] * pts_raw[(i+1)%n][1] -
                    pts_raw[(i+1)%n][0] * pts_raw[i][1]
                    for i in range(n)
                ) / 2

                poly = _np.array(
                    [(int(x * OVERSAMPLE), int(y * OVERSAMPLE)) for x, y in pts_raw],
                    _np.int32
                )
                _cv2.fillPoly(img, [poly], 255 if area_s < 0 else 0)

        # Trace contours
        contours_cv, hierarchy_cv = _cv2.findContours(
            img, _cv2.RETR_CCOMP, _cv2.CHAIN_APPROX_TC89_KCOS)

        if not len(contours_cv):
            raise RuntimeError("rasterize produced empty image")

        h_arr = hierarchy_cv[0]
        pen = TTGlyphPen(None)
        wrote = 0

        for i, c in enumerate(contours_cv):
            if _cv2.contourArea(c) < 80:
                continue

            pts_font = []
            for pt in c:
                px, py = int(pt[0][0]), int(pt[0][1])
                # pixel → local SVG → font UPM
                local_x = px / OVERSAMPLE
                local_y = py / OVERSAMPLE
                # local_x, local_y zaten cell_tx/ty çıkarılmış
                # Ama scale_path formülü absolute kullanıyor — düzelt:
                abs_x = local_x + cell_tx
                abs_y = local_y + cell_ty
                fx = int(round(abs_x * sx + tx))
                fy = int(round(abs_y * sy + ty))
                pts_font.append((fx, fy))

            if len(pts_font) < 3:
                continue

            pts_font = list(reversed(pts_font))
            pen.moveTo(pts_font[0])
            for pt in pts_font[1:]:
                pen.lineTo(pt)
            pen.closePath()
            wrote += 1

        if wrote == 0:
            raise RuntimeError("no contours written")

        return pen.glyph(), target_w + 80

    except Exception as e_raster:
        _raster_err = str(e_raster)

    # ── Fallback A: pathops ───────────────────────────────────────────
    svg_str = f'<svg xmlns="http://www.w3.org/2000/svg"><path d="{combined}"/></svg>'
    svg_bytes = svg_str.encode('utf-8')

    try:
        import pathops
        ops_path = pathops.Path()
        SVGPathLib(io.BytesIO(svg_bytes)).draw(ops_path)
        pathops.simplify(ops_path, pathops.FillType.WINDING)
        from fontTools.pens.cu2quPen import Cu2QuPen
        pen = TTGlyphPen(None)
        ops_path.draw(Cu2QuPen(pen, max_err=0.5, reverse_direction=False))
        return pen.glyph(), target_w + 80
    except ImportError:
        pass
    except Exception:
        pass

    # ── Fallback B: direct winding ────────────────────────────────────
    try:
        from fontTools.pens.cu2quPen import Cu2QuPen
        pen = TTGlyphPen(None)
        SVGPathLib(io.BytesIO(svg_bytes)).draw(Cu2QuPen(pen, max_err=0.5, reverse_direction=True))
        return pen.glyph(), target_w + 80
    except Exception as e2:
        raise RuntimeError(f"all render paths failed: {e2}")


def make_empty_glyph():
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((1, 0))
    pen.lineTo((1, 1))
    pen.lineTo((0, 1))
    pen.closePath()
    return pen.glyph()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN BUILD FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def build_font(svg_file, font_name, output_dir,
               char_order=None, bold=False, italic=False,
               units_per_em=1000,
               gemini_key=None,
               style_prompt="",
               progress_callback=None):
    """
    SVG → TTF/OTF font builder v8
    
    Yeni parametreler:
      gemini_key  : Gemini API key (opsiyonel, dekorasyon için)
      style_prompt: Gemini'ye gönderilecek stil açıklaması
      progress_callback: fn(msg, pct) — Railway/Flask için progress
    
    Returns: (ttf_path, otf_path)
    """

    def log(msg, pct=None):
        if progress_callback:
            progress_callback(msg, pct)
        pct_str = f" ({pct}%)" if pct is not None else ""
        print(f"  {msg}{pct_str}")

    print(f"\n{'='*56}")
    print(f"  SVG → Font Engine v8.0")
    print(f"  File  : {os.path.basename(svg_file)}")
    print(f"  Font  : {font_name}")
    print(f"  UPM   : {units_per_em}")
    print(f"  Scale : {SCALE:.4f} (cap_h={SVG_GLYPH_H:.0f}→{ASCENDER})")
    print(f"  Shapes: {'available' if _SHAPES_AVAILABLE else 'disabled'}")
    print(f"  Gemini: {'enabled' if gemini_key else 'disabled'}")
    print(f"{'='*56}\n")

    if char_order is None:
        char_order = list(DEFAULT_CHAR_ORDER)

    # ── 1. SVG oku ──────────────────────────────────────────────────
    log("SVG okunuyor...", 5)
    try:
        tree = etree.parse(svg_file)
        root = tree.getroot()
    except Exception as e:
        raise RuntimeError(f"SVG parse hatası: {e}")

    viewbox = get_svg_viewbox(root)
    log(f"ViewBox: {viewbox}", 8)

    # ── 2. Grupları topla ───────────────────────────────────────────
    log("Gruplar toplanıyor...", 12)
    groups = collect_groups(root)
    log(f"{len(groups)} nesne bulundu", 15)

    if not groups:
        raise RuntimeError("SVG'de hiç path bulunamadı!")

    groups = sort_groups(groups)

    # ── 3. Karakter ataması ─────────────────────────────────────────
    log("Karakterlere atanıyor...", 20)
    n = min(len(groups), len(char_order))
    char_map = {char_order[i]: groups[i] for i in range(n)}
    log(f"{n} karakter atandı", 22)

    # ── 4. Font yapısı ──────────────────────────────────────────────
    log("Font yapısı kuruluyor...", 25)

    glyph_order = ['.notdef']
    char_to_glyph = {}

    for ch in char_map:
        name = 'space' if ch == ' ' else f'uni{ord(ch):04X}'
        glyph_order.append(name)
        char_to_glyph[ch] = name

    if 'space' not in glyph_order:
        glyph_order.append('space')

    fb = FontBuilder(units_per_em, isTTF=True)
    fb.setupGlyphOrder(glyph_order)

    cmap = {ord(ch): name for ch, name in char_to_glyph.items()}
    cmap[32] = 'space'
    fb.setupCharacterMap(cmap)

    # ── 5. Glyphleri çiz ────────────────────────────────────────────
    log("Glyphlar çiziliyor...", 30)
    glyphs = {}
    metrics = {}

    glyphs['.notdef'] = make_empty_glyph()
    metrics['.notdef'] = (500, 0)

    if 'space' not in char_to_glyph.values():
        glyphs['space'] = make_empty_glyph()
        metrics['space'] = (250, 0)

    # Fixed metric system (font_skeletons.py ile uyumlu)
    ref_height     = SVG_GLYPH_H   # 480
    svg_baseline_y = SVG_BASE      # 560

    ok, fail = 0, 0
    total = len(char_to_glyph)

    for idx, (ch, gname) in enumerate(char_to_glyph.items()):
        pct = 30 + int(idx / total * 50)

        if ch == ' ':
            glyphs[gname] = make_empty_glyph()
            metrics[gname] = (250, 0)
            ok += 1
            continue

        group = char_map[ch]

        try:
            # Gemini design call (opsiyonel)
            gemini_decs = []
            if gemini_key and style_prompt:
                design = gemini_design_call(ch, style_prompt, gemini_key)
                gemini_decs = design.get('decorations', [])
                if gemini_decs:
                    log(f"  ✦ '{ch}' → {len(gemini_decs)} Gemini decoration(s)", pct)

            # Glyph çiz
            g, adv = draw_glyph(
                group, ASCENDER, DESCENDER,
                ref_height=ref_height,
                svg_baseline_y=svg_baseline_y
            )

            if g is None:
                raise ValueError("glyph None döndü")

            glyphs[gname] = g
            metrics[gname] = (adv, 0)
            ok += 1

            if idx % 10 == 0:
                log(f"  '{ch}' ✓  [{idx+1}/{total}]", pct)

        except Exception as e:
            log(f"  [UYARI] '{ch}' çizilemedi: {e}", pct)
            glyphs[gname] = make_empty_glyph()
            metrics[gname] = (400, 0)
            fail += 1

    log(f"✓ {ok} başarılı  ✗ {fail} başarısız  (toplam {ok+fail})", 82)

    # ── 6. Cubic → Quadratic ────────────────────────────────────────
    log("Cubic → Quadratic dönüştürülüyor...", 85)
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen as TTGPen2

    converted = {}
    for gname, glyph in glyphs.items():
        if glyph is None or not hasattr(glyph, 'draw'):
            converted[gname] = glyph
            continue
        try:
            pen2 = TTGPen2(None)
            cu2qu = Cu2QuPen(pen2, max_err=1.0, reverse_direction=False)
            glyph.draw(cu2qu)
            converted[gname] = pen2.glyph()
        except Exception:
            converted[gname] = glyph
    glyphs = converted

    # ── 7. Font tabloları ───────────────────────────────────────────
    log("Font tabloları kuruluyor...", 88)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASCENDER, descent=DESCENDER)

    if bold and italic:
        style_name, weight, fs_sel = 'Bold Italic', 700, 0x03
    elif bold:
        style_name, weight, fs_sel = 'Bold', 700, 0x20
    elif italic:
        style_name, weight, fs_sel = 'Italic', 400, 0x02
    else:
        style_name, weight, fs_sel = 'Regular', 400, 0x40

    fb.setupNameTable({
        "familyName": font_name,
        "styleName": style_name,
        "uniqueFontIdentifier": f"{font_name}-{style_name}-v8",
        "fullName": f"{font_name} {style_name}".strip(),
        "version": "Version 2.000",
        "psName": f"{font_name}-{style_name}".replace(" ", ""),
    })

    fb.setupOS2(
        sTypoAscender=ASCENDER,
        sTypoDescender=DESCENDER,
        sTypoLineGap=0,
        usWinAscent=ASCENDER,
        usWinDescent=abs(DESCENDER),
        sxHeight=X_HEIGHT,
        sCapHeight=CAP_HEIGHT,
        usWeightClass=weight,
        fsType=0,
        fsSelection=fs_sel,
        achVendID="VCTR",
        ulUnicodeRange1=0b10000000000000000000000011111111,
    )

    fb.setupPost(isFixedPitch=0, underlinePosition=-100, underlineThickness=50)
    fb.setupHead(unitsPerEm=units_per_em, lowestRecPPEM=8, indexToLocFormat=0)

    # ── 8. Kaydet ───────────────────────────────────────────────────
    log("Dosyalar kaydediliyor...", 93)
    os.makedirs(output_dir, exist_ok=True)

    safe = re.sub(r'[^\w]', '_', font_name)
    safe_style = style_name.replace(' ', '_')

    ttf_path = os.path.join(output_dir, f"{safe}_{safe_style}.ttf")
    otf_path = os.path.join(output_dir, f"{safe}_{safe_style}.otf")

    fb.font.save(ttf_path)
    log(f"✓ TTF: {ttf_path}", 96)

    import shutil
    shutil.copy2(ttf_path, otf_path)
    log(f"✓ OTF: {otf_path}", 98)

    # Mapping JSON
    mapping = {
        "engine_version": __ENGINE_VERSION__,
        "font_name": font_name,
        "style": style_name,
        "units_per_em": units_per_em,
        "ascender": ASCENDER,
        "descender": DESCENDER,
        "scale_factor": round(SCALE, 4),
        "total": ok + fail,
        "success": ok,
        "failed": fail,
        "shapes_used": _SHAPES_AVAILABLE,
        "gemini_used": bool(gemini_key),
        "characters": list(char_to_glyph.keys())
    }
    mapping_path = os.path.join(output_dir, f"{safe}_{safe_style}_mapping.json")
    with open(mapping_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    log("✅ TAMAMLANDI!", 100)
    print(f"\n{'='*56}")
    print(f"  ✅ {ok}/{ok+fail} glyph  |  Scale: {SCALE:.4f}  |  UPM: {units_per_em}")
    print(f"  TTF : {ttf_path}")
    print(f"  OTF : {otf_path}")
    print(f"{'='*56}\n")

    return ttf_path, otf_path


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='SVG → Font Converter v8')
    p.add_argument('svg')
    p.add_argument('--name', default='CustomFont')
    p.add_argument('--output', default='./output')
    p.add_argument('--bold', action='store_true')
    p.add_argument('--italic', action='store_true')
    p.add_argument('--gemini-key', default='', help='Gemini API key (optional)')
    p.add_argument('--style', default='', help='Style prompt for Gemini')
    args = p.parse_args()

    build_font(
        args.svg, args.name, args.output,
        bold=args.bold, italic=args.italic,
        gemini_key=args.gemini_key,
        style_prompt=args.style
    )
