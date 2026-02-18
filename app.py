"""
PDFCraft Backend - Real PDF Processing Server
=============================================
Install dependencies:
    pip install flask pypdf2 pillow reportlab flask-cors

Run:
    python app.py

Then open: http://localhost:5000
"""

from flask import Flask, request, send_file, jsonify, render_template
from flask_cors import CORS
import os, io, uuid, time, threading

# PDF Libraries
try:
    import PyPDF2
    from PyPDF2 import PdfReader, PdfWriter, PdfMerger
    PYPDF2_OK = True
except ImportError:
    PYPDF2_OK = False

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.units import inch
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ─────────────────────────────────────────
# AUTO-CLEANUP: delete files older than 2h
# ─────────────────────────────────────────
def cleanup_old_files():
    while True:
        now = time.time()
        for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER]:
            for f in os.listdir(folder):
                fp = os.path.join(folder, f)
                if os.path.isfile(fp) and now - os.path.getmtime(fp) > 7200:
                    os.remove(fp)
        time.sleep(600)  # check every 10 min

threading.Thread(target=cleanup_old_files, daemon=True).start()

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
def save_upload(file):
    ext = os.path.splitext(file.filename)[1].lower()
    uid = str(uuid.uuid4())
    path = os.path.join(UPLOAD_FOLDER, uid + ext)
    file.save(path)
    return path

def output_path(suffix='.pdf'):
    return os.path.join(OUTPUT_FOLDER, str(uuid.uuid4()) + suffix)

def error(msg, code=400):
    return jsonify({'error': msg}), code

def check_lib(name):
    if name == 'pypdf2' and not PYPDF2_OK:
        return error('PyPDF2 not installed. Run: pip install pypdf2')
    if name == 'pil' and not PIL_OK:
        return error('Pillow not installed. Run: pip install pillow')
    if name == 'reportlab' and not REPORTLAB_OK:
        return error('ReportLab not installed. Run: pip install reportlab')
    return None

# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def status():
    return jsonify({
        'status': 'online',
        'pypdf2': PYPDF2_OK,
        'pillow': PIL_OK,
        'reportlab': REPORTLAB_OK,
        'tools_available': get_available_tools()
    })

def get_available_tools():
    tools = []
    if PYPDF2_OK:
        tools += ['merge', 'split', 'rotate', 'extract', 'compress', 'protect', 'unlock', 'remove_pages', 'page_numbers']
    if PIL_OK:
        tools += ['jpg_to_pdf', 'images_to_pdf']
    if PIL_OK and PYPDF2_OK:
        tools += ['pdf_to_jpg']
    return tools

# ── 1. MERGE PDF ──────────────────────────
@app.route('/api/merge', methods=['POST'])
def merge_pdf():
    e = check_lib('pypdf2')
    if e: return e

    files = request.files.getlist('files')
    if len(files) < 2:
        return error('Please upload at least 2 PDF files to merge.')

    merger = PdfMerger()
    saved = []
    try:
        for f in files:
            if not f.filename.lower().endswith('.pdf'):
                return error(f'"{f.filename}" is not a PDF file.')
            path = save_upload(f)
            saved.append(path)
            merger.append(path)

        out = output_path('.pdf')
        with open(out, 'wb') as fout:
            merger.write(fout)
        merger.close()

        return send_file(out, as_attachment=True,
                         download_name='merged.pdf',
                         mimetype='application/pdf')
    except Exception as ex:
        return error(f'Merge failed: {str(ex)}')
    finally:
        for p in saved:
            if os.path.exists(p): os.remove(p)

# ── 2. SPLIT PDF ──────────────────────────
@app.route('/api/split', methods=['POST'])
def split_pdf():
    e = check_lib('pypdf2')
    if e: return e

    file = request.files.get('file')
    if not file: return error('No file uploaded.')

    mode = request.form.get('mode', 'all')  # 'all' or 'range'
    page_range = request.form.get('range', '')  # e.g. "1-3,5,7-9"

    path = save_upload(file)
    try:
        reader = PdfReader(path)
        total = len(reader.pages)

        if mode == 'all':
            # Split every page into individual PDF
            import zipfile
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                for i in range(total):
                    writer = PdfWriter()
                    writer.add_page(reader.pages[i])
                    buf = io.BytesIO()
                    writer.write(buf)
                    zf.writestr(f'page_{i+1}.pdf', buf.getvalue())
            zip_buf.seek(0)
            return send_file(zip_buf, as_attachment=True,
                             download_name='split_pages.zip',
                             mimetype='application/zip')
        else:
            # Parse range
            pages = parse_page_range(page_range, total)
            if not pages:
                return error('Invalid page range.')
            writer = PdfWriter()
            for p in pages:
                writer.add_page(reader.pages[p])
            out = output_path('.pdf')
            with open(out, 'wb') as f:
                writer.write(f)
            return send_file(out, as_attachment=True,
                             download_name='split.pdf',
                             mimetype='application/pdf')
    except Exception as ex:
        return error(f'Split failed: {str(ex)}')
    finally:
        if os.path.exists(path): os.remove(path)

def parse_page_range(s, total):
    """Parse '1-3,5,7-9' into 0-indexed page list."""
    pages = []
    for part in s.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-', 1)
            try:
                a, b = int(a)-1, int(b)-1
                pages += list(range(max(0,a), min(total-1,b)+1))
            except: pass
        else:
            try:
                p = int(part) - 1
                if 0 <= p < total: pages.append(p)
            except: pass
    return pages

# ── 3. COMPRESS PDF ───────────────────────
@app.route('/api/compress', methods=['POST'])
def compress_pdf():
    e = check_lib('pypdf2')
    if e: return e

    file = request.files.get('file')
    if not file: return error('No file uploaded.')

    path = save_upload(file)
    try:
        reader = PdfReader(path)
        writer = PdfWriter()
        for page in reader.pages:
            page.compress_content_streams()  # compress page content
            writer.add_page(page)

        # Copy metadata
        if reader.metadata:
            writer.add_metadata(reader.metadata)

        out = output_path('.pdf')
        with open(out, 'wb') as f:
            writer.write(f)

        original = os.path.getsize(path)
        compressed = os.path.getsize(out)
        reduction = round((1 - compressed/original) * 100, 1)

        resp = send_file(out, as_attachment=True,
                         download_name='compressed.pdf',
                         mimetype='application/pdf')
        resp.headers['X-Original-Size'] = str(original)
        resp.headers['X-Compressed-Size'] = str(compressed)
        resp.headers['X-Reduction-Percent'] = str(reduction)
        return resp
    except Exception as ex:
        return error(f'Compress failed: {str(ex)}')
    finally:
        if os.path.exists(path): os.remove(path)

# ── 4. ROTATE PDF ─────────────────────────
@app.route('/api/rotate', methods=['POST'])
def rotate_pdf():
    e = check_lib('pypdf2')
    if e: return e

    file = request.files.get('file')
    if not file: return error('No file uploaded.')
    angle = int(request.form.get('angle', 90))
    if angle not in [90, 180, 270]: return error('Angle must be 90, 180, or 270.')

    path = save_upload(file)
    try:
        reader = PdfReader(path)
        writer = PdfWriter()
        for page in reader.pages:
            page.rotate(angle)
            writer.add_page(page)
        out = output_path('.pdf')
        with open(out, 'wb') as f:
            writer.write(f)
        return send_file(out, as_attachment=True,
                         download_name='rotated.pdf',
                         mimetype='application/pdf')
    except Exception as ex:
        return error(f'Rotate failed: {str(ex)}')
    finally:
        if os.path.exists(path): os.remove(path)

# ── 5. EXTRACT PAGES ──────────────────────
@app.route('/api/extract', methods=['POST'])
def extract_pages():
    e = check_lib('pypdf2')
    if e: return e

    file = request.files.get('file')
    if not file: return error('No file uploaded.')
    page_range = request.form.get('range', '1')

    path = save_upload(file)
    try:
        reader = PdfReader(path)
        total = len(reader.pages)
        pages = parse_page_range(page_range, total)
        if not pages: return error('Invalid page range.')

        writer = PdfWriter()
        for p in pages:
            writer.add_page(reader.pages[p])
        out = output_path('.pdf')
        with open(out, 'wb') as f:
            writer.write(f)
        return send_file(out, as_attachment=True,
                         download_name='extracted.pdf',
                         mimetype='application/pdf')
    except Exception as ex:
        return error(f'Extract failed: {str(ex)}')
    finally:
        if os.path.exists(path): os.remove(path)

# ── 6. REMOVE PAGES ───────────────────────
@app.route('/api/remove-pages', methods=['POST'])
def remove_pages():
    e = check_lib('pypdf2')
    if e: return e

    file = request.files.get('file')
    if not file: return error('No file uploaded.')
    to_remove = request.form.get('pages', '')  # e.g. "2,4,6"

    path = save_upload(file)
    try:
        reader = PdfReader(path)
        total = len(reader.pages)
        remove_set = set(parse_page_range(to_remove, total))

        writer = PdfWriter()
        for i, page in enumerate(reader.pages):
            if i not in remove_set:
                writer.add_page(page)

        out = output_path('.pdf')
        with open(out, 'wb') as f:
            writer.write(f)
        return send_file(out, as_attachment=True,
                         download_name='removed_pages.pdf',
                         mimetype='application/pdf')
    except Exception as ex:
        return error(f'Remove pages failed: {str(ex)}')
    finally:
        if os.path.exists(path): os.remove(path)

# ── 7. PAGE NUMBERS ───────────────────────
@app.route('/api/page-numbers', methods=['POST'])
def add_page_numbers():
    e = check_lib('pypdf2')
    if e: return e
    e2 = check_lib('reportlab')
    if e2: return e2

    file = request.files.get('file')
    if not file: return error('No file uploaded.')
    position = request.form.get('position', 'bottom-center')  # bottom-center, bottom-right, top-center

    path = save_upload(file)
    try:
        reader = PdfReader(path)
        total = len(reader.pages)
        writer = PdfWriter()

        for i, page in enumerate(reader.pages):
            # Get page dimensions
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)

            # Create overlay with page number
            packet = io.BytesIO()
            c = canvas.Canvas(packet, pagesize=(w, h))
            c.setFont('Helvetica', 10)
            c.setFillColorRGB(0.4, 0.4, 0.4)

            text = f'{i+1} / {total}'
            text_w = c.stringWidth(text, 'Helvetica', 10)

            if position == 'bottom-center':
                x, y = (w - text_w) / 2, 20
            elif position == 'bottom-right':
                x, y = w - text_w - 30, 20
            elif position == 'bottom-left':
                x, y = 30, 20
            elif position == 'top-center':
                x, y = (w - text_w) / 2, h - 30
            else:
                x, y = (w - text_w) / 2, 20

            c.drawString(x, y, text)
            c.save()
            packet.seek(0)

            # Merge overlay onto page
            overlay_reader = PdfReader(packet)
            page.merge_page(overlay_reader.pages[0])
            writer.add_page(page)

        out = output_path('.pdf')
        with open(out, 'wb') as f:
            writer.write(f)
        return send_file(out, as_attachment=True,
                         download_name='page_numbers.pdf',
                         mimetype='application/pdf')
    except Exception as ex:
        return error(f'Page numbers failed: {str(ex)}')
    finally:
        if os.path.exists(path): os.remove(path)

# ── 8. WATERMARK ──────────────────────────
@app.route('/api/watermark', methods=['POST'])
def watermark_pdf():
    e = check_lib('pypdf2')
    if e: return e
    e2 = check_lib('reportlab')
    if e2: return e2

    file = request.files.get('file')
    if not file: return error('No file uploaded.')
    text = request.form.get('text', 'CONFIDENTIAL')
    opacity = float(request.form.get('opacity', 0.3))

    path = save_upload(file)
    try:
        reader = PdfReader(path)
        writer = PdfWriter()

        for page in reader.pages:
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)

            packet = io.BytesIO()
            c = canvas.Canvas(packet, pagesize=(w, h))
            c.setFont('Helvetica-Bold', 48)
            c.setFillColorRGB(0.6, 0.6, 0.6, alpha=opacity)
            c.saveState()
            c.translate(w / 2, h / 2)
            c.rotate(45)
            text_w = c.stringWidth(text, 'Helvetica-Bold', 48)
            c.drawString(-text_w / 2, 0, text)
            c.restoreState()
            c.save()
            packet.seek(0)

            overlay = PdfReader(packet)
            page.merge_page(overlay.pages[0])
            writer.add_page(page)

        out = output_path('.pdf')
        with open(out, 'wb') as f:
            writer.write(f)
        return send_file(out, as_attachment=True,
                         download_name='watermarked.pdf',
                         mimetype='application/pdf')
    except Exception as ex:
        return error(f'Watermark failed: {str(ex)}')
    finally:
        if os.path.exists(path): os.remove(path)

# ── 9. PROTECT PDF ────────────────────────
@app.route('/api/protect', methods=['POST'])
def protect_pdf():
    e = check_lib('pypdf2')
    if e: return e

    file = request.files.get('file')
    if not file: return error('No file uploaded.')
    password = request.form.get('password', '')
    if not password: return error('Please provide a password.')

    path = save_upload(file)
    try:
        reader = PdfReader(path)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        writer.encrypt(password)

        out = output_path('.pdf')
        with open(out, 'wb') as f:
            writer.write(f)
        return send_file(out, as_attachment=True,
                         download_name='protected.pdf',
                         mimetype='application/pdf')
    except Exception as ex:
        return error(f'Protect failed: {str(ex)}')
    finally:
        if os.path.exists(path): os.remove(path)

# ── 10. UNLOCK PDF ────────────────────────
@app.route('/api/unlock', methods=['POST'])
def unlock_pdf():
    e = check_lib('pypdf2')
    if e: return e

    file = request.files.get('file')
    if not file: return error('No file uploaded.')
    password = request.form.get('password', '')

    path = save_upload(file)
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            if not reader.decrypt(password):
                return error('Wrong password. Please enter the correct password.')

        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        out = output_path('.pdf')
        with open(out, 'wb') as f:
            writer.write(f)
        return send_file(out, as_attachment=True,
                         download_name='unlocked.pdf',
                         mimetype='application/pdf')
    except Exception as ex:
        return error(f'Unlock failed: {str(ex)}')
    finally:
        if os.path.exists(path): os.remove(path)

# ── 11. JPG / IMAGES → PDF ────────────────
@app.route('/api/images-to-pdf', methods=['POST'])
def images_to_pdf():
    e = check_lib('pil')
    if e: return e

    files = request.files.getlist('files')
    if not files: return error('No images uploaded.')

    saved = []
    try:
        images = []
        for f in files:
            path = save_upload(f)
            saved.append(path)
            img = Image.open(path).convert('RGB')
            images.append(img)

        out = output_path('.pdf')
        if len(images) == 1:
            images[0].save(out, 'PDF', resolution=100)
        else:
            images[0].save(out, 'PDF', resolution=100, save_all=True, append_images=images[1:])

        return send_file(out, as_attachment=True,
                         download_name='images.pdf',
                         mimetype='application/pdf')
    except Exception as ex:
        return error(f'Image to PDF failed: {str(ex)}')
    finally:
        for p in saved:
            if os.path.exists(p): os.remove(p)

# ── 12. PDF → JPG ─────────────────────────
@app.route('/api/pdf-to-jpg', methods=['POST'])
def pdf_to_jpg():
    # Requires pdf2image + poppler
    try:
        from pdf2image import convert_from_path
    except ImportError:
        return error('pdf2image not installed. Run: pip install pdf2image\nAlso install poppler: https://poppler.freedesktop.org/')

    file = request.files.get('file')
    if not file: return error('No file uploaded.')

    path = save_upload(file)
    try:
        images = convert_from_path(path, dpi=150)
        import zipfile
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w') as zf:
            for i, img in enumerate(images):
                buf = io.BytesIO()
                img.save(buf, 'JPEG', quality=85)
                zf.writestr(f'page_{i+1}.jpg', buf.getvalue())
        zip_buf.seek(0)
        return send_file(zip_buf, as_attachment=True,
                         download_name='pdf_pages.zip',
                         mimetype='application/zip')
    except Exception as ex:
        return error(f'PDF to JPG failed: {str(ex)}')
    finally:
        if os.path.exists(path): os.remove(path)

# ── 13. GET PDF INFO ──────────────────────
@app.route('/api/info', methods=['POST'])
def pdf_info():
    e = check_lib('pypdf2')
    if e: return e

    file = request.files.get('file')
    if not file: return error('No file uploaded.')

    path = save_upload(file)
    try:
        reader = PdfReader(path)
        info = {
            'pages': len(reader.pages),
            'encrypted': reader.is_encrypted,
            'metadata': {}
        }
        if reader.metadata:
            m = reader.metadata
            info['metadata'] = {
                'title': m.get('/Title', ''),
                'author': m.get('/Author', ''),
                'creator': m.get('/Creator', ''),
                'subject': m.get('/Subject', ''),
            }
        if reader.pages:
            p0 = reader.pages[0]
            info['width'] = float(p0.mediabox.width)
            info['height'] = float(p0.mediabox.height)
        info['file_size'] = os.path.getsize(path)
        return jsonify(info)
    except Exception as ex:
        return error(f'Could not read PDF info: {str(ex)}')
    finally:
        if os.path.exists(path): os.remove(path)

# ─────────────────────────────────────────
if __name__ == '__main__':
    print("\n" + "="*50)
    print("  PDFCraft Backend Starting...")
    print("="*50)
    print(f"  PyPDF2:    {'✅ Ready' if PYPDF2_OK else '❌ Not installed — pip install pypdf2'}")
    print(f"  Pillow:    {'✅ Ready' if PIL_OK else '❌ Not installed — pip install pillow'}")
    print(f"  ReportLab: {'✅ Ready' if REPORTLAB_OK else '❌ Not installed — pip install reportlab'}")
    print("="*50)
    print("  Open: http://localhost:5000")
    print("="*50 + "\n")
    app.run(debug=True, port=5000)
