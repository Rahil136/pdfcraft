# PDFCraft — Real PDF Processing Backend
## Setup in 3 Steps

### Step 1 — Install Python dependencies
```bash
pip install flask pypdf2 pillow reportlab flask-cors
```
Optional (for PDF → JPG):
```bash
pip install pdf2image
# Also install Poppler: https://poppler.freedesktop.org/
```

### Step 2 — Run the server
```bash
cd pdfcraft
python app.py
```
You'll see:
```
==================================================
  PDFCraft Backend Starting...
==================================================
  PyPDF2:    ✅ Ready
  Pillow:    ✅ Ready
  ReportLab: ✅ Ready
==================================================
  Open: http://localhost:5000
==================================================
```

### Step 3 — Open the website
Go to: **http://localhost:5000**

---

## What Each Tool Actually Does

| Tool | Library | What Happens |
|------|---------|--------------|
| Merge PDF | PyPDF2 PdfMerger | All PDFs are genuinely combined page by page |
| Split PDF | PyPDF2 PdfWriter | Every page becomes a separate PDF, zipped |
| Remove Pages | PyPDF2 PdfWriter | Specified pages are dropped from the output |
| Extract Pages | PyPDF2 PdfWriter | Only specified pages are written to new PDF |
| Compress PDF | PyPDF2 compress_content_streams | Deflate compression on content streams |
| Rotate PDF | PyPDF2 page.rotate() | Pages are permanently rotated |
| Watermark | ReportLab + PyPDF2 | Text rendered at angle, merged onto each page |
| Page Numbers | ReportLab + PyPDF2 | Numbers rendered and merged onto each page |
| Protect PDF | PyPDF2 writer.encrypt() | Real AES password encryption |
| Unlock PDF | PyPDF2 reader.decrypt() | Decryption with provided password |
| JPG/PNG → PDF | Pillow Image.save() | Images embedded into a real PDF |
| PDF → JPG | pdf2image | Each page rendered to JPEG at 150 DPI |

## Deploy to the Web (optional)

### Render.com (Free)
1. Push this folder to GitHub
2. Go to render.com → New Web Service
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `python app.py`
5. Update `const API = 'https://your-app.onrender.com'` in index.html

### Railway / Fly.io
Same approach — just point to your deployed URL in the frontend.

## File Structure
```
pdfcraft/
├── app.py              ← Flask backend (run this)
├── requirements.txt    ← Python dependencies
├── templates/
│   └── index.html      ← Full frontend UI
├── uploads/            ← Temp uploads (auto-deleted after 2h)
└── outputs/            ← Temp outputs (auto-deleted after 2h)
```
