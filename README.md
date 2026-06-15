# AMT PAS Generator

A guided web interface that turns a folder of source documents into **one branded
Technical Submittal (PAS) PDF** — cover, bilingual table of contents, eight sections,
datasheets and certificates merged together.

It is a thin wrapper around the **[amt-pas-compiler](https://github.com/airandblueamt-Claude/amt-pas-compiler)**
engine: this app only collects metadata, sorts your uploaded files into the compiler's
numbered-section folders, and calls it. The PDF logic lives entirely in the compiler.

```
Wizard (browser)  ──>  FastAPI (app.py)  ──>  amt-pas-compiler  ──>  one PDF
  metadata + files       numbered folders        cover/TOC/merge
```

## The 4-step wizard

1. **Project details** — reference, version, bilingual title, client, sign-off, revision.
2. **Upload & sort files** — drop files (or a whole folder). Each file is auto-classified
   into a section (BOQ, datasheet, warranty, single-line diagram, …); fix any guesses.
3. **Review** — shows the compiler's discovery report and flags any missing required section.
4. **Generate** — builds the PDF and gives you a download link.

---

## Run free, locally (no hosting needed)

Requires Python 3.10+ and git. LibreOffice is optional but recommended for
pixel-faithful tables (`sudo apt-get install -y libreoffice-calc libreoffice-writer`);
without it the compiler uses a readable `reportlab` fallback.

```bash
git clone https://github.com/airandblueamt-Claude/amt-pas-generator.git
cd amt-pas-generator
./fetch-compiler.sh                     # clone the compiler engine into ./compiler
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload                # open http://127.0.0.1:8000
```

## Deploy free to Hugging Face Spaces (public URL, includes LibreOffice)

[Hugging Face Spaces](https://huggingface.co/spaces) offers a **free Docker tier** —
the one free host that allows Python **and** the LibreOffice binary.

1. Create a new Space → **SDK: Docker** → Blank.
2. Push this repo's contents to the Space (the `Dockerfile` is detected automatically;
   it clones the compiler and installs LibreOffice at build time).
3. The app serves on port `7860` — Spaces wires that up for you.

The same `Dockerfile` runs on any free/low-cost Docker host (Render, Railway, Fly.io,
Cloud Run) if you prefer.

---

## Notes

- **No paid services.** Files are uploaded straight from the browser; nothing touches
  OneDrive/Azure. (A native OneDrive picker can be added later as a second upload source.)
- **Sessions** (uploads + generated PDFs) live under `sessions/` locally or `/tmp` in the
  container. Treat tender documents as confidential — clear `sessions/` periodically.
- `compiler/` is a fetched dependency and is git-ignored — never edit it; re-run
  `./fetch-compiler.sh` to update.
