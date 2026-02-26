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
    Bir grubu glyph'e çevir.
    
    ref_height: büyük harf yüksekliği (SVG birimlerinde) — orantılı scale için
    svg_baseline_y: SVG'de baseline'ın y koordinatı (büyük harflerin y_max ortalaması)
    """
    bb = get_group_bbox(group)
    if bb is None:
        return None, 500
    
    x0, y0, x1, y1 = bb
    src_w = x1 - x0
    src_h = y1 - y0
    
    if src_w <= 0 or src_h <= 0:
        return None, 500
    
    if ref_height and ref_height > 0 and svg_baseline_y is not None:
        # Scale faktörü: büyük harf yüksekliği = font ascender
        scale = ascender / ref_height
        target_w = int(src_w * scale)
        
        # SVG Y aşağı gider, font Y yukarı
        # svg_baseline_y → font'ta 0 (baseline)
        # SVG'de yukarı gitmek = font'ta yukarı gitmek
        sx = scale
        sy = -scale
        # x: sol kenarı 0'a al
        tx = -x0 * sx
        # y: SVG baseline'ı → font baseline (0)
        # font_y = (svg_baseline_y - svg_y) * scale
        # yani: font_y = svg_baseline_y * scale - svg_y * scale
        ty = svg_baseline_y * scale  # bu baseline'ı 0'a alır, yukarısı pozitif
    else:
        scale = (ascender - descender) / src_h
        target_w = int(src_w * scale)
        sx = scale
        sy = -scale
        tx = -x0 * sx
        ty = ascender + y0 * scale
    
    # Tüm path'leri birleştir
    parts = []
    for p in group['paths']:
        d = p.get('d', '').strip()
        if d:
            parts.append(scale_path(d, sx, sy, tx, ty))
    
    if not parts:
        return None, 500
    
    combined = ' '.join(parts)
    
    # fontTools ile çiz
    svg_str = f'<svg xmlns="http://www.w3.org/2000/svg"><path d="{combined}"/></svg>'
    
    try:
        from fontTools.pens.cu2quPen import Cu2QuPen
        pen = TTGlyphPen(None)
        cu2qu_pen = Cu2QuPen(pen, max_err=1.0, reverse_direction=False)
        svg_obj = SVGPathLib(io.BytesIO(svg_str.encode('utf-8')))
        svg_obj.draw(cu2qu_pen)  # direkt quadratic'e çiz
        glyph = pen.glyph()
        return glyph, target_w + 80
    except Exception as e:
        raise RuntimeError(f"SVGPath çizim hatası: {e}")


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

    # Referans: büyük harflerden baseline ve cap yüksekliği hesapla
    ref_cap_heights = []
    ref_baseline_ys = []  # SVG'de baseline y koordinatları (y_max büyük harfler)
    for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        if ch in char_map:
            bb = get_group_bbox(char_map[ch])
            if bb:
                ref_cap_heights.append(bb[3] - bb[1])  # yükseklik
                ref_baseline_ys.append(bb[3])           # y_max = baseline
    
    ref_height = sum(ref_cap_heights) / len(ref_cap_heights) if ref_cap_heights else None
    svg_baseline_y = sum(ref_baseline_ys) / len(ref_baseline_ys) if ref_baseline_ys else None
    
    if ref_height:
        print(f"      Referans cap yüksekliği: {ref_height:.1f} birim")
        print(f"      SVG baseline Y: {svg_baseline_y:.2f}")

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
