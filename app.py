#!/usr/bin/env python3
"""
VectoFont - SVG to Font Converter
Multi-user, auto-cleanup, production ready
"""

import os, sys, json, re, uuid, time, threading, shutil, traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import build_font, DEFAULT_CHAR_ORDER

# ── Storage ───────────────────────────────────────────────────────────────────
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sessions')
os.makedirs(BASE_DIR, exist_ok=True)

SESSION_TTL = 3600  # 1 saat sonra sil

def new_session():
    sid = uuid.uuid4().hex
    path = os.path.join(BASE_DIR, sid)
    os.makedirs(path, exist_ok=True)
    # Oluşturma zamanını kaydet
    with open(os.path.join(path, '.created'), 'w') as f:
        f.write(str(time.time()))
    return sid, path

def session_path(sid):
    p = os.path.join(BASE_DIR, sid)
    return p if os.path.isdir(p) else None

def cleanup_old_sessions():
    """Eski session'ları temizle — her 10 dakikada çalışır"""
    while True:
        time.sleep(600)
        try:
            now = time.time()
            for sid in os.listdir(BASE_DIR):
                p = os.path.join(BASE_DIR, sid)
                created_file = os.path.join(p, '.created')
                try:
                    with open(created_file) as f:
                        created = float(f.read())
                    if now - created > SESSION_TTL:
                        shutil.rmtree(p, ignore_errors=True)
                        print(f"[CLEANUP] Session {sid[:8]}... silindi")
                except:
                    pass
        except:
            pass

# Cleanup thread'i başlat
t = threading.Thread(target=cleanup_old_sessions, daemon=True)
t.start()

# ── Multipart parser ──────────────────────────────────────────────────────────
def parse_multipart(data, content_type):
    m = re.search(r'boundary=([^\s;]+)', content_type)
    if not m:
        return {}, {}
    boundary = m.group(1).strip('"\'')
    fields, files = {}, {}
    sep = ('--' + boundary).encode()
    parts = data.split(sep)
    for part in parts[1:]:
        if part.strip() in (b'', b'--', b'--\r\n', b'\r\n--'):
            continue
        if b'\r\n\r\n' in part:
            header_bytes, body = part.split(b'\r\n\r\n', 1)
        elif b'\n\n' in part:
            header_bytes, body = part.split(b'\n\n', 1)
        else:
            continue
        body = body.rstrip(b'\r\n-')
        header_str = header_bytes.decode('utf-8', errors='ignore')
        name_m = re.search(r'name="([^"]+)"', header_str)
        filename_m = re.search(r'filename="([^"]+)"', header_str)
        if not name_m:
            continue
        name = name_m.group(1)
        if filename_m:
            files[name] = {'filename': filename_m.group(1), 'data': body}
        else:
            fields[name] = body.decode('utf-8', errors='ignore').strip()
    return fields, files

# ── Request Handler ───────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}")

    def send_cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors()
        self.end_headers()

    def json_resp(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.send_cors()
        self.end_headers()
        self.wfile.write(body)

    def handle_handwriting_process(self):
        """Handwriting image → glyph preview + session SVG"""
        try:
            fields, files = self.read_body()
            print(f"[HW-PROCESS] fields={list(fields.keys())} files={list(files.keys())}")

            if 'image' not in files:
                self.json_resp({'success': False, 'error': 'No image uploaded — check form field name'}, 400)
                return

            img_data = files['image'].get('data', b'')
            if len(img_data) < 100:
                self.json_resp({'success': False, 'error': f'Image too small ({len(img_data)} bytes) — upload failed'}, 400)
                return

            mode          = fields.get('mode', 'sentence')
            expected_text = fields.get('expected_text', '').strip()
            print(f"[HW-PROCESS] img={len(img_data)} bytes mode={mode} text='{expected_text[:60]}'")

            # Import processor (it's in same directory, sys.path already set)
            try:
                from handwriting_processor import process_handwriting
            except ImportError as ie:
                self.json_resp({'success': False, 'error': f'Processor module error: {ie}'}, 500)
                return

            result = process_handwriting(img_data, mode=mode,
                                         expected_text=expected_text or None)

            if not result.get('success'):
                self.json_resp({'success': False,
                                'error': result.get('error', 'Character detection failed')})
                return

            # Save SVG to temp session
            sid     = os.urandom(8).hex()
            tmp_dir = f'/tmp/hw_{sid}'
            os.makedirs(tmp_dir, exist_ok=True)
            svg_path = os.path.join(tmp_dir, 'handwriting.svg')
            svg_content = result.get('svg', '')
            if not svg_content:
                self.json_resp({'success': False, 'error': 'SVG generation returned empty — no glyphs built'})
                return

            with open(svg_path, 'w', encoding='utf-8') as svgf:
                svgf.write(svg_content)

            print(f"[HW-PROCESS] OK sid={sid[:8]} chars={result.get('char_count')} svg={len(svg_content)}")
            self.json_resp({
                'success':        True,
                'preview':        result.get('preview'),
                'char_count':     result.get('char_count', 0),
                'detected_chars': result.get('detected_chars', []),
                'session_id':     sid,
                'mode':           mode,
            })

        except Exception as e:
            print(f"[HW-PROCESS ERROR] {e}\n{traceback.format_exc()}")
            self.json_resp({'success': False, 'error': f'Server error: {str(e)}'}, 500)

    def handle_handwriting_to_font(self):
        """Session SVG → TTF + OTF download"""
        try:
            length = int(self.headers.get('Content-Length', 0))
            body   = self.rfile.read(length)
            data   = json.loads(body.decode('utf-8'))

            session_id = data.get('session_id', '')
            font_name  = (data.get('font_name') or 'MyHandwriting').strip()
            exp_text   = data.get('expected_text', '')

            svg_path = f'/tmp/hw_{session_id}/handwriting.svg'
            if not os.path.exists(svg_path):
                self.json_resp({'success': False,
                                'error': 'Session expired — please upload again'})
                return

            from engine import build_font, DEFAULT_CHAR_ORDER
            import shutil

            out_dir = f'/tmp/hw_{session_id}/output'
            os.makedirs(out_dir, exist_ok=True)

            if exp_text:
                chars      = list(dict.fromkeys(c for c in exp_text if c.strip()))
                char_order = chars + [c for c in DEFAULT_CHAR_ORDER if c not in chars]
            else:
                char_order = list(DEFAULT_CHAR_ORDER)

            print(f"[HW→FONT] '{font_name}' chars={char_order[:12]}")
            ttf_path, otf_path = build_font(svg_path, font_name, out_dir,
                                             char_order=char_order)

            if not ttf_path:
                self.json_resp({'success': False, 'error': 'Font generation failed'})
                return

            result_files = []
            for fp in [ttf_path, otf_path]:
                if fp and os.path.exists(fp):
                    sid2, sp2 = new_session()
                    out2 = os.path.join(sp2, 'output')
                    os.makedirs(out2, exist_ok=True)
                    dest = os.path.join(out2, os.path.basename(fp))
                    shutil.copy2(fp, dest)
                    result_files.append({
                        'filename': os.path.basename(fp),
                        'size':     os.path.getsize(fp),
                        'url':      f'/download/{sid2}/{os.path.basename(fp)}'
                    })

            self.json_resp({'success': True, 'files': result_files, 'font_name': font_name})

        except Exception as e:
            print(f"[HW→FONT ERROR] {e}\n{traceback.format_exc()}")
            self.json_resp({'success': False, 'error': str(e)}, 500)

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ('/', '/index.html'):
            self.serve_static('index.html', 'text/html')

        elif path == '/fonts':
            self.serve_static('fonts.html', 'text/html')

        elif path == '/find-font':
            self.serve_static('find-font.html', 'text/html')

        elif path == '/about':
            self.serve_static('about.html', 'text/html')

        elif path == '/pairing':
            self.serve_static('pairing.html', 'text/html')

        elif path == '/preview':
            self.serve_static('preview.html', 'text/html')

        elif path == '/blog':
            self.serve_static('blog.html', 'text/html')

        elif path == '/brands':
            self.serve_static('brands.html', 'text/html')

        elif path == '/css-stack':
            self.serve_static('css-stack.html', 'text/html')

        elif path == '/license-checker':
            self.serve_static('license-checker.html', 'text/html')

        elif path == '/font-size':
            self.serve_static('font-size.html', 'text/html')

        elif path == '/variable-fonts':
            self.serve_static('variable-fonts.html', 'text/html')

        elif path == '/font-twin':
            self.serve_static('font-twin.html', 'text/html')

        elif path == '/moodboard':
            self.serve_static('moodboard.html', 'text/html')

        elif path == '/font-quiz':
            self.serve_static('font-quiz.html', 'text/html')

        elif path == '/css-animation':
            self.serve_static('css-animation.html', 'text/html')
        elif path == '/tools':
            self.serve_static('tools.html', 'text/html')
        elif path == '/type-scale':
            self.serve_static('type-scale.html', 'text/html')
        elif path == '/contrast-checker':
            self.serve_static('contrast-checker.html', 'text/html')
        elif path == '/color-palette':
            self.serve_static('color-palette.html', 'text/html')
        elif path == '/font-name-generator':
            self.serve_static('font-name-generator.html', 'text/html')
        elif path == '/font-mood':
            self.serve_static('font-mood.html', 'text/html')
        elif path == '/readability-checker':
            self.serve_static('readability-checker.html', 'text/html')
        elif path == '/handwriting-font':
            self.serve_static('handwriting-font.html', 'text/html')

        elif path == '/sitemap.xml':
            self.serve_static('sitemap.xml', 'application/xml')

        elif path == '/favicon.ico':
            self.serve_static('favicon.ico', 'image/x-icon')
        elif path == '/favicon.svg':
            self.serve_static('favicon.svg', 'image/svg+xml')
        elif path == '/favicon-32.png':
            self.serve_static('favicon-32.png', 'image/png')
        elif path == '/robots.txt':
            self.serve_static('robots.txt', 'text/plain')

        elif path == '/privacy':
            self.serve_static('privacy.html', 'text/html')

        elif path == '/terms':
            self.serve_static('terms.html', 'text/html')

        elif path == '/api/fonts':
            self.handle_fonts_api()

        elif path.startswith('/download/'):
            # /download/{session_id}/{filename}
            parts = path[10:].split('/', 1)
            if len(parts) == 2:
                sid, filename = parts
                filename = os.path.basename(filename)
                sp = session_path(sid)
                if sp:
                    filepath = os.path.join(sp, 'output', filename)
                    if os.path.exists(filepath):
                        self.serve_file(filepath)
                        return
            self.send_error(404)
        else:
            self.send_error(404)

    def handle_fonts_api(self):
        """Font listesini döndür — önce embedded DB, sonra Google API bonus"""
        import urllib.request, json as _json
        GKEY = 'AIzaSyAkLMad9aRgv6wEAyYhe4xUrzHlyfvJu_o'

        # Embedded font database — her zaman çalışır
        try:
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'font_db.py')
            import importlib.util
            spec = importlib.util.spec_from_file_location('font_db', db_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            fonts = mod.get_all_fonts()
        except Exception as e:
            print(f'[FONT DB ERROR] {e}')
            fonts = []

        # Google API'den ek fontlar çekmeyi dene (bonus)
        try:
            url = f'https://www.googleapis.com/webfonts/v1/webfonts?key={GKEY}&sort=popularity'
            req = urllib.request.Request(url, headers={'User-Agent': 'Vectrod/1.0'})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = _json.loads(r.read())
            existing = {f['family'] for f in fonts}
            for i, f in enumerate(data.get('items', [])):
                if f['family'] not in existing:
                    fonts.append({
                        'family': f['family'],
                        'category': f['category'],
                        'source': 'google',
                        'files': f.get('files', {}),
                        'pop': i + 1000
                    })
            print(f'[FONTS API] Google bonus loaded, total: {len(fonts)}')
        except Exception as e:
            print(f'[FONTS API] Google API unavailable (using embedded DB): {e}')

        self.json_resp({'success': True, 'fonts': fonts, 'total': len(fonts)})

    def serve_static(self, filename, mime):
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', mime + '; charset=utf-8')
            self.send_header('Content-Length', len(data))
            self.send_cors()
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_error(404)

    def serve_file(self, filepath):
        with open(filepath, 'rb') as f:
            data = f.read()
        ext = filepath.rsplit('.', 1)[-1].lower()
        mime = {'ttf': 'font/ttf', 'otf': 'font/otf', 'svg': 'image/svg+xml', 'json': 'application/json'}.get(ext, 'application/octet-stream')
        filename = os.path.basename(filepath)
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', len(data))
        self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.send_cors()
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/convert':
            self.handle_convert()
        elif path == '/convert-auto':
            self.handle_convert_auto()
        elif path == '/optimize':
            self.handle_optimize()
        elif path == '/png-to-svg':
            self.handle_png_to_svg()
        elif path == '/ai-generate':
            self.handle_ai_generate()
        elif path == '/api/font-license':
            self.handle_font_license()
        elif path == '/fonts':
            self.serve_fonts_page()
        elif path == '/api/handwriting-process':
            self.handle_handwriting_process()
        elif path == '/api/handwriting-to-font':
            self.handle_handwriting_to_font()
        else:
            self.send_error(404)

    def read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        ctype = self.headers.get('Content-Type', '')
        body = self.rfile.read(length)
        return parse_multipart(body, ctype)


    def handle_font_license(self):
        """AI-powered font license checker — Anthropic API"""
        try:
            import urllib.request as urlreq
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode('utf-8'))
            font_name = data.get('font', '').strip()

            if not font_name:
                self.json_resp({'error': 'Font name required'}, 400)
                return

            api_key = os.environ.get('ANTHROPIC_API_KEY', '')
            if not api_key:
                self.json_resp({'error': 'API key not configured'}, 500)
                return

            prompt = f"""You are a font licensing expert with deep knowledge of ALL fonts worldwide.

Font to check: "{font_name}"

Respond ONLY with a valid JSON object. No markdown, no extra text:

{{
  "found": true,
  "name": "exact official font name",
  "foundry": "foundry or designer",
  "license_type": "SIL OFL 1.1",
  "license_category": "free",
  "commercial": true,
  "web_use": true,
  "pdf_embed": true,
  "modify": true,
  "logo_branding": true,
  "app_embed": true,
  "source_name": "Google Fonts",
  "source_url": "https://fonts.google.com/...",
  "summary": "2-3 sentence expert summary of this font's license, restrictions, and any free alternatives if it's paid.",
  "free_alternatives": ["Alt1", "Alt2"]
}}

license_category must be: "free", "paid", "personal", or "proprietary"
Set found:false ONLY if this is completely unrecognizable as a real font.
For DaFont fonts: most are "personal" (free personal use only, paid commercial).
For Google Fonts: always "free" (SIL OFL or Apache 2.0).
Be accurate. Respond with ONLY the JSON."""

            payload = json.dumps({
                "model": "claude-opus-4-5",
                "max_tokens": 600,
                "messages": [{"role": "user", "content": prompt}]
            }).encode('utf-8')

            req = urlreq.Request(
                'https://api.anthropic.com/v1/messages',
                data=payload,
                headers={
                    'Content-Type': 'application/json',
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01'
                },
                method='POST'
            )

            with urlreq.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode('utf-8'))

            raw = ''.join(b.get('text', '') for b in resp_data.get('content', []))
            # Extract JSON from response
            import re as _re
            m = _re.search(r'\{[\s\S]*\}', raw)
            if not m:
                self.json_resp({'error': 'Could not parse AI response'}, 500)
                return

            result = json.loads(m.group(0))
            self.json_resp({'success': True, 'result': result})

        except Exception as e:
            print(f'[FONT-LICENSE ERROR] {e}')
            self.json_resp({'error': str(e)}, 500)

    def handle_ai_generate(self):
        """AI ile prompt'tan font üret"""
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode('utf-8'))

            prompt = data.get('prompt', '').strip()
            font_name = data.get('font_name', 'AIFont').strip() or 'AIFont'

            if not prompt:
                self.json_resp({'success': False, 'error': 'Prompt required'}, 400)
                return

            sid, sp = new_session()
            out_dir = os.path.join(sp, 'output')
            os.makedirs(out_dir, exist_ok=True)

            print(f"\n[AI-GENERATE] session={sid[:8]} prompt=\"{prompt[:60]}\" font={font_name}")

            from ai_font import generate_ai_font

            def progress(msg, pct=None):
                print(f"  [AI] {msg}" + (f" ({pct}%)" if pct else ""))

            ttf_path, otf_path = generate_ai_font(
                prompt=prompt,
                font_name=font_name,
                output_dir=out_dir,
                progress_callback=progress
            )

            if not ttf_path:
                self.json_resp({'success': False, 'error': 'Font generation failed'}, 500)
                return

            result_files = []
            for fp in [ttf_path, otf_path]:
                if fp and os.path.exists(fp):
                    fname = os.path.basename(fp)
                    result_files.append({
                        'filename': fname,
                        'size': os.path.getsize(fp),
                        'url': f'/download/{sid}/{fname}'
                    })

            self.json_resp({'success': True, 'files': result_files, 'session': sid})

        except Exception as e:
            import traceback
            print(f"[AI-GENERATE ERROR] {e}\n{traceback.format_exc()}")
            self.json_resp({'success': False, 'error': str(e)}, 500)

    def handle_convert_auto(self):
        """Otomatik optimize et + fonta çevir — tek adımda"""
        try:
            fields, files = self.read_body()
            if 'svg' not in files:
                self.json_resp({'success': False, 'error': 'SVG file missing'}, 400)
                return

            sid, sp = new_session()
            out_dir = os.path.join(sp, 'output')
            os.makedirs(out_dir, exist_ok=True)

            svg_data = files['svg']['data']
            font_name = fields.get('font_name', 'CustomFont').strip() or 'CustomFont'
            bold = fields.get('bold', '0') == '1'
            italic = fields.get('italic', '0') == '1'
            try:
                char_order = json.loads(fields.get('char_order', '[]')) or list(DEFAULT_CHAR_ORDER)
            except:
                char_order = list(DEFAULT_CHAR_ORDER)

            print(f"\n[AUTO-CONVERT] session={sid[:8]} font={font_name}")

            # 1. Otomatik optimize
            from lxml import etree
            try:
                tree = etree.fromstring(svg_data)
                ns = 'http://www.w3.org/2000/svg'
                # Metadata temizle
                to_remove = []
                for elem in tree.iter():
                    if not isinstance(elem.tag, str): continue
                    tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                    if tag in ('metadata', 'title', 'desc'):
                        to_remove.append(elem)
                    attrs_to_del = [k for k in elem.attrib if 'inkscape' in k or 'sodipodi' in k]
                    for attr in attrs_to_del:
                        del elem.attrib[attr]
                for elem in to_remove:
                    p = elem.getparent()
                    if p is not None: p.remove(elem)
                svg_data = etree.tostring(tree, pretty_print=True, xml_declaration=True, encoding='UTF-8')
                print(f"  ✓ SVG optimize edildi")
            except Exception as e:
                print(f"  ⚠ Optimize atlandı: {e}")

            # 2. SVG kaydet
            svg_path = os.path.join(sp, 'input.svg')
            with open(svg_path, 'wb') as f:
                f.write(svg_data)

            # 3. Fonta çevir
            ttf_path, otf_path = build_font(svg_path, font_name, out_dir,
                                             char_order=char_order, bold=bold, italic=italic)
            if not ttf_path:
                self.json_resp({'success': False, 'error': 'Font generation failed'}, 500)
                return

            result_files = []
            for fp in [ttf_path, otf_path]:
                if fp and os.path.exists(fp):
                    fname = os.path.basename(fp)
                    result_files.append({
                        'filename': fname,
                        'size': os.path.getsize(fp),
                        'url': f'/download/{sid}/{fname}'
                    })

            self.json_resp({'success': True, 'files': result_files, 'session': sid, 'auto_optimized': True})

        except Exception as e:
            print(f"[AUTO-CONVERT ERROR] {e}\n{traceback.format_exc()}")
            self.json_resp({'success': False, 'error': str(e)}, 500)

    def handle_png_to_svg(self):
        """PNG/JPG görselini SVG'ye dönüştür — potrace algoritması ile"""
        try:
            fields, files = self.read_body()
            if 'image' not in files:
                self.json_resp({'success': False, 'error': 'Image file missing'}, 400)
                return

            from PIL import Image, ImageFilter, ImageOps
            import io, struct, zlib

            img_data = files['image']['data']
            img = Image.open(io.BytesIO(img_data))

            # RGBA veya RGB'ye çevir
            if img.mode not in ('RGB', 'RGBA', 'L'):
                img = img.convert('RGB')

            # Boyutu sınırla — max 2000px
            max_dim = 2000
            if max(img.size) > max_dim:
                ratio = max_dim / max(img.size)
                img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)

            w, h = img.size

            # Gri tonlamaya çevir ve keskinleştir
            gray = img.convert('L')
            gray = gray.filter(ImageFilter.SHARPEN)

            # Kontrast artır
            from PIL import ImageEnhance
            enhancer = ImageEnhance.Contrast(gray)
            gray = enhancer.enhance(2.0)

            # Binary threshold (Otsu benzeri)
            import statistics
            pixels = list(gray.getdata())
            mean_val = statistics.mean(pixels)
            threshold = mean_val * 0.85
            binary = gray.point(lambda p: 0 if p < threshold else 255, '1')
            binary = binary.convert('L')

            # SVG oluştur — path tabanlı (basit ama etkili)
            # Her koyu piksel bloğunu dikdörtgen olarak grupla
            pix = binary.load()
            paths = []
            visited = [[False]*w for _ in range(h)]

            # Bounding box tespiti — bitişik koyu piksel grupları
            def flood_fill(sx, sy):
                stack = [(sx, sy)]
                pts = []
                while stack:
                    x, y = stack.pop()
                    if x < 0 or x >= w or y < 0 or y >= h: continue
                    if visited[y][x]: continue
                    if pix[x, y] > 128: continue  # beyaz, atla
                    visited[y][x] = True
                    pts.append((x, y))
                    stack.extend([(x+1,y),(x-1,y),(x,y+1),(x,y-1)])
                return pts

            scale = 0.264583  # px → mm (96dpi varsayımı)
            svg_w = w * scale
            svg_h = h * scale

            for y in range(h):
                for x in range(w):
                    if not visited[y][x] and pix[x, y] <= 128:
                        group = flood_fill(x, y)
                        if len(group) < 4: continue  # çok küçük gürültüleri atla
                        xs = [p[0] for p in group]
                        ys = [p[1] for p in group]
                        x0, y0 = min(xs), min(ys)
                        x1, y1 = max(xs)+1, max(ys)+1
                        # Basit dikdörtgen path
                        rx = x0 * scale
                        ry = y0 * scale
                        rw = (x1-x0) * scale
                        rh = (y1-y0) * scale
                        paths.append(f'<rect x="{rx:.3f}" y="{ry:.3f}" width="{rw:.3f}" height="{rh:.3f}"/>')

            svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w:.3f}mm" height="{svg_h:.3f}mm"
     viewBox="0 0 {svg_w:.3f} {svg_h:.3f}">
  <g fill="#000000" stroke="none">
    {''.join(paths)}
  </g>
</svg>'''

            sid, sp = new_session()
            out_dir = os.path.join(sp, 'output')
            os.makedirs(out_dir, exist_ok=True)
            filename = 'converted.svg'
            out_path = os.path.join(out_dir, filename)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(svg_content)

            size_kb = f"{len(svg_content)/1024:.1f} KB"
            print(f"[PNG→SVG] session={sid[:8]} | {w}x{h}px | {len(paths)} shapes | {size_kb}")

            self.json_resp({
                'success': True,
                'filename': filename,
                'url': f'/download/{sid}/{filename}',
                'width': w, 'height': h,
                'shapes': len(paths),
                'size': size_kb
            })

        except Exception as e:
            print(f"[PNG→SVG ERROR] {e}\n{traceback.format_exc()}")
            self.json_resp({'success': False, 'error': str(e)}, 500)

    def handle_convert(self):
        try:
            fields, files = self.read_body()

            if 'svg' not in files:
                self.json_resp({'success': False, 'error': 'SVG file missing'}, 400)
                return

            sid, sp = new_session()
            out_dir = os.path.join(sp, 'output')
            os.makedirs(out_dir, exist_ok=True)

            svg_path = os.path.join(sp, 'input.svg')
            with open(svg_path, 'wb') as f:
                f.write(files['svg']['data'])

            font_name = fields.get('font_name', 'CustomFont').strip() or 'CustomFont'
            bold = fields.get('bold', '0') == '1'
            italic = fields.get('italic', '0') == '1'

            try:
                char_order = json.loads(fields.get('char_order', '[]')) or list(DEFAULT_CHAR_ORDER)
            except:
                char_order = list(DEFAULT_CHAR_ORDER)

            print(f"\n[CONVERT] session={sid[:8]} font={font_name} bold={bold} italic={italic} chars={len(char_order)}")

            ttf_path, otf_path = build_font(svg_path, font_name, out_dir,
                                             char_order=char_order, bold=bold, italic=italic)
            if not ttf_path:
                self.json_resp({'success': False, 'error': 'Font generation failed'}, 500)
                return

            result_files = []
            for fp in [ttf_path, otf_path]:
                if fp and os.path.exists(fp):
                    fname = os.path.basename(fp)
                    result_files.append({
                        'filename': fname,
                        'size': os.path.getsize(fp),
                        'url': f'/download/{sid}/{fname}'
                    })

            self.json_resp({'success': True, 'files': result_files, 'session': sid})

        except Exception as e:
            print(f"[CONVERT ERROR] {e}\n{traceback.format_exc()}")
            self.json_resp({'success': False, 'error': str(e)}, 500)

    def handle_optimize(self):
        try:
            fields, files = self.read_body()

            if 'svg' not in files:
                self.json_resp({'success': False, 'error': 'SVG file missing'}, 400)
                return

            sid, sp = new_session()
            out_dir = os.path.join(sp, 'output')
            os.makedirs(out_dir, exist_ok=True)

            svg_data = files['svg']['data']
            original_size = f"{len(svg_data)/1024:.1f} KB"
            clean_ids = fields.get('clean_ids', '1') == '1'

            from lxml import etree

            tree = etree.fromstring(svg_data)
            ns = 'http://www.w3.org/2000/svg'

            if clean_ids:
                to_remove = []
                for elem in tree.iter():
                    if not isinstance(elem.tag, str):
                        continue
                    tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                    if tag in ('metadata', 'title', 'desc'):
                        to_remove.append(elem)
                    attrs_to_del = [k for k in elem.attrib if 'inkscape' in k or 'sodipodi' in k]
                    for attr in attrs_to_del:
                        del elem.attrib[attr]
                for elem in to_remove:
                    p = elem.getparent()
                    if p is not None:
                        p.remove(elem)

            optimized = etree.tostring(tree, pretty_print=True, xml_declaration=True, encoding='UTF-8')
            optimized_size = f"{len(optimized)/1024:.1f} KB"

            groups = [e for e in tree.iter('{%s}g' % ns) if list(e.iter('{%s}path' % ns))]
            print(f"[OPTIMIZE] session={sid[:8]} {original_size} → {optimized_size} | {len(groups)} groups preserved")

            filename = 'optimized.svg'
            out_path = os.path.join(out_dir, filename)
            with open(out_path, 'wb') as f:
                f.write(optimized)

            self.json_resp({
                'success': True,
                'filename': filename,
                'url': f'/download/{sid}/{filename}',
                'original_size': original_size,
                'optimized_size': optimized_size,
            })

        except Exception as e:
            print(f"[OPTIMIZE ERROR] {e}\n{traceback.format_exc()}")
            self.json_resp({'success': False, 'error': str(e)}, 500)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    port = int(os.environ.get("PORT", 8080))

    print(f"\n{'='*52}")
    print(f"  VectoFont — SVG to Font Converter")
    print(f"  Multi-user | Auto-cleanup | v2.0")
    print(f"{'='*52}")
    print(f"\n  ✓ Open: http://localhost:{port}")
    print(f"  ✓ Sessions auto-delete after {SESSION_TTL//60} min")
    print(f"  ✓ Ctrl+C to stop\n")

    server = HTTPServer(('0.0.0.0', port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        shutil.rmtree(BASE_DIR, ignore_errors=True)

if __name__ == '__main__':
    main()
