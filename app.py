"""
AMT PAS Generator — guided web interface around the amt-pas-compiler engine.

This app never reimplements the PDF logic. It:
  1. collects cover/sign-off metadata through a wizard,
  2. accepts uploaded source files and maps them into the compiler's
     numbered-section folder contract,
  3. calls the compiler (discover + assemble) to emit ONE branded PDF.

The compiler is a fetched dependency under ./compiler (see fetch-compiler.sh).
Run:  uvicorn app:app --reload      (after pip install -r requirements.txt)
"""
from __future__ import annotations

import os
import re
import sys
import json
import uuid
import shutil
import tempfile

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# --------------------------------------------------------------------------- #
# Locate and import the compiler (read-only dependency)
# --------------------------------------------------------------------------- #
HERE = os.path.dirname(os.path.abspath(__file__))
COMPILER_DIR = os.environ.get("PAS_COMPILER_DIR", os.path.join(HERE, "compiler"))
SCRIPTS_DIR = os.path.join(COMPILER_DIR, "scripts")

if not os.path.isdir(SCRIPTS_DIR):
    raise RuntimeError(
        f"Compiler not found at {COMPILER_DIR}.\n"
        f"Run ./fetch-compiler.sh first (it clones the amt-pas-compiler repo)."
    )

sys.path.insert(0, SCRIPTS_DIR)
import pas_spec as SPEC      # noqa: E402
import discover as DISC      # noqa: E402
import assemble as ASM       # noqa: E402
import build_pas as BUILD    # noqa: E402

# Where uploaded files + generated PDFs live for the lifetime of a session.
SESSIONS_DIR = os.environ.get("PAS_SESSIONS_DIR", os.path.join(HERE, "sessions"))
os.makedirs(SESSIONS_DIR, exist_ok=True)
# Blob store for files uploaded in the background as the user adds them, so the
# "Review" step only posts a tiny manifest (instant) instead of re-uploading bytes.
UPLOADS_DIR = os.path.join(SESSIONS_DIR, "_uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

app = FastAPI(title="AMT PAS Generator")


# --------------------------------------------------------------------------- #
# Section template (authoritative — comes from the compiler, not hardcoded)
# --------------------------------------------------------------------------- #
def default_sections() -> list[dict]:
    tmpl = SPEC.resolve_template({})  # built-in 8-section material submittal
    return [
        dict(no=s["no"], en=s["en"], ar=s["ar"],
             kind=s["kind"], optional=s["optional"], prefix=s["prefix"])
        for s in tmpl["sections"]
    ]


SECTIONS = default_sections()
SECTION_BY_NO = {s["no"]: s for s in SECTIONS}


# --------------------------------------------------------------------------- #
# Auto-classification: guess which section a file belongs to from its name
# --------------------------------------------------------------------------- #
TABLE_RULES = [   # (section_no, keywords) for spreadsheet sections 1-4
    (1, ("boq", "tender", "bill of quant")),
    (2, ("amt material", "material sheet", "provided by amt", "amt sheet")),
    (3, ("traceab", "compliance")),
    (4, ("selection",)),
]
PDF_RULES = [     # (section_no, keywords) for append/PDF sections
    (6, ("partnership", "authoriz", "distributor", "vendor cert", "channel")),
    (7, ("warranty", "guarantee")),
    (8, ("single line", "single-line", "sld", "layout", "diagram",
          "schematic", "drawing", "riser")),
    (5, ("datasheet", "data sheet", "catalog", "catalogue", "brochure",
          "spec", "manual")),
]


def classify(filename: str) -> dict:
    """Return {section, reason, confident} suggestion for a file."""
    name = filename.lower()
    ext = os.path.splitext(name)[1]

    if ext in (".xlsx", ".xls"):
        for no, kws in TABLE_RULES:
            if any(k in name for k in kws):
                return dict(section=no, reason=f"spreadsheet matched '{_hit(name, kws)}'",
                            confident=True)
        return dict(section=1, reason="spreadsheet — defaulted to §1, please confirm",
                    confident=False)

    if ext in (".pdf",):
        for no, kws in PDF_RULES:
            if any(k in name for k in kws):
                return dict(section=no, reason=f"matched '{_hit(name, kws)}'", confident=True)
        return dict(section=5, reason="PDF — defaulted to Datasheets §5, please confirm",
                    confident=False)

    if ext in (".docx", ".doc"):
        if any(k in name for k in ("warranty", "guarantee")):
            return dict(section=7, reason="document matched 'warranty'", confident=True)
        if any(k in name for k in ("partnership", "authoriz")):
            return dict(section=6, reason="document matched 'partnership'", confident=True)
        return dict(section=8, reason="document — defaulted to §8, please confirm",
                    confident=False)

    return dict(section=5, reason=f"unrecognised type '{ext}' — please confirm",
                confident=False)


def _hit(name: str, kws) -> str:
    for k in kws:
        if k in name:
            return k
    return kws[0]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _safe(name: str) -> str:
    base = os.path.basename(name).replace("\\", "_").replace("/", "_")
    return re.sub(r"[^A-Za-z0-9._ \-()]", "_", base) or "file"


def _session_dir(sid: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,40}", sid):
        raise HTTPException(400, "bad session id")
    d = os.path.join(SESSIONS_DIR, sid)
    if not os.path.isdir(d):
        raise HTTPException(404, "session not found")
    return d


def _build_config(meta: dict, input_dir: str, output_pdf: str) -> dict:
    """Turn the wizard's flat metadata into the compiler's config schema."""
    def sign(role):
        r = meta.get(role) or {}
        return {"role_en": r.get("role_en", ""), "initials": r.get("initials", "")}

    cfg = {
        "ref_no": meta.get("ref_no", ""),
        "version": meta.get("version", "00"),
        "mts_ref_no": meta.get("mts_ref_no", ""),
        "date": meta.get("date", ""),
        "project_title_en": meta.get("project_title_en", ""),
        "project_title_ar": meta.get("project_title_ar", ""),
        "company_name_ar": meta.get("company_name_ar", ""),
        "client": meta.get("client", ""),
        "building": meta.get("building", ""),
        "template": "material-submittal",
        "client_logo": "",
        "signoff": {
            "prepared_by": sign("prepared_by"),
            "checked_by": sign("checked_by"),
            "approved_by": sign("approved_by"),
        },
        "revision": {
            "author": (meta.get("revision") or {}).get("author", ""),
            "remarks": (meta.get("revision") or {}).get("remarks", "Issued for approval"),
        },
        "input_dir": input_dir,
        "output_pdf": output_pdf,
        "render_engine": "auto",
        "missing_section_mode": "placeholder",
        "placeholder_note": "To be submitted / Certificate to follow",
        "normalize_appended": True,
        "drawing_fit": meta.get("drawing_fit", "auto"),  # fit every page onto A4
    }
    return cfg


def _materialize(session: str, items: list[dict]) -> str:
    """Copy each already-uploaded blob (referenced by id) into
    compiler/<n>-<title>/ inside the session input dir, per its section."""
    sdir = os.path.join(SESSIONS_DIR, session)
    input_dir = os.path.join(sdir, "input")
    if os.path.isdir(input_dir):
        shutil.rmtree(input_dir)
    os.makedirs(input_dir, exist_ok=True)

    # pre-create a folder for every section so naming is stable
    folders = {}
    for s in SECTIONS:
        folder = os.path.join(input_dir, f"{s['prefix']}-{_safe(s['en'])[:40]}")
        os.makedirs(folder, exist_ok=True)
        folders[s["no"]] = folder

    for it in items:
        fid = it.get("id", "")
        if not re.fullmatch(r"[A-Za-z0-9]{8,40}", fid):
            continue
        src = os.path.join(UPLOADS_DIR, fid)
        target = folders.get(int(it.get("section", 0)))
        if target is None or not os.path.isfile(src):
            continue
        shutil.copyfile(src, os.path.join(target, _safe(it.get("name", "file"))))
    return input_dir


def _manifest_summary(manifest: dict) -> dict:
    secs = []
    for s in manifest["sections"]:
        if s["kind"] == SPEC.TABLE:
            detail = os.path.basename(s["xlsx"]) if s["xlsx"] else None
        else:
            parts = []
            if s["pdfs"]:
                parts.append(f"{len(s['pdfs'])} pdf")
            if s["docx"]:
                parts.append(f"{len(s['docx'])} docx")
            detail = ", ".join(parts) if parts else None
        secs.append(dict(no=s["no"], en=s["en"], kind=s["kind"],
                         optional=s["optional"], status=s["status"], detail=detail))
    return dict(sections=secs, warnings=manifest["warnings"], errors=manifest["errors"],
                report=DISC.format_report(manifest))


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@app.get("/api/template")
def api_template():
    return {"sections": SECTIONS}


@app.post("/api/classify")
async def api_classify(payload: dict):
    names = payload.get("names", [])
    return {"suggestions": [dict(name=n, **classify(n)) for n in names]}


@app.post("/api/files")
def api_files(files: list[UploadFile] = File(...)):
    """Store uploaded file bytes in the blob store and return their ids. Called in
    the background as the user adds files, so the bytes are uploaded once, up front."""
    out = []
    for up in files:
        fid = uuid.uuid4().hex
        dest = os.path.join(UPLOADS_DIR, fid)
        with open(dest, "wb") as fh:
            shutil.copyfileobj(up.file, fh)
        out.append({"id": fid, "name": up.filename, "size": os.path.getsize(dest)})
    return {"files": out}


@app.post("/api/session")
def api_session(config: str = Form(...), manifest: str = Form(...)):
    """Build a session from a lightweight manifest of already-uploaded blobs
    ([{id, section, name}]) — no file bytes here, so this is fast."""
    try:
        meta = json.loads(config)
        items = json.loads(manifest)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(400, "config/manifest is not valid JSON")
    if not isinstance(items, list):
        raise HTTPException(400, "manifest must be a list")

    sid = uuid.uuid4().hex
    sdir = os.path.join(SESSIONS_DIR, sid)
    os.makedirs(sdir, exist_ok=True)
    with open(os.path.join(sdir, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    _materialize(sid, items)
    return {"session": sid, "files": len(items)}


@app.get("/api/session/{sid}/validate")
def api_validate(sid: str):
    sdir = _session_dir(sid)
    input_dir = os.path.join(sdir, "input")
    template = SPEC.resolve_template({})
    manifest = DISC.discover(input_dir, template["sections"])
    return _manifest_summary(manifest)


@app.post("/api/session/{sid}/compile")
def api_compile(sid: str):
    sdir = _session_dir(sid)
    input_dir = os.path.join(sdir, "input")
    with open(os.path.join(sdir, "meta.json"), encoding="utf-8") as fh:
        meta = json.load(fh)

    output_pdf = os.path.join(sdir, "submittal.pdf")
    cfg = _build_config(meta, input_dir, output_pdf)

    cfg_errs = BUILD.validate_config(cfg)
    if cfg_errs:
        return JSONResponse(status_code=422, content={"ok": False, "config_errors": cfg_errs})

    template = SPEC.resolve_template(cfg)
    manifest = DISC.discover(input_dir, template["sections"])
    if manifest["errors"]:
        return JSONResponse(status_code=422, content={
            "ok": False, "errors": manifest["errors"],
            "summary": _manifest_summary(manifest),
        })

    try:
        qa = ASM.build(manifest, cfg, template)
    except Exception as exc:  # surface compiler failures to the UI
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})

    return {
        "ok": True,
        "qa": {
            "pages": qa["actual_pages"],
            "expected_pages": qa["expected_pages"],
            "consistent": qa["consistent"],
            "engines": list(qa["engines"]),
            "page_map": {str(k): v for k, v in qa["page_map"].items()},
        },
        "download": f"/api/session/{sid}/download",
    }


@app.get("/api/session/{sid}/download")
def api_download(sid: str):
    sdir = _session_dir(sid)
    pdf = os.path.join(sdir, "submittal.pdf")
    if not os.path.isfile(pdf):
        raise HTTPException(404, "not generated yet")
    with open(os.path.join(sdir, "meta.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    ref = (meta.get("ref_no") or "submittal").replace("/", "-")
    ver = meta.get("version", "00")
    return FileResponse(pdf, media_type="application/pdf",
                        filename=f"{ref} v.{ver} PAS.pdf")


# --------------------------------------------------------------------------- #
# Static wizard UI (mounted last so /api/* wins)
# --------------------------------------------------------------------------- #
STATIC_DIR = os.path.join(HERE, "static")


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as fh:
        return fh.read()


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
# Serve the brand logo straight from the compiler's assets, if present.
_assets = os.path.join(COMPILER_DIR, "assets")
if os.path.isdir(_assets):
    app.mount("/assets", StaticFiles(directory=_assets), name="assets")
