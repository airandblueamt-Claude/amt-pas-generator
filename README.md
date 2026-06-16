# AMT PAS Generator

A guided web app that turns a folder of source documents into **one branded,
print-ready Technical Submittal (PAS) PDF** — cover, bilingual table of contents,
eight sections, BOQ tables, datasheets, certificates and drawings, all assembled
to AMT's document-control standard.

**Live app:** https://randblue-amt-pas-generator.hf.space

It is a thin wrapper around the **[amt-pas-compiler](https://github.com/airandblueamt-Claude/amt-pas-compiler)**
engine — the web app collects the cover/metadata, sorts your uploaded files into the
compiler's numbered sections, and calls it. All PDF logic lives in the compiler.

```
Wizard (browser)  ──>  FastAPI (app.py)  ──>  amt-pas-compiler  ──>  one PDF
  metadata + files       numbered sections       cover / TOC / merge
```

---

## How to use it (the 4-step wizard)

1. **Project details** — submittal ref no., version, date, bilingual project title,
   client/building, the three sign-off roles + initials, and the revision line. These
   fill the **cover page** and the **sign-off table**.
2. **Upload & sort files** — drop your files (or pick a whole folder exported from
   OneDrive). Each file is **auto-sorted** into the right section; drag a file between
   the section cards, or use its menu, to fix any guess. The coverage strip shows when
   every required section has a file.
3. **Review** — shows the compiler's discovery report and flags any missing required
   section before you commit.
4. **Generate** — builds the PDF, shows the page count, and gives a **Download** link.

Tip: nothing touches OneDrive/Azure — just drag in the files you exported from there.

---

## What it produces — the 8 sections

| # | Section | Accepts | AMT logo on the content? |
|---|---------|---------|--------------------------|
| 1 | Tender BOQ | Excel **or** PDF | No — it's the client's document |
| 2 | Material Sheet Provided by AMT | Excel **or** PDF | Yes (small header logo) |
| 3 | Material Traceability & BoQ Compliance | Excel **or** PDF | Yes |
| 4 | Material Selection | Excel **or** PDF | Yes |
| 5 | Product's Datasheet & Catalogue | PDF (datasheets) | No — manufacturer's document |
| 6 | Vendor Partnership Certificate *(optional)* | PDF | No — vendor's document |
| 7 | Warranty Certificate *(optional)* | PDF | No — vendor's document |
| 8 | Layout & Single Line Diagram | PDF (drawings) | Yes (small corner logo) |

Sections 1–5 and 8 are **required**; 6 and 7 are optional (a placeholder page is
inserted if empty). Every section also gets a **branded divider page** in front of it,
so AMT identity is always present even where the content itself is left unbranded.

### Format is interchangeable
A section's content can be **Excel or PDF** and the layout is always good — spreadsheets
are rendered as tables, PDFs/Word are appended. Upload the BOQ as Excel or as a PDF; it
works either way.

---

## Document-control behaviour (best practice, built in)

- **Uniform A4 portrait** — every page is the same A4 portrait size, so the submittal
  reads as one controlled document.
- **Drawings keep their native size** — Section 8 fold-out sheets (A1 / A3 single-line
  diagrams, layouts) are **not** shrunk to A4; they stay full size.
- **No header/footer overlap** — AMT-generated tables reserve a top/bottom band so the
  logo and reference line never sit on the table.
- **Clean reference documents** — third-party datasheets, certificates and drawings are
  kept at full size and are **not** stamped; their branded divider carries AMT identity.
- **Sharp reference images** — embedded product/reference images are exported at full
  resolution (no down-sampling) and image-bearing sheets keep their layout, so pictures
  stay crisp and correctly sized.
- **Bilingual, clickable Table of Contents** — English + Arabic with real page numbers;
  each row links to that section's first page.

---

## Run locally (free)

Requires Python 3.10+ and git. LibreOffice is strongly recommended for pixel-faithful
Excel/Arabic rendering and sharp images (`sudo apt-get install -y libreoffice-calc
libreoffice-writer`); without it the compiler uses a readable `reportlab` fallback.

```bash
git clone https://github.com/airandblueamt-Claude/amt-pas-generator.git
cd amt-pas-generator
./fetch-compiler.sh                     # clone the compiler engine into ./compiler
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload                # open http://127.0.0.1:8000
```

## Deploy free to Hugging Face Spaces (public URL, includes LibreOffice)

[Hugging Face Spaces](https://huggingface.co/spaces) offers a free **Docker** tier — the
one free host that allows Python *and* the LibreOffice binary.

1. Create a new Space → **SDK: Docker** → Blank.
2. Push this repo's contents to the Space (the `Dockerfile` is auto-detected; it clones
   the pinned compiler version and installs LibreOffice at build time).
3. The app serves on port `7860` — Spaces wires that up for you.

The same `Dockerfile` runs on any Docker host (Render, Railway, Fly.io, Cloud Run).
To pull a newer engine, bump `PAS_COMPILER_REF` in the `Dockerfile` and redeploy.

---

## Advanced: compiler config knobs

The web app sends sensible defaults, but the underlying compiler config accepts:

| Key | Default | Effect |
|-----|---------|--------|
| `unbranded_sections` | `[1, 5, 6, 7]` | Sections whose content gets no AMT logo |
| `native_sections` | `[8]` | Sections kept at native size (not fitted to A4) |
| `uniform_pages` | `true` | Fit all non-native pages to A4 portrait |
| `missing_section_mode` | `placeholder` | `placeholder` \| `skip` \| `error` for optional sections |

---

## Notes & housekeeping

- **No paid services.** Files upload straight from the browser; nothing leaves the host.
- **Confidential data.** Uploaded source docs and generated PDFs live under `sessions/`
  locally (or `/tmp` in the container). Clear them periodically — tender material is
  sensitive.
- **`compiler/` is a fetched dependency** (git-ignored). Never edit it directly; re-run
  `./fetch-compiler.sh`, or change `PAS_COMPILER_REF` in the `Dockerfile`, to update.
- If a generated table looks cramped, it's a very wide sheet fitted to A4 portrait — the
  data is intact; consider splitting columns in the source.
