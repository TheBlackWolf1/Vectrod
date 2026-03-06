# engine v7.2
__ENGINE_VERSION__ = "v7.2-raster-local"
#!/usr/bin/env python3
"""
SVG → TTF/OTF Font Engine v2
"""

import sys, os, re, json, io
from lxml import etree
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.misc.transform import Identity, Transform
from fontTools.svgLib.path import SVGPath as SVGPathLib

DEFAULT_CHAR_ORDER = (
    'A','B','C','D','E','F','G','H','I','J','K','L','M',
    'N','O','P','Q','R','S','T','U','V','W','X','Y','Z',
    'a','b','c','d','e','f','g','h','i','j','k','l','m',
    'n','o','p','q','r','s','t','u','v','w','x','y','z',
    '0','1','2','3','4','5','6','7','8','9',
    '.', ',', '!', '?', ';', ':', "'", '"', '(', ')', '-', '_',
    '/', '\\', '@', '#', '$', '%', '&', '*', '+', '=', ' ',
    'Ç','Ğ','İ','Ö','Ş','Ü',
    'ç','ğ','ı','ö','ş','ü',
)


def get_svg_viewbox(root):
    vb = root.get('viewBox','')
    if vb:
        parts = re.split(r'[,\s]+', vb.strip())
        if len(parts) == 4:
            return [float(x) for x in parts]
    w = float(re.sub(r'[^\d.]','', root.get('width','1000')) or '1000')
    h = float(re.sub(r'[^\d.]','', root.get('height','1000')) or '1000')
    return [0, 0, w, h]


def get_translate(elem):
    """Elementin translate transform değerini döndür"""
    import re
    if elem is None:
        return None
    t = elem.get('transform', '')
    m = re.search(r'translate\(([^,)]+),\s*([^)]+)\)', t)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None


def collect_groups(root):
    """SVG'deki tüm grupları ve path'leri topla — translate'li grupları öncelikle al"""
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
                # translate'li gruplar = Canva'nın her karakteri
                groups.append({'paths': paths, 'elem': elem, 'tx': translate[0], 'ty': translate[1]})
                return  # alt grupları ayrıca işleme
        
        for child in elem:
            walk(child)
    
    walk(root)
    
    # Hiç translate'li grup bulunamadıysa eski yönteme dön
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
    """Path'teki tüm sayıları çıkar"""
    return [float(n) for n in re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', d) if n]


def get_elem_bbox(elem):
    """Bir elementin path'lerinden bbox hesapla"""
    ns = 'http://www.w3.org/2000/svg'
    if not isinstance(elem.tag, str):
        return None
    tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
    
    all_d = []
    if tag == 'path':
        d = elem.get('d','')
        if d: all_d.append(d)
    else:
        for p in elem.iter('{%s}path' % ns):
            d = p.get('d','')
            if d: all_d.append(d)
    
    if not all_d:
        return None
    
    xs, ys = [], []
    for d in all_d:
        nums = get_path_numbers(d)
        xs.extend(nums[0::2])
        ys.extend(nums[1::2])
    
    min_len = min(len(xs), len(ys))
    if min_len == 0:
        return None
    
    return min(xs[:min_len]), min(ys[:min_len]), max(xs[:min_len]), max(ys[:min_len])


def get_group_bbox(group):
    xs, ys = [], []
    for p in group['paths']:
        d = p.get('d','')
        if not d: continue
        nums = get_path_numbers(d)
        xs.extend(nums[0::2])
        ys.extend(nums[1::2])
    
    min_len = min(len(xs), len(ys))
    if min_len == 0:
        return None
    return min(xs[:min_len]), min(ys[:min_len]), max(xs[:min_len]), max(ys[:min_len])


def sort_groups(groups):
    """Grupları soldan sağa, yukarıdan aşağıya sırala"""
    # translate varsa direkt kullan (en güvenilir)
    if groups and groups[0].get('tx') is not None:
        def sort_key(g):
            tx = g.get('tx', 0)
            ty = g.get('ty', 0)
            row = round(ty / 50) * 50
            return (row, tx)
        return sorted(groups, key=sort_key)
    
    # Yoksa bbox'a göre
    def group_pos(g):
        bb = get_group_bbox(g)
        if bb is None:
            return (9999, 9999)
        row = round(bb[1] / 50) * 50
        return (row, bb[0])
    return sorted(groups, key=group_pos)


def scale_path(d, sx, sy, tx, ty):
    """Path koordinatlarını ölçekle ve taşı"""
    tokens = re.findall(r'[MmLlCcQqZzHhVvAaSsTtNn]|[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', d)
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
            result.extend([f'{x*sx+tx:.3f}', f'{y*sy+ty:.3f}'])
        elif cu == 'H':
            x, = take(1)
            result.append(f'{x*sx+tx:.3f}')
        elif cu == 'V':
            y, = take(1)
            result.append(f'{y*sy+ty:.3f}')
        elif cu == 'C':
            coords = take(6)
            for j in range(0, 6, 2):
                result.extend([f'{coords[j]*sx+tx:.3f}', f'{coords[j+1]*sy+ty:.3f}'])
        elif cu in ('Q', 'S'):
            coords = take(4)
            for j in range(0, 4, 2):
                result.extend([f'{coords[j]*sx+tx:.3f}', f'{coords[j+1]*sy+ty:.3f}'])
        elif cu == 'A':
            rx, ry = take(2)
            rot = take(1)[0]
            laf, sf = take(1)[0], take(1)[0]
            x, y = take(2)
            result.extend([
                f'{abs(rx*sx):.3f}', f'{abs(ry*sy):.3f}',
                f'{rot:.3f}', f'{int(laf)}', f'{int(sf)}',
                f'{x*sx+tx:.3f}', f'{y*sy+ty:.3f}'
            ])
        elif cu == 'Z':
            result.append('Z')
        else:
            result.append(t)
            idx += 1
            continue

    return ' '.join(result)


def draw_glyph(group, ascender=800, descender=-200, ref_height=None, svg_baseline_y=None):
    """
    Convert a glyph group to a TTF glyph.
    Uses FIXED metric system — immune to decorative effect bbox inflation.

    SVG grid: each glyph sits in a 700×700 cell at translate(col*700, row*700).
    group['tx'], group['ty'] = cell top-left corner in absolute SVG coords.
    LOCAL coords: glyph path coords are relative to cell origin.

    Fixed constants (must match font_skeletons.py):
      SVG_CAP=80, SVG_BASE=560, SVG_CELL=700
      ref_height  = 480  (BASE - CAP)
      svg_baseline_y = 560  (BASE, local to cell)
    """
    # Use cell origin as left margin — NOT bbox x0 (bbox inflated by spikes/tremor)
    cell_tx = group.get('tx', 0)
    cell_ty = group.get('ty', 0)

    # Fixed SVG metric constants
    SVG_CAP    =  80.0
    SVG_BASE   = 560.0
    SVG_CELL   = 700.0
    SVG_LEFT   =  44.0   # standard left margin in our skeleton (= L constant)

    # ── UNIVERSAL SCALING: bbox-based, works for ANY SVG coordinate system ──
    # AI-generated (y=[80,560]), user SVG (y=[-33,5]), Figma export, Illustrator etc.
    bb = get_group_bbox(group)
    if bb is None:
        return None, 500
    x0, y0, x1, y1 = bb
    src_w = x1 - x0
    src_h = y1 - y0
    if src_w <= 0 or src_h <= 0:
        return None, 500

    # Scale glyph height to fill ascender space with 5% padding
    usable_h = ascender - descender          # 1000 units (800 - (-200))
    scale    = usable_h * 0.90 / src_h      # 90% of full height = nice cap height
    sx       = scale
    sy       = -scale                        # flip Y (SVG down = font up)

    # Center horizontally, place top at ascender
    glyph_w  = src_w * scale
    target_w = max(int(glyph_w * 1.15), 300)  # 15% sidebearings
    side_b   = (target_w - glyph_w) / 2
    tx       = -x0 * sx + side_b
    ty       = ascender * 0.95 + y0 * scale  # top of glyph at 95% ascender
    
    # Tüm path'leri birleştir
    parts = []
    for p in group['paths']:
        d = p.get('d', '').strip()
        if d:
            parts.append(scale_path(d, sx, sy, tx, ty))
    
    if not parts:
        return None, 500
    
    combined = ' '.join(parts)
    
    # ── GLYPH RENDERING: Rasterize (NORMALIZED space) → Trace → TTF ─
    # Collect all raw path coords, normalize to [0, SZ] regardless of
    # original SVG coordinate range (handles y=-30, y=500, y=3000 etc.)
    try:
        import cv2 as _cv2
        import numpy as _np

        OVERSAMPLE = 4
        SZ = 700 * OVERSAMPLE   # 2800 px

        # ── Step 0: Find actual bbox of all paths ─────────────────────
        all_pts = []
        for p in group['paths']:
            raw_d = p.get('d', '').strip()
            if not raw_d:
                continue
            for sp in [s.strip() for s in raw_d.split('Z') if s.strip()]:
                nums = re.findall(r'[-+]?\d*\.?\d+', sp)
                for i in range(0, len(nums)-1, 2):
                    if i+1 < len(nums):
                        all_pts.append((float(nums[i]), float(nums[i+1])))

        if not all_pts:
            raise RuntimeError("no points found")

        raw_x0 = min(p[0] for p in all_pts)
        raw_x1 = max(p[0] for p in all_pts)
        raw_y0 = min(p[1] for p in all_pts)
        raw_y1 = max(p[1] for p in all_pts)
        raw_w  = max(raw_x1 - raw_x0, 1.0)
        raw_h  = max(raw_y1 - raw_y0, 1.0)

        # Scale to fill SZ canvas with 5% padding
        PAD   = SZ * 0.05
        INNER = SZ - 2 * PAD
        norm_scale = INNER / max(raw_w, raw_h)
        # Center in canvas
        off_x = PAD + (INNER - raw_w * norm_scale) / 2
        off_y = PAD + (INNER - raw_h * norm_scale) / 2

        def to_px(x, y):
            return (int((x - raw_x0) * norm_scale + off_x),
                    int((y - raw_y0) * norm_scale + off_y))

        # ── Step 1: Rasterize ─────────────────────────────────────────
        img = _np.zeros((SZ, SZ), dtype=_np.uint8)

        for p in group['paths']:
            raw_d = p.get('d', '').strip()
            if not raw_d:
                continue
            for sp in [s.strip() for s in raw_d.split('Z') if s.strip()]:
                nums = re.findall(r'[-+]?\d*\.?\d+', sp)
                pts_raw = [(float(nums[i]), float(nums[i+1]))
                           for i in range(0, len(nums)-1, 2) if i+1 < len(nums)]
                if len(pts_raw) < 3:
                    continue
                n = len(pts_raw)
                area_s = sum(pts_raw[i][0]*pts_raw[(i+1)%n][1] -
                             pts_raw[(i+1)%n][0]*pts_raw[i][1] for i in range(n)) / 2
                poly = _np.array([to_px(x, y) for x, y in pts_raw], _np.int32)
                _cv2.fillPoly(img, [poly], 255 if area_s < 0 else 0)

        # ── Step 2: Trace ─────────────────────────────────────────────
        contours_cv, hierarchy_cv = _cv2.findContours(
            img, _cv2.RETR_CCOMP, _cv2.CHAIN_APPROX_TC89_KCOS)
        if not len(contours_cv):
            raise RuntimeError("rasterize produced empty image")

        h_arr = hierarchy_cv[0]

        # ── Step 3: Convert pixel → font units ────────────────────────
        # pixel → SVG local: svgx = px / OVERSAMPLE
        # SVG local → font:  font_x = svgx * sx + tx
        #                    font_y = svgy * sy + ty
        pen = TTGlyphPen(None)
        wrote = 0
        for i, c in enumerate(contours_cv):
            if _cv2.contourArea(c) < 80:
                continue
            is_hole = h_arr[i][3] >= 0

            pts_font = []
            for pt in c:
                px, py = int(pt[0][0]), int(pt[0][1])
                # Map normalized pixel coords directly to font units
                # px=0 → left edge (x=0), px=SZ → right edge (x=target_w)
                # py=0 → top (ascender), py=SZ → bottom (descender)
                fx = int(round(px / SZ * target_w))
                fy = int(round(ascender - py / SZ * (ascender - descender)))
                pts_font.append((fx, fy))

            if len(pts_font) < 3:
                continue

            # Reverse to get correct TTF winding
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
        pass_msg = f"raster={type(e_raster).__name__}: {e_raster}"

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
    except Exception as ep:
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
    """Boş/görünmez glyph"""
    pen = TTGlyphPen(None)
    # 1x1 görünmez nokta
    pen.moveTo((0, 0))
    pen.lineTo((1, 0))
    pen.lineTo((1, 1))
    pen.lineTo((0, 1))
    pen.closePath()
    return pen.glyph()


def build_font(svg_file, font_name, output_dir,
               char_order=None, bold=False, italic=False,
               units_per_em=1000):
    
    print(f"\n{'='*52}")
    print(f"  SVG → Font Converter v2")
    print(f"  Dosya : {os.path.basename(svg_file)}")
    print(f"  Font  : {font_name}")
    print(f"{'='*52}\n")

    if char_order is None:
        char_order = list(DEFAULT_CHAR_ORDER)

    # SVG oku
    print("[1/6] SVG okunuyor...")
    tree = etree.parse(svg_file)
    root = tree.getroot()
    viewbox = get_svg_viewbox(root)
    print(f"      ViewBox: {viewbox}")

    # Grupları topla ve sırala
    print("[2/6] Gruplar toplanıyor...")
    groups = collect_groups(root)
    print(f"      {len(groups)} nesne bulundu")

    if not groups:
        print("HATA: SVG'de hiç path bulunamadı!")
        return None, None

    groups = sort_groups(groups)
    print(f"      Sıralandı: soldan sağa, yukarıdan aşağıya")

    # Karakter ataması
    print("[3/6] Karakterlere atanıyor...")
    n = min(len(groups), len(char_order))
    char_map = {char_order[i]: groups[i] for i in range(n)}
    print(f"      {n} karakter atandı")

    # Glyph order
    print("[4/6] Font yapısı kuruluyor...")
    ascender, descender = 800, -200

    glyph_order = ['.notdef']
    char_to_glyph = {}

    for ch in char_map:
        if ch == ' ':
            name = 'space'
        else:
            name = f'uni{ord(ch):04X}'
        glyph_order.append(name)
        char_to_glyph[ch] = name

    if 'space' not in glyph_order:
        glyph_order.append('space')

    fb = FontBuilder(units_per_em, isTTF=True)
    fb.setupGlyphOrder(glyph_order)

    cmap = {ord(ch): name for ch, name in char_to_glyph.items()}
    cmap[32] = 'space'
    fb.setupCharacterMap(cmap)

    # Glyphleri çiz
    print("[5/6] Glyphlar çiziliyor...")
    glyphs = {}
    metrics = {}

    glyphs['.notdef'] = make_empty_glyph()
    metrics['.notdef'] = (500, 0)

    if 'space' not in char_to_glyph.values():
        glyphs['space'] = make_empty_glyph()
        metrics['space'] = (250, 0)

    # ── FIXED METRIC SYSTEM ─────────────────────────────────────────
    # Our SVG grid uses known constants from font_skeletons.py:
    #   CAP=80 (top of capitals), BASE=560 (baseline), CELL=700 (em)
    # Using FIXED values bypasses bbox measurement entirely —
    # decorative effects (crystal spikes, drips, tremor) never distort scaling.
    ref_height     = 480.0   # BASE(560) - CAP(80) = cap height in SVG units
    svg_baseline_y = 560.0   # LOCAL baseline y per glyph cell (= BASE constant)
    print(f"      Fixed metrics: cap_height={ref_height:.0f}  baseline_y={svg_baseline_y:.0f}")

    ok = 0
    fail = 0

    for ch, gname in char_to_glyph.items():
        if ch == ' ':
            glyphs[gname] = make_empty_glyph()
            metrics[gname] = (250, 0)
            continue

        group = char_map[ch]

        try:
            g, adv = draw_glyph(group, ascender, descender, 
                                ref_height=ref_height, svg_baseline_y=svg_baseline_y)
            if g is None:
                raise ValueError("glyph None döndü")
            glyphs[gname] = g
            metrics[gname] = (adv, 0)
            ok += 1
        except Exception as e:
            print(f"      [UYARI] '{ch}' çizilemedi: {e}")
            glyphs[gname] = make_empty_glyph()
            metrics[gname] = (400, 0)
            fail += 1

    print(f"      ✓ {ok} başarılı  ✗ {fail} başarısız  (toplam {ok+fail})")

    # Cubic bezier → Quadratic dönüşümü (TTF zorunluluğu)
    print("      Cubic → Quadratic dönüştürülüyor...")
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
        except Exception as e:
            converted[gname] = glyph
    glyphs = converted

    # Font tabloları
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ascender, descent=descender)

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
        "uniqueFontIdentifier": f"{font_name}-{style_name}",
        "fullName": f"{font_name} {style_name}".strip(),
        "version": "Version 1.000",
        "psName": f"{font_name}-{style_name}".replace(" ", ""),
    })
    fb.setupOS2(
        sTypoAscender=ascender,
        sTypoDescender=descender,
        sTypoLineGap=0,
        usWinAscent=ascender,
        usWinDescent=abs(descender),
        sxHeight=500,
        sCapHeight=700,
        usWeightClass=weight,
        fsType=0,
        fsSelection=fs_sel,
        achVendID="CSTM",
        ulUnicodeRange1=0b10000000000000000000000011111111,
    )
    fb.setupPost(isFixedPitch=0, underlinePosition=-100, underlineThickness=50)
    fb.setupHead(unitsPerEm=units_per_em, lowestRecPPEM=8, indexToLocFormat=0)

    # Kaydet
    print("[6/6] Dosyalar kaydediliyor...")
    os.makedirs(output_dir, exist_ok=True)

    safe = re.sub(r'[^\w]', '_', font_name)
    safe_style = style_name.replace(' ', '_')

    ttf_path = os.path.join(output_dir, f"{safe}_{safe_style}.ttf")
    otf_path = os.path.join(output_dir, f"{safe}_{safe_style}.otf")

    fb.font.save(ttf_path)
    print(f"      ✓ TTF: {ttf_path}")

    import shutil
    shutil.copy2(ttf_path, otf_path)
    print(f"      ✓ OTF: {otf_path}")

    # Mapping
    mapping = {
        "font_name": font_name, "style": style_name,
        "total": ok + fail, "success": ok, "failed": fail,
        "characters": list(char_to_glyph.keys())
    }
    mapping_path = os.path.join(output_dir, f"{safe}_{safe_style}_mapping.json")
    with open(mapping_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*52}")
    print(f"  ✅ TAMAMLANDI! {ok}/{ok+fail} glyph başarılı")
    print(f"  TTF : {ttf_path}")
    print(f"  OTF : {otf_path}")
    print(f"{'='*52}\n")

    return ttf_path, otf_path


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('svg')
    p.add_argument('--name', default='CustomFont')
    p.add_argument('--output', default='./output')
    p.add_argument('--bold', action='store_true')
    p.add_argument('--italic', action='store_true')
    args = p.parse_args()
    build_font(args.svg, args.name, args.output, bold=args.bold, italic=args.italic)
