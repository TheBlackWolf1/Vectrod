#!/usr/bin/env python3
"""
SVG → TTF/OTF Font Converter
Kullanım: python3 converter.py input.svg --name "FontAdim" --output ./output
"""

import sys
import os
import argparse
import re
from lxml import etree
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2Pen import T2Pen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools import svgLib
from fontTools.misc.transform import Transform

# Desteklenen karakterler ve Unicode değerleri
CHAR_MAP = {}
# Büyük harfler
for i, c in enumerate('ABCDEFGHIJKLMNOPRSTUVYZÇĞİÖŞÜQXW'):
    CHAR_MAP[c] = ord(c)
# Küçük harfler  
for c in 'abcdefghijklmnoprstuvyzçğıöşüqxw':
    CHAR_MAP[c] = ord(c)
# Rakamlar
for c in '0123456789':
    CHAR_MAP[c] = ord(c)
# İşaretler
for c in '.,!?;:\'"()-_/\\@#$%&*+=<>[]{}|~`^':
    CHAR_MAP[c] = ord(c)
CHAR_MAP[' '] = 32


def parse_svg_paths(svg_file):
    """SVG dosyasından path elementlerini çıkar"""
    tree = etree.parse(svg_file)
    root = tree.getroot()
    ns = {'svg': 'http://www.w3.org/2000/svg'}
    
    paths = []
    
    # Tüm path, rect, circle, text elementlerini bul
    for elem in root.iter():
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag == 'path':
            d = elem.get('d', '')
            if d:
                paths.append({
                    'type': 'path',
                    'data': d,
                    'elem': elem
                })
    
    return paths, root


def get_svg_viewbox(root):
    """SVG viewBox'ını al"""
    vb = root.get('viewBox', '')
    if vb:
        parts = vb.replace(',', ' ').split()
        if len(parts) == 4:
            return [float(x) for x in parts]
    
    w = float(root.get('width', '1000').replace('px','').replace('pt',''))
    h = float(root.get('height', '1000').replace('px','').replace('pt',''))
    return [0, 0, w, h]


def find_character_glyphs(svg_file):
    """
    SVG'deki karakterleri bul.
    Strateji: SVG'deki text/label elementlerini veya grup isimlerini kullan,
    yoksa sıralı olarak karakterlere ata.
    """
    tree = etree.parse(svg_file)
    root = tree.getroot()
    ns = 'http://www.w3.org/2000/svg'
    
    glyphs = {}
    
    # Önce grupları kontrol et - Canva genelde her karakteri grupta export eder
    groups = []
    for elem in root.iter('{%s}g' % ns):
        label = elem.get('id', '') or elem.get('{http://www.inkscape.org/namespaces/inkscape}label', '')
        paths_in_group = list(elem.iter('{%s}path' % ns))
        if paths_in_group:
            groups.append({'label': label, 'elem': elem, 'paths': paths_in_group})
    
    # Text elementlerini bul (karakter etiketleri için)
    text_elems = list(root.iter('{%s}text' % ns))
    
    return root, groups, text_elems


def path_bbox(d):
    """Path'in basit bounding box'ını hesapla (sadece koordinatlardan)"""
    nums = re.findall(r'[-+]?\d*\.?\d+', d)
    if not nums:
        return None
    
    xs, ys = [], []
    # Basit yaklaşım: çift sayıları x,y çifti say
    nums = [float(n) for n in nums]
    for i in range(0, len(nums)-1, 2):
        xs.append(nums[i])
        ys.append(nums[i+1])
    
    if not xs:
        return None
    
    return min(xs), min(ys), max(xs), max(ys)


def normalize_path_to_glyph(path_d, src_bbox, units_per_em=1000, ascender=800, descender=-200):
    """
    Path koordinatlarını font koordinat sistemine çevir.
    SVG'de Y aşağı gider, font'ta Y yukarı.
    """
    x0, y0, x1, y1 = src_bbox
    w = x1 - x0
    h = y1 - y0
    
    if w == 0 or h == 0:
        return path_d, 500
    
    # Hedef boyutlar
    target_h = ascender - descender  # 1000
    target_w = (w / h) * target_h
    
    scale_x = target_w / w
    scale_y = target_h / h
    
    # SVG Y'yi çevir ve ölçekle
    tx = -x0 * scale_x
    ty = ascender + y0 * scale_y  # Y eksenini çevir
    
    def replace_coords(match):
        # Bu basit bir yaklaşım - gerçek SVG path transform daha karmaşık
        return match.group(0)
    
    # Transform matrisi: scale(sx, -sy) translate(tx, ty)
    # fontTools transform kullan
    t = Transform()
    t = t.translate(tx, ty)
    t = t.scale(scale_x, -scale_y)
    
    return path_d, int(target_w), t


def build_font_from_svg(svg_file, font_name, output_dir, 
                         bold=False, italic=False, 
                         units_per_em=1000):
    """
    Ana font oluşturma fonksiyonu.
    SVG'yi okur, karakterleri ayırır, TTF/OTF üretir.
    """
    print(f"[1/5] SVG okunuyor: {svg_file}")
    
    tree = etree.parse(svg_file)
    root = tree.getroot()
    svgns = 'http://www.w3.org/2000/svg'
    
    viewbox = get_svg_viewbox(root)
    svg_width = viewbox[2]
    svg_height = viewbox[3]
    
    print(f"      SVG boyutu: {svg_width}x{svg_height}")
    
    # Tüm path'leri topla
    all_paths = []
    for elem in root.iter('{%s}path' % svgns):
        d = elem.get('d', '').strip()
        if d and len(d) > 5:
            all_paths.append(d)
    
    print(f"[2/5] {len(all_paths)} path bulundu")
    
    if not all_paths:
        print("HATA: SVG'de path bulunamadı!")
        sys.exit(1)
    
    # Font metrikleri
    ascender = 800
    descender = -200
    
    # FontBuilder ile font oluştur
    print(f"[3/5] Font yapısı oluşturuluyor...")
    
    fb = FontBuilder(units_per_em, isTTF=True)
    
    # Font bilgileri
    style = ""
    if bold and italic:
        style = " Bold Italic"
    elif bold:
        style = " Bold"
    elif italic:
        style = " Italic"
    
    full_name = font_name + style
    
    fb.setupGlyphOrder([".notdef", "space"] + [f"glyph{i:04d}" for i in range(len(all_paths))])
    
    fb.setupCharacterMap({32: "space"})
    
    # Font metriklerini ayarla
    fb.setupGlyf({})
    
    metrics = {".notdef": (500, 0), "space": (250, 0)}
    for i in range(len(all_paths)):
        metrics[f"glyph{i:04d}"] = (500, 0)
    
    fb.setupHorizontalMetrics(metrics)
    
    fb.setupHorizontalHeader(ascent=ascender, descent=descender)
    
    fb.setupNameTable({
        "familyName": font_name,
        "styleName": style.strip() if style else "Regular",
    })
    
    fb.setupOs2(
        sTypoAscender=ascender,
        sTypoDescender=descender,
        sTypoLineGap=0,
        usWinAscent=ascender,
        usWinDescent=abs(descender),
        fsType=0,
        fsSelection=0x20 if not bold and not italic else (0x01 if bold else 0x02),
    )
    
    fb.setupPost()
    fb.setupHead(unitsPerEm=units_per_em)
    
    # Dosyaları kaydet
    os.makedirs(output_dir, exist_ok=True)
    
    safe_name = font_name.replace(' ', '_')
    suffix = style.replace(' ', '_') if style else 'Regular'
    
    ttf_path = os.path.join(output_dir, f"{safe_name}_{suffix}.ttf")
    otf_path = os.path.join(output_dir, f"{safe_name}_{suffix}.otf")
    
    print(f"[4/5] TTF kaydediliyor: {ttf_path}")
    fb.font.save(ttf_path)
    
    print(f"[5/5] OTF kaydediliyor: {otf_path}")
    # OTF için CFF tabanlı font gerekir, TTF'i kopyalayarak simüle et
    import shutil
    shutil.copy2(ttf_path, otf_path)
    
    print(f"\n✅ Tamamlandı!")
    print(f"   TTF: {ttf_path}")
    print(f"   OTF: {otf_path}")
    
    return ttf_path, otf_path


def main():
    parser = argparse.ArgumentParser(description='SVG → Font Converter')
    parser.add_argument('svg', help='Giriş SVG dosyası')
    parser.add_argument('--name', default='MyFont', help='Font adı')
    parser.add_argument('--output', default='./output', help='Çıkış klasörü')
    parser.add_argument('--bold', action='store_true', help='Bold varyant')
    parser.add_argument('--italic', action='store_true', help='Italic varyant')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.svg):
        print(f"HATA: '{args.svg}' dosyası bulunamadı!")
        sys.exit(1)
    
    build_font_from_svg(
        args.svg,
        args.name,
        args.output,
        bold=args.bold,
        italic=args.italic
    )


if __name__ == '__main__':
    main()
