"""
Handwriting → Font Processor  v2
Fotoğraftaki el yazısını okur → karakterleri segmente eder → SVG + TTF üretir
"""
import cv2, numpy as np, os, base64, re
from lxml import etree

# ──────────────────────────────────────────────────────────────
# STEP 1: IMAGE PREPROCESSING
# ──────────────────────────────────────────────────────────────
def preprocess(img_bytes):
    """Raw bytes → clean binary (ink=255, bg=0)"""
    arr  = np.frombuffer(img_bytes, np.uint8)
    bgr  = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("Cannot decode image — try JPG or PNG")

    # Resize to max 2800px wide (keeps quality, speeds processing)
    h, w = bgr.shape[:2]
    if w > 2800:
        s = 2800 / w
        bgr = cv2.resize(bgr, (2800, int(h*s)), interpolation=cv2.INTER_LANCZOS4)

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # CLAHE – fixes uneven phone lighting
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    gray  = clahe.apply(gray)

    # Denoise
    gray = cv2.fastNlMeansDenoising(gray, h=12)

    # Adaptive threshold → white ink on black bg
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=31, C=10
    )

    # Close small gaps in strokes
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2,2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k)

    return binary

# ──────────────────────────────────────────────────────────────
# STEP 2: SENTENCE-MODE SEGMENTATION
# Writes "Hello World" → photo → tell us "Hello World"
# We detect blobs, sort left→right / top→bottom, map to unique chars
# ──────────────────────────────────────────────────────────────
def segment_sentence(binary, expected_text):
    """
    Detect connected components, sort into reading order,
    map to the unique characters in expected_text.
    Returns {char: cropped_glyph_binary}
    """
    # Get unique chars preserving order (skip spaces)
    unique_chars = list(dict.fromkeys(c for c in expected_text if not c.isspace()))
    if not unique_chars:
        raise ValueError("No characters in expected text")

    H, W = binary.shape
    n_lbl, labels, stats, cents = cv2.connectedComponentsWithStats(binary, connectivity=8)

    # Filter components by reasonable size
    min_area = H * W * 0.00008
    max_area = H * W * 0.12
    comps = []
    for i in range(1, n_lbl):
        a = stats[i, cv2.CC_STAT_AREA]
        if not (min_area <= a <= max_area): continue
        cw = stats[i, cv2.CC_STAT_WIDTH]
        ch = stats[i, cv2.CC_STAT_HEIGHT]
        if cw/max(ch,1) > 10 or ch/max(cw,1) > 10: continue  # too thin/flat = noise
        comps.append({
            'i': i,
            'x': stats[i, cv2.CC_STAT_LEFT],
            'y': stats[i, cv2.CC_STAT_TOP],
            'w': cw, 'h': ch,
            'cx': cents[i][0], 'cy': cents[i][1], 'area': a
        })

    if not comps:
        raise ValueError("No ink detected. Check lighting and contrast.")

    # Group into lines by Y-proximity
    comps_s = sorted(comps, key=lambda c: c['cy'])
    med_h   = float(np.median([c['h'] for c in comps_s]))
    thr     = med_h * 0.55
    lines   = [[comps_s[0]]]
    for c in comps_s[1:]:
        if abs(c['cy'] - np.mean([x['cy'] for x in lines[-1]])) < thr:
            lines[-1].append(c)
        else:
            lines.append([c])

    # Sort each line left→right, flatten
    ordered = []
    for ln in lines:
        ordered.extend(sorted(ln, key=lambda c: c['x']))

    # Map to unique chars (take first N blobs = N unique chars)
    glyphs = {}
    for idx, char in enumerate(unique_chars):
        if idx >= len(ordered): break
        comp = ordered[idx]
        pad = 8
        x1 = max(0, comp['x'] - pad)
        y1 = max(0, comp['y'] - pad)
        x2 = min(W, comp['x'] + comp['w'] + pad)
        y2 = min(H, comp['y'] + comp['h'] + pad)
        mask = ((labels == comp['i']).astype(np.uint8) * 255)
        glyphs[char] = mask[y1:y2, x1:x2]

    return glyphs

# ──────────────────────────────────────────────────────────────
# STEP 2b: GRID-MODE SEGMENTATION (template sheet)
# ──────────────────────────────────────────────────────────────
GRID_LAYOUT = [
    list('ABCDEF'), list('GHIJKL'), list('MNOPQR'), list('STUVWX'),
    list('YZabcd'), list('efghij'), list('klmnop'), list('qrstuv'),
    list('wxyz01'), list('234567'), list('89!?,.'),
]

def segment_grid(binary, layout=None):
    if layout is None:
        layout = GRID_LAYOUT
    rows = len(layout)
    cols = max(len(r) for r in layout)
    H, W = binary.shape
    cH, cW = H // rows, W // cols
    glyphs = {}
    for ri, row in enumerate(layout):
        for ci, ch in enumerate(row):
            y1, y2 = ri*cH, min((ri+1)*cH, H)
            x1, x2 = ci*cW, min((ci+1)*cW, W)
            cell = binary[y1:y2, x1:x2]
            coords = cv2.findNonZero(cell)
            if coords is None: continue
            ink = np.sum(cell > 0) / cell.size
            if ink < 0.005 or ink > 0.95: continue
            bx, by, bw, bh = cv2.boundingRect(coords)
            pad = max(6, min(bw,bh)//8)
            cx1 = max(0, bx-pad); cy1 = max(0, by-pad)
            cx2 = min(cell.shape[1], bx+bw+pad)
            cy2 = min(cell.shape[0], by+bh+pad)
            glyphs[ch] = cell[cy1:cy2, cx1:cx2]
    return glyphs

# ──────────────────────────────────────────────────────────────
# STEP 3: GLYPH → SVG PATH (vectorize)
# ──────────────────────────────────────────────────────────────
def glyph_to_paths(glyph_bin, target=520):
    """Binary glyph → SVG path string (smooth cubic bezier)"""
    if glyph_bin is None or glyph_bin.size == 0:
        return None, 0, 0

    h, w = glyph_bin.shape
    scale = max(target / max(w, h, 1), 1.0)
    nw, nh = int(w*scale), int(h*scale)
    up = cv2.resize(glyph_bin, (nw, nh), interpolation=cv2.INTER_CUBIC)
    _, up = cv2.threshold(up, 127, 255, cv2.THRESH_BINARY)

    # Slight smooth
    up = cv2.GaussianBlur(up, (3,3), 0)
    _, up = cv2.threshold(up, 127, 255, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(up, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_TC89_KCOS)
    if not contours:
        return None, nw, nh

    parts = []
    for cnt in contours:
        if len(cnt) < 3: continue
        eps = 0.006 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, eps, True).reshape(-1, 2)
        if len(approx) < 2: continue

        d = f"M {approx[0][0]:.1f} {approx[0][1]:.1f}"
        n = len(approx)
        for i in range(1, n):
            p0 = approx[max(0,i-2)]
            p1 = approx[i-1]
            p2 = approx[i]
            p3 = approx[min(n-1,i+1)]
            t = 0.28
            cp1x = p1[0] + t*(p2[0]-p0[0])/6
            cp1y = p1[1] + t*(p2[1]-p0[1])/6
            cp2x = p2[0] - t*(p3[0]-p1[0])/6
            cp2y = p2[1] - t*(p3[1]-p1[1])/6
            d += f" C {cp1x:.1f},{cp1y:.1f} {cp2x:.1f},{cp2y:.1f} {p2[0]:.1f},{p2[1]:.1f}"
        d += " Z"
        parts.append(d)

    return " ".join(parts) if parts else None, nw, nh

# ──────────────────────────────────────────────────────────────
# STEP 4: BUILD MULTI-GLYPH SVG (input to engine.py)
# ──────────────────────────────────────────────────────────────
def build_svg(glyph_dict, cell=620):
    chars = [c for c in glyph_dict if glyph_dict[c] is not None]
    if not chars:
        return None

    cols = min(6, len(chars))
    rows = (len(chars) + cols - 1) // cols
    W, H = cols * cell, rows * cell

    root = etree.Element('svg')
    root.set('xmlns', 'http://www.w3.org/2000/svg')
    root.set('width', str(W))
    root.set('height', str(H))
    root.set('viewBox', f'0 0 {W} {H}')

    for idx, ch in enumerate(chars):
        g_bin = glyph_dict[ch]
        path_d, gw, gh = glyph_to_paths(g_bin, target=int(cell*0.82))
        if not path_d: continue

        col = idx % cols
        row = idx // cols
        ox  = col * cell + (cell - gw) // 2
        oy  = row * cell + (cell - gh) // 2

        g = etree.SubElement(root, 'g')
        g.set('id', f'char_{ord(ch):04X}')
        g.set('transform', f'translate({ox},{oy})')
        pe = etree.SubElement(g, 'path')
        pe.set('d', path_d)
        pe.set('fill', '#000000')

    return etree.tostring(root, pretty_print=True,
                          xml_declaration=True, encoding='UTF-8').decode()

# ──────────────────────────────────────────────────────────────
# STEP 5: PREVIEW IMAGE (for UI)
# ──────────────────────────────────────────────────────────────
def build_preview(glyph_dict):
    chars = [c for c in glyph_dict if glyph_dict[c] is not None]
    if not chars: return None
    cell = 90
    cols = min(13, len(chars))
    rows = (len(chars) + cols - 1) // cols
    canvas = np.full((rows*cell, cols*cell), 245, dtype=np.uint8)

    for idx, ch in enumerate(chars):
        g = glyph_dict[ch]
        if g is None: continue
        row, col = idx//cols, idx%cols
        y1, x1 = row*cell+6, col*cell+6
        y2, x2 = (row+1)*cell-6, (col+1)*cell-6
        ch_h, cw_h = y2-y1, x2-x1
        gh, gw = g.shape
        s = min(ch_h/max(gh,1), cw_h/max(gw,1))
        rh, rw = max(1,int(gh*s)), max(1,int(gw*s))
        resized = cv2.resize(g, (rw, rh), interpolation=cv2.INTER_AREA)
        dy, dx = (ch_h-rh)//2, (cw_h-rw)//2
        py1, py2 = y1+dy, y1+dy+rh
        px1, px2 = x1+dx, x1+dx+rw
        inv = 255 - resized
        canvas[py1:py2, px1:px2] = np.minimum(canvas[py1:py2, px1:px2], inv)
        cv2.rectangle(canvas, (x1-6,y1-6), (x2+6,y2+6), 210, 1)

    _, buf = cv2.imencode('.png', canvas)
    return base64.b64encode(buf.tobytes()).decode()

# ──────────────────────────────────────────────────────────────
# MAIN API
# ──────────────────────────────────────────────────────────────
def process_handwriting(img_bytes, mode='sentence', expected_text=None):
    """
    Returns dict with keys: success, svg, preview, char_count, detected_chars
    Or: success=False, error=str
    """
    try:
        binary = preprocess(img_bytes)

        if mode == 'grid':
            glyphs = segment_grid(binary)
        else:
            if not expected_text:
                expected_text = "The quick brown fox"
            glyphs = segment_sentence(binary, expected_text)

        if not glyphs:
            return {'success': False, 'error': 'No characters detected. Try better lighting or higher contrast.'}

        svg_str  = build_svg(glyphs)
        preview  = build_preview(glyphs)
        detected = [c for c in glyphs if isinstance(c, str)]

        return {
            'success':        True,
            'svg':            svg_str or '',
            'preview':        preview,
            'char_count':     len(glyphs),
            'detected_chars': detected,
            'mode':           mode,
        }

    except Exception as e:
        import traceback; traceback.print_exc()
        return {'success': False, 'error': str(e)}

if __name__ == '__main__':
    print("handwriting_processor v2 — ready")
    print(f"Grid: {sum(len(r) for r in GRID_LAYOUT)} chars / {len(GRID_LAYOUT)} rows")
