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

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ('/', '/index.html'):
            self.serve_static('index.html', 'text/html')

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
        elif path == '/optimize':
            self.handle_optimize()
        elif path == '/ai-generate':
            self.handle_ai_generate()
        else:
            self.send_error(404)

    def read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        ctype = self.headers.get('Content-Type', '')
        body = self.rfile.read(length)
        return parse_multipart(body, ctype)


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
