"""
Handwriting → Font Processor  v3
cv2 varsa OpenCV pipeline, yoksa Pillow fallback
"""
import os, base64, traceback

# ── Try importing cv2, fall back to Pillow-only ──────────────
try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    import numpy as np  # numpy is always available (fonttools dep)

from PIL import Image, ImageFilter, ImageEnhance, ImageOps
import io

# ─────────────────────────────────────────────────────────────
# GRID LAYOUT (for template sheet mode)
# ─────────────────────────────────────────────────────────────
GRID_LAYOUT = [
    list('ABCDEF'), list('GHIJKL'), list('MNOPQR'), list('STUVWX'),
    list('YZabcd'), list('efghij'), list('klmnop'), list('qrstuv'),
    list('wxyz01'), list('234567'), list('89!?,.'),
]

# ─────────────────────────────────────────────────────────────
# PILLOW-ONLY PIPELINE (fallback when cv2 not available)
# ─────────────────────────────────────────────────────────────
def pil_preprocess(img_bytes):
    """Pillow-based preprocessing — works without cv2"""
    img = Image.open(io.BytesIO(img_bytes))

    # Handle EXIF rotation
    try:
        from PIL import ExifTags
        exif = img._getexif()
        if exif:
            for tag, val in exif.items():
                if ExifTags.TAGS.get(tag) == 'Orientation':
                    if val == 3:   img = img.rotate(180, expand=True)
                    elif val == 6: img = img.rotate(270, expand=True)
                    elif val == 8: img = img.rotate(90,  expand=True)
                    break
    except Exception:
        pass

    # Resize max 2400px
    w, h = img.size
    if max(w, h) > 2400:
        s = 2400 / max(w, h)
        img = img.resize((int(w*s), int(h*s)), Image.LANCZOS)

    # Grayscale
    gray = img.convert('L')

    # Enhance contrast
    gray = ImageEnhance.Contrast(gray).enhance(2.2)
    gray = ImageEnhance.Sharpness(gray).enhance(2.0)

    # Convert to numpy for processing
    arr = np.array(gray)

    # Adaptive threshold (simple block-based)
    binary = adaptive_threshold_pil(arr)
    return binary, arr

def adaptive_threshold_pil(gray_arr):
    """Simple adaptive threshold without cv2"""
    h, w = gray_arr.shape
    block = 32
    binary = np.zeros((h, w), dtype=np.uint8)

    for y in range(0, h, block):
        for x in range(0, w, block):
            patch = gray_arr[y:y+block, x:x+block]
            if patch.size == 0: continue
            mean_val = float(patch.mean())
            thresh = mean_val * 0.82
            local = (gray_arr[y:y+block, x:x+block] < thresh).astype(np.uint8) * 255
            binary[y:y+block, x:x+block] = local

    return binary

def pil_segment_sentence(binary, expected_text):
    """Segment characters using numpy (no cv2)"""
    unique_chars = list(dict.fromkeys(c for c in expected_text if not c.isspace()))
    if not unique_chars:
        raise ValueError("No characters in expected text")

    H, W = binary.shape

    # Find connected components via labeling
    from scipy import ndimage
    labeled, n_features = ndimage.label(binary > 127)

    min_area = H * W * 0.00008
    max_area = H * W * 0.12

    comps = []
    for i in range(1, n_features + 1):
        mask = (labeled == i)
        area = mask.sum()
        if not (min_area <= area <= max_area): continue
        rows = np.where(mask.any(axis=1))[0]
        cols = np.where(mask.any(axis=0))[0]
        if len(rows) == 0 or len(cols) == 0: continue
        y1, y2 = rows[0], rows[-1]
        x1, x2 = cols[0], cols[-1]
        ch, cw = y2-y1, x2-x1
        if cw/max(ch,1) > 10 or ch/max(cw,1) > 10: continue
        comps.append({'i':i,'x':x1,'y':y1,'w':cw,'h':ch,
                      'cx':(x1+x2)/2,'cy':(y1+y2)/2,'area':area})

    if not comps:
        raise ValueError("No ink detected. Try better lighting and darker pen.")

    # Group into lines
    comps_s = sorted(comps, key=lambda c: c['cy'])
    med_h = float(np.median([c['h'] for c in comps_s]))
    thr = med_h * 0.55
    lines = [[comps_s[0]]]
    for c in comps_s[1:]:
        line_cy = np.mean([x['cy'] for x in lines[-1]])
        if abs(c['cy'] - line_cy) < thr:
            lines[-1].append(c)
        else:
            lines.append([c])

    ordered = []
    for ln in lines:
        ordered.extend(sorted(ln, key=lambda c: c['x']))

    glyphs = {}
    for idx, char in enumerate(unique_chars):
        if idx >= len(ordered): break
        comp = ordered[idx]
        pad = 8
        x1 = max(0, comp['x'] - pad)
        y1 = max(0, comp['y'] - pad)
        x2 = min(W, comp['x'] + comp['w'] + pad)
        y2 = min(H, comp['y'] + comp['h'] + pad)
        glyphs[char] = (labeled == comp['i']).astype(np.uint8)[y1:y2, x1:x2] * 255

    return glyphs

# ─────────────────────────────────────────────────────────────
# OPENCV PIPELINE (preferred when available)
# ─────────────────────────────────────────────────────────────
def cv2_preprocess(img_bytes):
    arr = np.frombuffer(img_bytes, np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("Cannot decode image")

    h, w = bgr.shape[:2]
    if w > 2800:
        s = 2800/w
        bgr = cv2.resize(bgr,(2800,int(h*s)),interpolation=cv2.INTER_LANCZOS4)

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    gray = clahe.apply(gray)
    gray = cv2.fastNlMeansDenoising(gray, h=12)
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=31, C=10
    )
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(2,2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k)
    return binary

def cv2_segment_sentence(binary, expected_text):
    unique_chars = list(dict.fromkeys(c for c in expected_text if not c.isspace()))
    if not unique_chars:
        raise ValueError("No characters in expected text")

    H, W = binary.shape
    n_lbl, labels, stats, cents = cv2.connectedComponentsWithStats(binary, connectivity=8)
    min_area = H*W*0.00008
    max_area = H*W*0.12

    comps = []
    for i in range(1, n_lbl):
        a = stats[i, cv2.CC_STAT_AREA]
        if not (min_area <= a <= max_area): continue
        cw = stats[i, cv2.CC_STAT_WIDTH]
        ch = stats[i, cv2.CC_STAT_HEIGHT]
        if cw/max(ch,1) > 10 or ch/max(cw,1) > 10: continue
        comps.append({'i':i,
            'x':stats[i,cv2.CC_STAT_LEFT],'y':stats[i,cv2.CC_STAT_TOP],
            'w':cw,'h':ch,'cx':cents[i][0],'cy':cents[i][1],'area':a})

    if not comps:
        raise ValueError("No ink detected. Try better lighting and darker pen.")

    comps_s = sorted(comps, key=lambda c: c['cy'])
    med_h = float(np.median([c['h'] for c in comps_s]))
    thr = med_h * 0.55
    lines = [[comps_s[0]]]
    for c in comps_s[1:]:
        if abs(c['cy'] - np.mean([x['cy'] for x in lines[-1]])) < thr:
            lines[-1].append(c)
        else:
            lines.append([c])

    ordered = []
    for ln in lines:
        ordered.extend(sorted(ln, key=lambda c: c['x']))

    glyphs = {}
    for idx, char in enumerate(unique_chars):
        if idx >= len(ordered): break
        comp = ordered[idx]
        pad = 8
        x1=max(0,comp['x']-pad); y1=max(0,comp['y']-pad)
        x2=min(W,comp['x']+comp['w']+pad); y2=min(H,comp['y']+comp['h']+pad)
        mask = (labels==comp['i']).astype(np.uint8)*255
        glyphs[char] = mask[y1:y2,x1:x2]

    return glyphs

def cv2_segment_grid(binary):
    rows, cols = len(GRID_LAYOUT), max(len(r) for r in GRID_LAYOUT)
    H, W = binary.shape
    cH, cW = H//rows, W//cols
    glyphs = {}
    for ri, row in enumerate(GRID_LAYOUT):
        for ci, ch in enumerate(row):
            y1,y2 = ri*cH, min((ri+1)*cH,H)
            x1,x2 = ci*cW, min((ci+1)*cW,W)
            cell = binary[y1:y2,x1:x2]
            coords = cv2.findNonZero(cell)
            if coords is None: continue
            ink = np.sum(cell>0)/cell.size
            if ink < 0.005 or ink > 0.95: continue
            bx,by,bw,bh = cv2.boundingRect(coords)
            pad = max(6,min(bw,bh)//8)
            cx1=max(0,bx-pad); cy1=max(0,by-pad)
            cx2=min(cell.shape[1],bx+bw+pad); cy2=min(cell.shape[0],by+bh+pad)
            glyphs[ch] = cell[cy1:cy2,cx1:cx2]
    return glyphs

# ─────────────────────────────────────────────────────────────
# GLYPH → SVG PATH  (works with either pipeline)
# ─────────────────────────────────────────────────────────────
def glyph_to_paths(glyph_bin, target=520):
    if glyph_bin is None or glyph_bin.size == 0:
        return None, 0, 0
    h, w = glyph_bin.shape

    if HAS_CV2:
        scale = max(target/max(w,h,1), 1.0)
        nw, nh = int(w*scale), int(h*scale)
        up = cv2.resize(glyph_bin,(nw,nh),interpolation=cv2.INTER_CUBIC)
        _,up = cv2.threshold(up,127,255,cv2.THRESH_BINARY)
        up = cv2.GaussianBlur(up,(3,3),0)
        _,up = cv2.threshold(up,127,255,cv2.THRESH_BINARY)
        contours,_ = cv2.findContours(up,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_TC89_KCOS)
        if not contours: return None,nw,nh
        parts=[]
        for cnt in contours:
            if len(cnt)<3: continue
            eps=0.006*cv2.arcLength(cnt,True)
            approx=cv2.approxPolyDP(cnt,eps,True).reshape(-1,2)
            if len(approx)<2: continue
            d=f"M {approx[0][0]:.1f} {approx[0][1]:.1f}"
            n2=len(approx)
            for i in range(1,n2):
                p0=approx[max(0,i-2)]; p1=approx[i-1]
                p2=approx[i]; p3=approx[min(n2-1,i+1)]
                t=0.28
                cp1x=p1[0]+t*(p2[0]-p0[0])/6; cp1y=p1[1]+t*(p2[1]-p0[1])/6
                cp2x=p2[0]-t*(p3[0]-p1[0])/6; cp2y=p2[1]-t*(p3[1]-p1[1])/6
                d+=f" C {cp1x:.1f},{cp1y:.1f} {cp2x:.1f},{cp2y:.1f} {p2[0]:.1f},{p2[1]:.1f}"
            d+=" Z"
            parts.append(d)
        return (" ".join(parts) if parts else None), nw, nh
    else:
        # Pillow-based contour tracing (simplified marching squares)
        return pil_glyph_to_paths(glyph_bin, target)

def pil_glyph_to_paths(glyph_bin, target=520):
    """Pillow-based path extraction without cv2"""
    h, w = glyph_bin.shape
    scale = max(target/max(w,h,1), 1.0)
    nw, nh = int(w*scale), int(h*scale)

    img = Image.fromarray(glyph_bin).resize((nw,nh), Image.LANCZOS)
    arr = np.array(img)
    _, arr = (arr > 127).astype(np.uint8), arr
    arr = (arr > 127).astype(np.uint8)

    # Simple contour: find boundary pixels
    # Pad image
    padded = np.pad(arr, 1, mode='constant')
    # Boundary = pixels that are 1 but have at least one 0 neighbor
    from scipy.ndimage import binary_erosion
    eroded = binary_erosion(padded)
    boundary = padded & ~eroded
    boundary = boundary[1:-1, 1:-1]

    # Get boundary pixel coordinates
    ys, xs = np.where(boundary)
    if len(xs) < 3:
        return None, nw, nh

    # Build rough polygon from boundary points (convex hull approach)
    pts = list(zip(xs.tolist(), ys.tolist()))

    # Reduce points (take every Nth)
    step = max(1, len(pts)//80)
    pts = pts[::step]

    if len(pts) < 3:
        return None, nw, nh

    # Build path
    d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"
    for px, py in pts[1:]:
        d += f" L {px:.1f} {py:.1f}"
    d += " Z"

    return d, nw, nh

# ─────────────────────────────────────────────────────────────
# BUILD SVG
# ─────────────────────────────────────────────────────────────
def build_svg(glyph_dict, cell=620):
    chars = [c for c in glyph_dict if glyph_dict[c] is not None]
    if not chars: return None

    cols = min(6, len(chars))
    rows = (len(chars)+cols-1)//cols
    W, H = cols*cell, rows*cell

    from lxml import etree
    root = etree.Element('svg')
    root.set('xmlns','http://www.w3.org/2000/svg')
    root.set('width',str(W)); root.set('height',str(H))
    root.set('viewBox',f'0 0 {W} {H}')

    for idx, ch in enumerate(chars):
        path_d, gw, gh = glyph_to_paths(glyph_dict[ch], target=int(cell*0.82))
        if not path_d: continue
        col, row = idx%cols, idx//cols
        ox = col*cell+(cell-gw)//2
        oy = row*cell+(cell-gh)//2
        g = etree.SubElement(root,'g')
        g.set('id',f'char_{ord(ch):04X}')
        g.set('transform',f'translate({ox},{oy})')
        pe = etree.SubElement(g,'path')
        pe.set('d',path_d); pe.set('fill','#000000')

    return etree.tostring(root,pretty_print=True,
                          xml_declaration=True,encoding='UTF-8').decode()

# ─────────────────────────────────────────────────────────────
# PREVIEW IMAGE
# ─────────────────────────────────────────────────────────────
def build_preview(glyph_dict):
    chars = [c for c in glyph_dict if glyph_dict[c] is not None]
    if not chars: return None
    cell=88; cols=min(13,len(chars)); rows=(len(chars)+cols-1)//cols
    canvas = np.full((rows*cell,cols*cell),245,dtype=np.uint8)

    for idx,ch in enumerate(chars):
        g=glyph_dict[ch]
        if g is None: continue
        row,col=idx//cols,idx%cols
        y1,x1=row*cell+5,col*cell+5
        y2,x2=(row+1)*cell-5,(col+1)*cell-5
        cH,cW=y2-y1,x2-x1
        gh,gw=g.shape
        s=min(cH/max(gh,1),cW/max(gw,1))
        rh,rw=max(1,int(gh*s)),max(1,int(gw*s))

        if HAS_CV2:
            resized=cv2.resize(g,(rw,rh),interpolation=cv2.INTER_AREA)
        else:
            ri=Image.fromarray(g).resize((rw,rh),Image.LANCZOS)
            resized=np.array(ri)

        dy,dx=(cH-rh)//2,(cW-rw)//2
        py1,py2=y1+dy,y1+dy+rh
        px1,px2=x1+dx,x1+dx+rw
        inv=255-resized
        canvas[py1:py2,px1:px2]=np.minimum(canvas[py1:py2,px1:px2],inv)

    # Encode PNG
    img=Image.fromarray(canvas)
    buf=io.BytesIO(); img.save(buf,format='PNG'); buf.seek(0)
    return base64.b64encode(buf.read()).decode()

# ─────────────────────────────────────────────────────────────
# MAIN API
# ─────────────────────────────────────────────────────────────
def process_handwriting(img_bytes, mode='sentence', expected_text=None):
    try:
        print(f"[HW] Using {'OpenCV' if HAS_CV2 else 'Pillow'} pipeline, mode={mode}")

        # Preprocess
        if HAS_CV2:
            binary = cv2_preprocess(img_bytes)
        else:
            binary, _ = pil_preprocess(img_bytes)

        # Segment
        if mode == 'grid':
            if HAS_CV2:
                glyphs = cv2_segment_grid(binary)
            else:
                glyphs = pil_segment_grid(binary)
        else:
            text = expected_text or 'The quick brown fox'
            if HAS_CV2:
                glyphs = cv2_segment_sentence(binary, text)
            else:
                glyphs = pil_segment_sentence(binary, text)

        if not glyphs:
            return {'success':False,'error':'No characters detected. Try better lighting or darker pen.'}

        svg_str  = build_svg(glyphs)
        preview  = build_preview(glyphs)
        detected = [c for c in glyphs if isinstance(c,str)]

        return {
            'success':True,
            'svg': svg_str or '',
            'preview': preview,
            'char_count': len(glyphs),
            'detected_chars': detected,
            'mode': mode,
            'engine': 'opencv' if HAS_CV2 else 'pillow',
        }

    except Exception as e:
        traceback.print_exc()
        return {'success':False,'error':str(e)}

def pil_segment_grid(binary):
    """Grid segmentation without cv2"""
    rows_count = len(GRID_LAYOUT)
    cols_count = max(len(r) for r in GRID_LAYOUT)
    H, W = binary.shape
    cH, cW = H//rows_count, W//cols_count
    glyphs = {}
    for ri, row in enumerate(GRID_LAYOUT):
        for ci, ch in enumerate(row):
            y1,y2 = ri*cH, min((ri+1)*cH,H)
            x1,x2 = ci*cW, min((ci+1)*cW,W)
            cell = binary[y1:y2,x1:x2]
            ink = np.sum(cell>127)/max(cell.size,1)
            if ink < 0.005 or ink > 0.95: continue
            rows_ink = np.where(cell.any(axis=1))[0]
            cols_ink = np.where(cell.any(axis=0))[0]
            if len(rows_ink)==0 or len(cols_ink)==0: continue
            pad=6
            ry1=max(0,rows_ink[0]-pad); ry2=min(cell.shape[0],rows_ink[-1]+pad)
            cx1=max(0,cols_ink[0]-pad); cx2=min(cell.shape[1],cols_ink[-1]+pad)
            glyphs[ch] = cell[ry1:ry2,cx1:cx2]
    return glyphs

if __name__ == '__main__':
    print(f"handwriting_processor v3")
    print(f"OpenCV available: {HAS_CV2}")
    try:
        from scipy import ndimage
        print("scipy available: True")
    except ImportError:
        print("scipy available: False (Pillow fallback will be limited)")
