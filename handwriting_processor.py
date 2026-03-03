"""
Handwriting → Font Processor
Fotoğraftaki el yazısını okur, karakterleri segmente eder, SVG'ye çevirir
"""
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import io, os, json, base64
from lxml import etree

# ─────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────
GRID_CHARS = [
    ['A','B','C','D','E','F'],
    ['G','H','I','J','K','L'],
    ['M','N','O','P','Q','R'],
    ['S','T','U','V','W','X'],
    ['Y','Z','a','b','c','d'],
    ['e','f','g','h','i','j'],
    ['k','l','m','n','o','p'],
    ['q','r','s','t','u','v'],
    ['w','x','y','z','0','1'],
    ['2','3','4','5','6','7'],
    ['8','9','!','?',',','.'],
]

SINGLE_LINE_CHARS = list('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789')

# ─────────────────────────────────────────
# IMAGE PREPROCESSING
# ─────────────────────────────────────────
def preprocess_image(img_bytes):
    """Raw image bytes → clean binary numpy array"""
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image")
    
    # Resize if too large (max 3000px wide)
    h, w = img.shape[:2]
    if w > 3000:
        scale = 3000 / w
        img = cv2.resize(img, (3000, int(h * scale)), interpolation=cv2.INTER_LANCZOS4)
    
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Deskew
    gray = deskew(gray)
    
    # Enhance contrast
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    gray = clahe.apply(gray)
    
    # Denoise
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    
    # Adaptive threshold — handles uneven lighting perfectly
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,  # black text on white → white text on black
        blockSize=25,
        C=8
    )
    
    # Morphological cleanup — connect broken strokes
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2,2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    
    return binary, img

def deskew(gray):
    """Detect and correct page tilt"""
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi/180, threshold=100)
    if lines is None:
        return gray
    
    angles = []
    for line in lines[:20]:
        rho, theta = line[0]
        angle = (theta - np.pi/2) * 180 / np.pi
        if abs(angle) < 15:  # only small corrections
            angles.append(angle)
    
    if not angles:
        return gray
    
    median_angle = np.median(angles)
    if abs(median_angle) < 0.5:
        return gray
    
    h, w = gray.shape
    center = (w//2, h//2)
    M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)

# ─────────────────────────────────────────
# GRID-BASED SEGMENTATION (template sheet)
# ─────────────────────────────────────────
def segment_grid(binary, grid_chars=None):
    """
    For template sheets where chars are in a known grid.
    Divides image into rows × cols cells and extracts each glyph.
    """
    if grid_chars is None:
        grid_chars = GRID_CHARS
    
    rows = len(grid_chars)
    cols = max(len(row) for row in grid_chars)
    
    h, w = binary.shape
    cell_h = h // rows
    cell_w = w // cols
    
    results = {}
    
    for row_idx, row in enumerate(grid_chars):
        for col_idx, char in enumerate(row):
            if not char:
                continue
            
            # Extract cell with padding
            y1 = row_idx * cell_h
            y2 = min((row_idx + 1) * cell_h, h)
            x1 = col_idx * cell_w
            x2 = min((col_idx + 1) * cell_w, w)
            
            cell = binary[y1:y2, x1:x2]
            glyph = extract_glyph_from_cell(cell)
            
            if glyph is not None:
                results[char] = glyph
    
    return results

def extract_glyph_from_cell(cell):
    """Extract tight bounding box of ink from a cell"""
    if cell is None or cell.size == 0:
        return None
    
    # Find ink pixels
    coords = cv2.findNonZero(cell)
    if coords is None:
        return None
    
    # Check if enough ink
    ink_ratio = np.sum(cell > 0) / cell.size
    if ink_ratio < 0.005 or ink_ratio > 0.95:
        return None
    
    # Tight crop
    x, y, w, h = cv2.boundingRect(coords)
    
    # Add padding
    pad = max(8, min(w, h) // 8)
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(cell.shape[1], x + w + pad)
    y2 = min(cell.shape[0], y + h + pad)
    
    cropped = cell[y1:y2, x1:x2]
    return cropped

# ─────────────────────────────────────────
# FREE-FORM SEGMENTATION (sentence/word photo)
# ─────────────────────────────────────────
def segment_freeform(binary, expected_chars=None):
    """
    For photos of written text — detect characters by connected components
    and line analysis. Returns dict of position→glyph.
    """
    # Find connected components
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )
    
    h, w = binary.shape
    min_area = (h * w) * 0.0001  # at least 0.01% of image
    max_area = (h * w) * 0.15    # at most 15% of image
    
    components = []
    for i in range(1, num_labels):  # skip background (0)
        area = stats[i, cv2.CC_STAT_AREA]
        if min_area <= area <= max_area:
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]
            cw = stats[i, cv2.CC_STAT_WIDTH]
            ch = stats[i, cv2.CC_STAT_HEIGHT]
            cx, cy = centroids[i]
            
            # Filter out noise (too thin or too flat)
            aspect = cw / max(ch, 1)
            if aspect > 8 or aspect < 0.08:
                continue
            
            components.append({
                'label': i, 'x': x, 'y': y, 'w': cw, 'h': ch,
                'cx': cx, 'cy': cy, 'area': area
            })
    
    if not components:
        return {}
    
    # Group into lines
    lines = group_into_lines(components, h)
    
    # Sort each line left to right
    results = {}
    char_idx = 0
    for line in lines:
        line_sorted = sorted(line, key=lambda c: c['x'])
        for comp in line_sorted:
            # Extract glyph
            pad = 4
            x1 = max(0, comp['x'] - pad)
            y1 = max(0, comp['y'] - pad)
            x2 = min(w, comp['x'] + comp['w'] + pad)
            y2 = min(h, comp['y'] + comp['h'] + pad)
            
            # Get the actual component pixels (not all ink in bbox)
            mask = (labels == comp['label']).astype(np.uint8) * 255
            glyph = mask[y1:y2, x1:x2]
            
            if expected_chars and char_idx < len(expected_chars):
                results[expected_chars[char_idx]] = glyph
            else:
                results[char_idx] = glyph
            char_idx += 1
    
    return results

def group_into_lines(components, img_height):
    """Group components into text lines using Y-coordinate clustering"""
    if not components:
        return []
    
    # Sort by Y
    sorted_comps = sorted(components, key=lambda c: c['cy'])
    
    # Estimate line height
    heights = [c['h'] for c in components]
    median_h = np.median(heights)
    line_threshold = median_h * 0.6
    
    lines = []
    current_line = [sorted_comps[0]]
    
    for comp in sorted_comps[1:]:
        # Check if same line as last component
        last_cy = np.mean([c['cy'] for c in current_line])
        if abs(comp['cy'] - last_cy) < line_threshold:
            current_line.append(comp)
        else:
            lines.append(current_line)
            current_line = [comp]
    
    lines.append(current_line)
    return lines

# ─────────────────────────────────────────
# GLYPH → SVG PATH CONVERSION
# ─────────────────────────────────────────
def glyph_to_svg_path(glyph_binary, target_size=500):
    """Convert binary glyph image to SVG path string"""
    if glyph_binary is None or glyph_binary.size == 0:
        return None, 0, 0
    
    h, w = glyph_binary.shape
    
    # Upscale for better path quality
    scale = max(target_size / max(w, h), 1.0)
    new_w = int(w * scale)
    new_h = int(h * scale)
    
    if scale > 1:
        upscaled = cv2.resize(glyph_binary, (new_w, new_h), 
                              interpolation=cv2.INTER_CUBIC)
        # Re-threshold after upscale
        _, upscaled = cv2.threshold(upscaled, 127, 255, cv2.THRESH_BINARY)
    else:
        upscaled = glyph_binary.copy()
        new_w, new_h = w, h
    
    # Smooth edges
    upscaled = cv2.GaussianBlur(upscaled, (3,3), 0)
    _, upscaled = cv2.threshold(upscaled, 127, 255, cv2.THRESH_BINARY)
    
    # Find contours
    contours, hierarchy = cv2.findContours(
        upscaled, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_TC89_KCOS
    )
    
    if not contours:
        return None, new_w, new_h
    
    path_parts = []
    
    for i, contour in enumerate(contours):
        if len(contour) < 3:
            continue
        
        # Simplify contour
        epsilon = 0.008 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        
        if len(approx) < 2:
            continue
        
        # Convert to SVG path
        pts = approx.reshape(-1, 2)
        
        # Start point
        path = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"
        
        # Use smooth curves (catmull-rom → cubic bezier)
        if len(pts) >= 4:
            path += smooth_path(pts)
        else:
            for pt in pts[1:]:
                path += f" L {pt[0]:.1f} {pt[1]:.1f}"
        
        path += " Z"
        path_parts.append(path)
    
    if not path_parts:
        return None, new_w, new_h
    
    return " ".join(path_parts), new_w, new_h

def smooth_path(pts):
    """Convert points to smooth cubic bezier path"""
    result = ""
    n = len(pts)
    
    for i in range(1, n):
        # Simple smooth curve using neighboring points as control points
        p0 = pts[max(0, i-2)]
        p1 = pts[i-1]
        p2 = pts[i]
        p3 = pts[min(n-1, i+1)]
        
        # Control points (Catmull-Rom → Bezier conversion)
        tension = 0.3
        cp1x = p1[0] + tension * (p2[0] - p0[0]) / 6
        cp1y = p1[1] + tension * (p2[1] - p0[1]) / 6
        cp2x = p2[0] - tension * (p3[0] - p1[0]) / 6
        cp2y = p2[1] - tension * (p3[1] - p1[1]) / 6
        
        result += f" C {cp1x:.1f} {cp1y:.1f} {cp2x:.1f} {cp2y:.1f} {p2[0]:.1f} {p2[1]:.1f}"
    
    return result

# ─────────────────────────────────────────
# BUILD MULTI-GLYPH SVG
# ─────────────────────────────────────────
def glyphs_to_svg(glyph_dict, canvas_size=600, glyphs_per_row=6):
    """Pack multiple glyphs into one SVG file for font building"""
    chars = list(glyph_dict.keys())
    
    if not chars:
        return None
    
    # Calculate grid
    n_chars = len(chars)
    n_cols = min(glyphs_per_row, n_chars)
    n_rows = (n_chars + n_cols - 1) // n_cols
    
    cell = canvas_size
    total_w = n_cols * cell
    total_h = n_rows * cell
    
    svg_root = etree.Element('svg')
    svg_root.set('xmlns', 'http://www.w3.org/2000/svg')
    svg_root.set('width', str(total_w))
    svg_root.set('height', str(total_h))
    svg_root.set('viewBox', f'0 0 {total_w} {total_h}')
    
    for idx, char in enumerate(chars):
        glyph = glyph_dict[char]
        if glyph is None:
            continue
        
        row = idx // n_cols
        col = idx % n_cols
        
        x_offset = col * cell
        y_offset = row * cell
        
        path_data, gw, gh = glyph_to_svg_path(glyph, target_size=int(cell * 0.8))
        
        if not path_data:
            continue
        
        # Center in cell
        cx = x_offset + (cell - gw) // 2
        cy = y_offset + (cell - gh) // 2
        
        # Flip Y (SVG top-down vs font bottom-up)
        cy_center = y_offset + cell // 2
        
        g = etree.SubElement(svg_root, 'g')
        g.set('id', f'char_{ord(char) if isinstance(char, str) else char}')
        g.set('transform', f'translate({cx},{cy})')
        
        path_el = etree.SubElement(g, 'path')
        path_el.set('d', path_data)
        path_el.set('fill', 'black')
    
    return etree.tostring(svg_root, pretty_print=True, xml_declaration=True, 
                          encoding='UTF-8').decode()

# ─────────────────────────────────────────
# PREVIEW GENERATION
# ─────────────────────────────────────────
def generate_preview_image(glyph_dict, max_chars=52):
    """Generate a preview PNG showing all detected glyphs"""
    chars = list(glyph_dict.keys())[:max_chars]
    if not chars:
        return None
    
    cell_size = 80
    cols = min(13, len(chars))
    rows = (len(chars) + cols - 1) // cols
    
    canvas = np.ones((rows * cell_size, cols * cell_size), dtype=np.uint8) * 240
    
    for idx, char in enumerate(chars):
        glyph = glyph_dict[char]
        if glyph is None:
            continue
        
        row = idx // cols
        col = idx % cols
        
        y1 = row * cell_size + 4
        y2 = (row + 1) * cell_size - 4
        x1 = col * cell_size + 4
        x2 = (col + 1) * cell_size - 4
        
        cell_h = y2 - y1
        cell_w = x2 - x1
        
        # Resize glyph to fit cell
        g_h, g_w = glyph.shape
        scale = min(cell_h / max(g_h, 1), cell_w / max(g_w, 1))
        new_h = max(1, int(g_h * scale))
        new_w = max(1, int(g_w * scale))
        
        resized = cv2.resize(glyph, (new_w, new_h), interpolation=cv2.INTER_AREA)
        
        # Center in cell
        dy = (cell_h - new_h) // 2
        dx = (cell_w - new_w) // 2
        
        py1, py2 = y1 + dy, y1 + dy + new_h
        px1, px2 = x1 + dx, x1 + dx + new_w
        
        # Invert (glyph is white-on-black, canvas is light)
        glyph_inv = 255 - resized
        canvas[py1:py2, px1:px2] = np.minimum(canvas[py1:py2, px1:px2], glyph_inv)
        
        # Draw cell border
        cv2.rectangle(canvas, (x1-4, y1-4), (x2+4, y2+4), 200, 1)
    
    # Convert to PNG bytes
    _, buf = cv2.imencode('.png', canvas)
    return base64.b64encode(buf.tobytes()).decode()

# ─────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────
def process_handwriting(img_bytes, mode='grid', expected_text=None, grid_chars=None):
    """
    Main function called from app.py
    
    mode: 'grid' = template sheet, 'freeform' = photo of text, 'sentence' = known text photo
    expected_text: for 'sentence' mode, the text written in the photo
    
    Returns: {
        'glyphs': dict of char→binary_glyph,
        'svg': SVG string,
        'preview': base64 PNG,
        'char_count': int,
        'detected_chars': list
    }
    """
    binary, original = preprocess_image(img_bytes)
    
    if mode == 'grid':
        chars_grid = grid_chars or GRID_CHARS
        glyph_dict = segment_grid(binary, chars_grid)
    
    elif mode == 'sentence' and expected_text:
        # User tells us what's written → segment and map
        clean_text = expected_text.replace(' ', '')
        expected_chars = list(dict.fromkeys(clean_text))  # unique, preserve order
        glyph_dict = segment_freeform(binary, expected_chars)
    
    else:  # freeform
        glyph_dict = segment_freeform(binary, None)
    
    if not glyph_dict:
        return {'error': 'No characters detected. Try better lighting or a clearer photo.'}
    
    svg_content = glyphs_to_svg(glyph_dict)
    preview_b64 = generate_preview_image(glyph_dict)
    
    detected = [str(c) for c in glyph_dict.keys() if isinstance(c, str)]
    
    return {
        'glyphs': {str(k): True for k in glyph_dict.keys()},
        'svg': svg_content,
        'preview': preview_b64,
        'char_count': len(glyph_dict),
        'detected_chars': detected,
        'mode': mode
    }

if __name__ == '__main__':
    print("Handwriting processor ready")
    print(f"Grid template: {sum(len(r) for r in GRID_CHARS)} chars across {len(GRID_CHARS)} rows")
