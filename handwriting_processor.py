"""
Handwriting → Font Processor  v4
Optimized for pencil-on-paper phone photos.
Key improvements over v3:
- No CLAHE (was boosting grid lines into ink territory)
- Strict threshold (t<165) isolates dark ink from light grid/pencil noise
- Text band detection (Y-projection) limits search to actual handwriting rows
- Glyph enhancement: dilate+close to thicken thin pencil strokes
- Contour area filtering to remove noise fragments
- cv2/Pillow dual pipeline
"""
import os, base64, traceback, io

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    import numpy as np

from PIL import Image, ImageFilter, ImageEnhance
from lxml import etree

# ─────────────────────────────────────────────────────────────
GRID_LAYOUT = [
    list('ABCDEF'), list('GHIJKL'), list('MNOPQR'), list('STUVWX'),
    list('YZabcd'), list('efghij'), list('klmnop'), list('qrstuv'),
    list('wxyz01'), list('234567'), list('89!?,.'),
]

# ─────────────────────────────────────────────────────────────
# PREPROCESSING
# ─────────────────────────────────────────────────────────────
def cv2_preprocess(img_bytes):
    """
    Converts photo to clean binary (ink=255, bg=0).
    Uses strict threshold to handle pencil-on-grid-paper photos.
    """
    arr = np.frombuffer(img_bytes, np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("Cannot decode image — try JPG or PNG")

    h, w = bgr.shape[:2]
    if w > 2800:
        s = 2800 / w
        bgr = cv2.resize(bgr, (2800, int(h*s)), interpolation=cv2.INTER_LANCZOS4)
    
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # Strict threshold: pixels darker than 165 = ink
    # Handles pencil, ballpoint, gel pen on white/grid/lined paper
    # DON'T use CLAHE here - it boosts grid lines into ink territory
    _, binary = cv2.threshold(gray, 165, 255, cv2.THRESH_BINARY_INV)

    # Small close to fill micro-gaps within strokes
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k)

    return binary, gray


def find_text_bands(binary, H, W):
    """
    Use Y-axis projection to find rows that contain handwriting.
    Excludes noise rows at top/bottom and thin grid-line bands.
    Returns list of (y1, y2) tuples for actual text rows.
    """
    y_proj = np.sum(binary > 0, axis=1).astype(float)
    smooth = cv2.GaussianBlur(y_proj.reshape(-1, 1), (1, 31), 0).flatten()
    threshold = np.max(smooth) * 0.08
    in_text = smooth > threshold

    bands = []
    in_band = False
    for y in range(H):
        if in_text[y] and not in_band:
            start = y
            in_band = True
        elif not in_text[y] and in_band:
            bands.append((start, y))
            in_band = False
    if in_band:
        bands.append((start, H))

    # Merge bands within 40px
    merged = []
    for b in bands:
        if merged and b[0] - merged[-1][1] < 40:
            merged[-1] = (merged[-1][0], b[1])
        else:
            merged.append(list(b))

    # Only keep real text bands (height >= 50px)
    return [(y1, y2) for y1, y2 in merged if y2 - y1 >= 50]


# ─────────────────────────────────────────────────────────────
# GLYPH ENHANCEMENT  
# ─────────────────────────────────────────────────────────────
def enhance_glyph(glyph_bin):
    """
    Makes thin pencil strokes thicker and removes grid noise.
    Critical for getting clean contours from pencil photos.
    """
    if glyph_bin is None or glyph_bin.size == 0:
        return glyph_bin

    # 1. Dilate: thicken thin pencil strokes
    k_thick = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (4, 4))
    g = cv2.dilate(glyph_bin, k_thick, iterations=1)

    # 2. Close: fill internal gaps in strokes
    k_fill = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (6, 6))
    g = cv2.morphologyEx(g, cv2.MORPH_CLOSE, k_fill)

    # 3. Remove noise specs smaller than 0.3% of bounding box area
    n, labels, stats, _ = cv2.connectedComponentsWithStats(g)
    min_a = g.size * 0.003
    clean = np.zeros_like(g)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_a:
            clean[labels == i] = 255

    return clean


# ─────────────────────────────────────────────────────────────
# GLYPH → SVG PATH
# ─────────────────────────────────────────────────────────────
def glyph_to_paths(glyph_bin, target=520):
    """
    Binary glyph → SVG path string (smooth cubic bezier).
    Filters tiny noise contours below 0.5% of glyph area.
    """
    if glyph_bin is None or glyph_bin.size == 0:
        return None, 0, 0

    if HAS_CV2:
        # Enhance first (thicken pencil strokes, remove noise)
        glyph_bin = enhance_glyph(glyph_bin)

        h, w = glyph_bin.shape
        scale = max(target / max(w, h, 1), 1.0)
        nw, nh = int(w * scale), int(h * scale)
        up = cv2.resize(glyph_bin, (nw, nh), interpolation=cv2.INTER_CUBIC)
        _, up = cv2.threshold(up, 127, 255, cv2.THRESH_BINARY)

        contours, _ = cv2.findContours(up, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_TC89_KCOS)
        min_c_area = nw * nh * 0.005  # filter contours < 0.5% glyph area

        parts = []
        for cnt in contours:
            if cv2.contourArea(cnt) < min_c_area:
                continue
            if len(cnt) < 3:
                continue
            eps = 0.008 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, eps, True).reshape(-1, 2)
            if len(approx) < 2:
                continue
            d = f"M {approx[0][0]:.1f} {approx[0][1]:.1f}"
            n2 = len(approx)
            for i in range(1, n2):
                p0 = approx[max(0, i-2)]
                p1 = approx[i-1]
                p2 = approx[i]
                p3 = approx[min(n2-1, i+1)]
                t = 0.28
                cp1x = p1[0] + t*(p2[0]-p0[0])/6
                cp1y = p1[1] + t*(p2[1]-p0[1])/6
                cp2x = p2[0] - t*(p3[0]-p1[0])/6
                cp2y = p2[1] - t*(p3[1]-p1[1])/6
                d += f" C {cp1x:.1f},{cp1y:.1f} {cp2x:.1f},{cp2y:.1f} {p2[0]:.1f},{p2[1]:.1f}"
            d += " Z"
            parts.append(d)

        return (" ".join(parts) if parts else None), nw, nh

    else:
        return _pil_glyph_to_paths(glyph_bin, target)


def _pil_glyph_to_paths(glyph_bin, target=520):
    """Pillow fallback for glyph vectorization"""
    h, w = glyph_bin.shape
    scale = max(target / max(w, h, 1), 1.0)
    nw, nh = int(w*scale), int(h*scale)
    img = Image.fromarray(glyph_bin).resize((nw, nh), Image.LANCZOS)
    arr = (np.array(img) > 127).astype(np.uint8)

    try:
        from scipy.ndimage import binary_erosion
        padded = np.pad(arr, 1)
        eroded = binary_erosion(padded)
        boundary = padded & ~eroded
        boundary = boundary[1:-1, 1:-1]
        ys, xs = np.where(boundary)
        if len(xs) < 3:
            return None, nw, nh
        pts = list(zip(xs.tolist(), ys.tolist()))
        step = max(1, len(pts)//80)
        pts = pts[::step]
        d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"
        for px, py in pts[1:]:
            d += f" L {px:.1f} {py:.1f}"
        d += " Z"
        return d, nw, nh
    except ImportError:
        return None, nw, nh


# ─────────────────────────────────────────────────────────────
# SEGMENTATION: SENTENCE MODE
# ─────────────────────────────────────────────────────────────
def segment_sentence(binary, gray, expected_text, H, W):
    """
    Extracts one glyph per unique character in expected_text.
    Uses text band detection + connected component analysis.
    Maps N largest-area components (sorted to reading order) → unique chars.
    """
    unique_chars = list(dict.fromkeys(c for c in expected_text if not c.isspace()))
    if not unique_chars:
        raise ValueError("No characters in expected text")

    text_bands = find_text_bands(binary, H, W)
    if not text_bands:
        raise ValueError("No text rows found. Try better lighting or darker pen.")

    band_heights = [y2 - y1 for y1, y2 in text_bands]
    min_comp_h = min(band_heights) * 0.15

    # Get connected components
    n, labels, stats, cents = cv2.connectedComponentsWithStats(binary, connectivity=8)

    candidates = []
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        cw = stats[i, cv2.CC_STAT_WIDTH]
        ch = stats[i, cv2.CC_STAT_HEIGHT]
        cx, cy = cents[i]

        if not any(y1 <= cy <= y2 for y1, y2 in text_bands):
            continue
        if ch < min_comp_h or a < 80:
            continue
        if cw > W * 0.22:
            continue
        ar = cw / max(ch, 1)
        if ar > 8 or ar < 0.05:
            continue

        candidates.append({
            'i': i, 'a': a, 'w': cw, 'h': ch,
            'cx': float(cx), 'cy': float(cy),
            'x': stats[i, cv2.CC_STAT_LEFT],
            'y': stats[i, cv2.CC_STAT_TOP]
        })

    if not candidates:
        raise ValueError("No characters found. Use darker pen or pen instead of pencil.")

    # Group letter+dot pairs (i dot, j dot, accents)
    med_h = float(np.median([c['h'] for c in candidates]))
    used = set()
    groups = []
    sv = sorted(candidates, key=lambda c: -c['a'])
    for i, c in enumerate(sv):
        if i in used:
            continue
        group = [c]
        used.add(i)
        for j, c2 in enumerate(sv):
            if j in used or j == i:
                continue
            if abs(c['cx'] - c2['cx']) < med_h * 0.45:
                group.append(c2)
                used.add(j)
        x1 = min(g['x'] for g in group)
        y1_ = min(g['y'] for g in group)
        x2 = max(g['x'] + g['w'] for g in group)
        y2_ = max(g['y'] + g['h'] for g in group)
        groups.append({
            'x': x1, 'y': y1_, 'x2': x2, 'y2': y2_,
            'cx': float(np.mean([g['cx'] for g in group])),
            'cy': float(np.mean([g['cy'] for g in group])),
            'parts': len(group),
            'area': sum(g['a'] for g in group)
        })

    # Filter obvious noise: area < 10% of median letter area
    group_areas_sorted = sorted([g['area'] for g in groups], reverse=True)
    top_median = float(np.median(group_areas_sorted[:max(1, len(group_areas_sorted)//2)]))
    groups = [g for g in groups if g['area'] >= top_median * 0.10]

    # Sort into reading order (line by line, left to right)
    line_step = min(band_heights) / 2
    groups.sort(key=lambda g: (round(g['cy'] / line_step) * line_step, g['cx']))

    # Map to unique chars (take first min(N_groups, N_chars))
    n_map = min(len(groups), len(unique_chars))
    glyphs = {}
    for idx in range(n_map):
        g = groups[idx]
        ch = unique_chars[idx]
        pad = 6
        x1 = max(0, g['x'] - pad)
        y1_ = max(0, g['y'] - pad)
        x2 = min(W, g['x2'] + pad)
        y2_ = min(H, g['y2'] + pad)
        crop = binary[y1_:y2_, x1:x2]
        if crop.size > 0:
            glyphs[ch] = crop

    return glyphs


# ─────────────────────────────────────────────────────────────
# SEGMENTATION: GRID MODE
# ─────────────────────────────────────────────────────────────
def segment_grid(binary, H, W):
    rows_count = len(GRID_LAYOUT)
    cols_count = max(len(r) for r in GRID_LAYOUT)
    cH, cW = H // rows_count, W // cols_count
    glyphs = {}
    for ri, row in enumerate(GRID_LAYOUT):
        for ci, ch in enumerate(row):
            y1, y2 = ri*cH, min((ri+1)*cH, H)
            x1, x2 = ci*cW, min((ci+1)*cW, W)
            cell = binary[y1:y2, x1:x2]
            coords = cv2.findNonZero(cell)
            if coords is None:
                continue
            ink = np.sum(cell > 0) / cell.size
            if ink < 0.005 or ink > 0.95:
                continue
            bx, by, bw, bh = cv2.boundingRect(coords)
            pad = max(6, min(bw, bh) // 8)
            cx1 = max(0, bx-pad)
            cy1 = max(0, by-pad)
            cx2 = min(cell.shape[1], bx+bw+pad)
            cy2 = min(cell.shape[0], by+bh+pad)
            glyphs[ch] = cell[cy1:cy2, cx1:cx2]
    return glyphs


# ─────────────────────────────────────────────────────────────
# BUILD SVG (multi-glyph, for engine.py)
# ─────────────────────────────────────────────────────────────
def build_svg(glyph_dict, cell=620):
    chars = [c for c in glyph_dict if glyph_dict[c] is not None]
    if not chars:
        return None

    cols = min(6, len(chars))
    rows = (len(chars) + cols - 1) // cols
    W_svg, H_svg = cols * cell, rows * cell

    root = etree.Element('svg')
    root.set('xmlns', 'http://www.w3.org/2000/svg')
    root.set('width', str(W_svg))
    root.set('height', str(H_svg))
    root.set('viewBox', f'0 0 {W_svg} {H_svg}')

    built = 0
    for idx, ch in enumerate(chars):
        path_d, gw, gh = glyph_to_paths(glyph_dict[ch], target=int(cell * 0.82))
        if not path_d:
            continue
        col, row = idx % cols, idx // cols
        ox = col * cell + (cell - gw) // 2
        oy = row * cell + (cell - gh) // 2
        g = etree.SubElement(root, 'g')
        g.set('id', f'char_{ord(ch):04X}')
        g.set('transform', f'translate({ox},{oy})')
        pe = etree.SubElement(g, 'path')
        pe.set('d', path_d)
        pe.set('fill', '#000000')
        built += 1

    if built == 0:
        return None
    return etree.tostring(root, pretty_print=True,
                          xml_declaration=True, encoding='UTF-8').decode()


# ─────────────────────────────────────────────────────────────
# PREVIEW IMAGE
# ─────────────────────────────────────────────────────────────
def build_preview(glyph_dict):
    chars = [c for c in glyph_dict if glyph_dict[c] is not None]
    if not chars:
        return None

    cell = 96
    cols = min(13, len(chars))
    rows = (len(chars) + cols - 1) // cols
    canvas = np.full((rows * cell, cols * cell), 245, dtype=np.uint8)

    for idx, ch in enumerate(chars):
        g = glyph_dict[ch]
        if g is None:
            continue

        # Enhance before preview too
        if HAS_CV2:
            g = enhance_glyph(g)

        row, col = idx // cols, idx % cols
        y1, x1 = row*cell + 6, col*cell + 6
        y2, x2 = (row+1)*cell - 6, (col+1)*cell - 6
        cH, cW = y2 - y1, x2 - x1
        gh, gw = g.shape
        s = min(cH / max(gh, 1), cW / max(gw, 1))
        rh, rw = max(1, int(gh*s)), max(1, int(gw*s))

        if HAS_CV2:
            resized = cv2.resize(g, (rw, rh), interpolation=cv2.INTER_AREA)
        else:
            ri = Image.fromarray(g).resize((rw, rh), Image.LANCZOS)
            resized = np.array(ri)

        dy, dx = (cH - rh) // 2, (cW - rw) // 2
        py1, py2 = y1+dy, y1+dy+rh
        px1, px2 = x1+dx, x1+dx+rw
        inv = 255 - resized
        canvas[py1:py2, px1:px2] = np.minimum(canvas[py1:py2, px1:px2], inv)
        cv2.rectangle(canvas, (x1-1, y1-1), (x2+1, y2+1), 210, 1)

    buf = io.BytesIO()
    Image.fromarray(canvas).save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()


# ─────────────────────────────────────────────────────────────
# PILLOW FALLBACK PIPELINE
# ─────────────────────────────────────────────────────────────
def pil_preprocess(img_bytes):
    img = Image.open(io.BytesIO(img_bytes))
    try:
        from PIL import ExifTags
        exif = img._getexif()
        if exif:
            for tag, val in exif.items():
                if ExifTags.TAGS.get(tag) == 'Orientation':
                    if val == 3: img = img.rotate(180, expand=True)
                    elif val == 6: img = img.rotate(270, expand=True)
                    elif val == 8: img = img.rotate(90, expand=True)
                    break
    except Exception:
        pass
    w, h = img.size
    if max(w, h) > 2400:
        s = 2400 / max(w, h)
        img = img.resize((int(w*s), int(h*s)), Image.LANCZOS)
    gray = img.convert('L')
    gray = ImageEnhance.Contrast(gray).enhance(2.0)
    arr = np.array(gray)
    binary = (arr < 165).astype(np.uint8) * 255
    return binary, arr


def pil_segment_sentence(binary, expected_text):
    unique_chars = list(dict.fromkeys(c for c in expected_text if not c.isspace()))
    if not unique_chars:
        raise ValueError("No characters in expected text")
    H, W = binary.shape
    try:
        from scipy.ndimage import label
        labeled, n = label(binary > 127)
    except ImportError:
        raise ValueError("scipy not available — please install opencv-python-headless")

    min_a = H * W * 0.00008
    max_a = H * W * 0.12
    comps = []
    for i in range(1, n+1):
        mask = labeled == i
        area = mask.sum()
        if not (min_a <= area <= max_a): continue
        rows = np.where(mask.any(axis=1))[0]
        cols = np.where(mask.any(axis=0))[0]
        if len(rows) == 0: continue
        y1, y2 = rows[0], rows[-1]
        x1, x2 = cols[0], cols[-1]
        ch, cw = y2-y1, x2-x1
        if cw/max(ch,1) > 10 or ch/max(cw,1) > 10: continue
        comps.append({'i':i,'x':x1,'y':y1,'w':cw,'h':ch,'cx':(x1+x2)/2,'cy':(y1+y2)/2,'area':area})

    if not comps:
        raise ValueError("No ink detected.")

    comps.sort(key=lambda c: (round(c['cy']/100)*100, c['cx']))
    glyphs = {}
    for idx, char in enumerate(unique_chars):
        if idx >= len(comps): break
        c = comps[idx]
        pad = 8
        x1 = max(0, c['x']-pad); y1 = max(0, c['y']-pad)
        x2 = min(W, c['x']+c['w']+pad); y2 = min(H, c['y']+c['h']+pad)
        glyphs[char] = (labeled==c['i']).astype(np.uint8)[y1:y2,x1:x2]*255
    return glyphs


# ─────────────────────────────────────────────────────────────
# MAIN API
# ─────────────────────────────────────────────────────────────
def process_handwriting(img_bytes, mode='sentence', expected_text=None):
    """
    Returns dict: success, svg, preview, char_count, detected_chars, engine
    Or: success=False, error=str
    """
    try:
        print(f"[HW] Pipeline: {'OpenCV' if HAS_CV2 else 'Pillow'} | mode={mode}")

        if HAS_CV2:
            binary, gray = cv2_preprocess(img_bytes)
            H, W = binary.shape

            if mode == 'grid':
                glyphs = segment_grid(binary, H, W)
            else:
                text = expected_text or 'The quick brown fox'
                glyphs = segment_sentence(binary, gray, text, H, W)
        else:
            binary, gray = pil_preprocess(img_bytes)
            text = expected_text or 'The quick brown fox'
            glyphs = pil_segment_sentence(binary, text)

        if not glyphs:
            return {'success': False, 'error': 'No characters detected. Try pen instead of pencil, or better lighting.'}

        svg_str = build_svg(glyphs)
        if not svg_str:
            return {'success': False, 'error': 'Vectorization failed — letters may be too faint.'}

        preview = build_preview(glyphs)
        detected = [c for c in glyphs if isinstance(c, str)]

        print(f"[HW] Done: {len(glyphs)} glyphs, svg={len(svg_str)} chars")
        return {
            'success': True,
            'svg': svg_str,
            'preview': preview,
            'char_count': len(glyphs),
            'detected_chars': detected,
            'mode': mode,
            'engine': 'opencv' if HAS_CV2 else 'pillow',
        }

    except Exception as e:
        traceback.print_exc()
        return {'success': False, 'error': str(e)}


if __name__ == '__main__':
    print(f"handwriting_processor v4 | OpenCV: {HAS_CV2}")
