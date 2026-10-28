import os, io, re, uuid, time
from datetime import timedelta
from functools import wraps

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from dotenv import load_dotenv
from supabase import create_client
from google import genai
from pypdf import PdfReader
from docx import Document as DocxDocument

from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE, override=True)
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "CHANGE_THIS_SECRET_BEFORE_DEPLOYING")
app.permanent_session_lifetime = timedelta(hours=8)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
BUCKET = os.getenv("SUPABASE_BUCKET", "department-documents")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY) if SUPABASE_URL and SUPABASE_SERVICE_KEY else None
gemini = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "csv"}
CACHE = {}
CACHE_SECONDS = 90

def allowed_file(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_user"):
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper

def sanitize_text(text: str) -> str:
    """Remove invalid Unicode surrogate characters."""
    return text.encode("utf-8", errors="replace").decode("utf-8")

def extract_text(filename, raw):
    ext = filename.rsplit(".", 1)[1].lower()
    try:
        if ext == "pdf":
            reader = PdfReader(io.BytesIO(raw))
            return "\n".join((page.extract_text() or "") for page in reader.pages)[:250000]
        if ext == "docx":
            doc = DocxDocument(io.BytesIO(raw))
            return "\n".join(p.text for p in doc.paragraphs)[:250000]
        return raw.decode("utf-8", errors="replace")[:250000]
    except Exception as exc:
        raise ValueError(f"Could not read this file: {exc}")

def get_documents(published_only=True):
    if not supabase:
        return []
    q = supabase.table("documents").select("id,name,category,content,created_at,status,storage_path").order("created_at", desc=True)
    if published_only:
        q = q.eq("status", "published")
    return q.execute().data or []

def get_notices(published_only=True):
    if not supabase:
        return []
    q = supabase.table("notices").select("id,title,body,category,published,created_at").order("created_at", desc=True)
    if published_only:
        q = q.eq("published", True)
    return q.execute().data or []

def retrieve_context(question, limit=5):
    """Small dependency-light lexical retrieval. No embeddings/API call is required."""
    docs = get_documents(True)
    notices = get_notices(True)
    terms = set(re.findall(r"[a-zA-Z0-9]{2,}", question.lower()))
    ranked = []
    for d in docs:
        content = d.get("content") or ""
        haystack = (d.get("name", "") + " " + d.get("category", "") + " " + content).lower()
        score = sum(1 for t in terms if t in haystack)
        if score:
            # Return only matching snippets to keep prompts small.
            chunks = re.split(r"(?<=[.!?])\s+|\n+", content)
            matching = [c.strip() for c in chunks if any(t in c.lower() for t in terms)]
            excerpt = " ".join(matching[:12])[:3500] or content[:1500]
            ranked.append((score, f"DOCUMENT: {d['name']} (category: {d.get('category','')})\n{excerpt}"))
    for n in notices:
        text = f"{n.get('title','')}\n{n.get('body','')}"
        score = sum(1 for t in terms if t in text.lower())
        if score:
            ranked.append((score + 1, f"NOTICE: {n['title']}\n{n['body']}"))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return "\n\n---\n\n".join(x[1] for x in ranked[:limit]), bool(ranked)

def find_relevant_pdfs(question, limit=3):
    """Find published PDF documents relevant to a student's question."""
    docs = get_documents(published_only=True)

    terms = set(re.findall(r"[a-zA-Z0-9]{2,}", question.lower()))
    ranked = []

    for doc in docs:
        name = doc.get("name", "")
        storage_path = doc.get("storage_path") or ""

        # Only return PDF documents.
        if not (
            name.lower().endswith(".pdf")
            or storage_path.lower().endswith(".pdf")
        ):
            continue

        content = doc.get("content") or ""
        searchable_text = (
            name + " " + doc.get("category", "") + " " + content
        ).lower()

        score = sum(1 for term in terms if term in searchable_text)

        if score > 0:
            ranked.append({
                "id": doc["id"],
                "name": name,
                "category": doc.get("category", "General"),
                "score": score,
            })

    ranked.sort(key=lambda doc: doc["score"], reverse=True)

    # Return only document information needed by the chat interface.
    return [
        {
            "id": doc["id"],
            "name": doc["name"],
            "category": doc["category"],
        }
        for doc in ranked[:limit]
    ]

def deterministic_answer(question, context, has_context):
    q = question.lower().strip()
    if re.fullmatch(r"(hi|hello|hey|hii|good morning|good afternoon|good evening)[!. ]*", q):
        return "Hello! 😊 I'm InfoMate, your Computer Department academic assistant. You can ask me about timetables, exam dates, notices, syllabi, and academic schedules."
    if any(x in q for x in ["what can you do", "help me", "what can i ask"]):
        return "I can help you find department information such as timetables, examination dates, academic calendars, notices, syllabi, and course details. Try one of the suggestion buttons or ask a specific question."
    if not has_context:
        return "I couldn't find this information in the currently published department documents or notices. Please try different keywords or check with the department office. I won't guess academic dates or room numbers."
    return None

def answer_question(question):
    key = question.strip().lower()
    now = time.time()
    if key in CACHE and now - CACHE[key][0] < CACHE_SECONDS:
        return CACHE[key][1], "cache"
    context, found = retrieve_context(question)
    fallback = deterministic_answer(question, context, found)
    if fallback:
        CACHE[key] = (now, fallback)
        return fallback, "local"
    if not gemini:
        result = "I found potentially relevant department information, but the AI service is not configured. Please ask the admin to check the Gemini API key. Relevant source snippets:\n\n" + context[:1800]
        return result, "retrieval"
    prompt = f"""You are InfoMate, a Computer Department academic assistant.
Answer using ONLY the approved department sources below. Never invent dates, seat numbers, rooms, schedules, or policies.
If the sources do not answer the question, say that the information is not available in the published sources.
Be concise, friendly, and clear. For a greeting, greet the student and suggest what they can ask.
QUESTION: {question}

APPROVED DEPARTMENT SOURCES:
{context[:12000]}
"""
    try:
        response = gemini.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        result = (response.text or "").strip()
        if not result:
            result = "I couldn't generate a response just now. Please try again."
        CACHE[key] = (now, result)
        return result, "gemini"
    except Exception:
        app.logger.exception(
            "Gemini generation failed; using source fallback"
        )
     
        if found and context.strip():
            result = (
                "Here is the relevant information from the department's published documents. "
                "The AI assistant is temporarily unavailable, so I'm showing the source information directly:\n\n"
                + context[:5000]
                + "\n\nPlease verify important dates and instructions against the official document."
            )
            CACHE[key] = (now, result)
            return result, "source_fallback"
        # Do not invent an answer when no matching approved source was found.
        return (
            "I couldn't find a relevant answer in the published department documents or notices. "
            "Please try different keywords or check with the department office.",
            "no_source"
        )

@app.get("/")
def home():
    try:
        notices = get_notices(True)[:5]
    except Exception:
        notices = []
    return render_template("index.html", notices=notices)

@app.get("/chat")
def chat_page():
    return render_template("chat.html")

@app.post("/api/chat")

def chat_api():
    data = request.get_json(silent=True) or {}
    question = (data.get("message") or "").strip()

    if not question:
        return jsonify({
            "answer": "Please type a question first.",
            "source": "local",
            "documents": []
        })

    if len(question) > 1200:
        return jsonify({
            "answer": "Please keep your question under 1,200 characters.",
            "source": "local",
            "documents": []
        }), 400

    try:
        answer, source = answer_question(question)

        # Find PDFs related to the student's question.
        try:
            documents = find_relevant_pdfs(question)
        except Exception:
            app.logger.exception("PDF lookup failed")
            documents = []

        return jsonify({
            "answer": answer,
            "source": source,
            "documents": documents
        })

    except Exception:
        app.logger.exception("Chat request failed")
        return jsonify({
            "answer": "I couldn't access department information right now. Please try again later.",
            "source": "fallback",
            "documents": []
        }), 500
@app.get("/api/documents/<document_id>/open")
def open_published_pdf(document_id):
    """Allow students to open published PDFs using temporary signed URLs."""

    if not supabase:
        return jsonify({"error": "Document storage is unavailable."}), 503

    try:
        result = (
            supabase.table("documents")
            .select("id, name, status, storage_path")
            .eq("id", document_id)
            .eq("status", "published")
            .single()
            .execute()
        )

        doc = result.data

        if not doc:
            return jsonify({"error": "Document not found."}), 404

        name = doc.get("name", "")
        storage_path = doc.get("storage_path") or ""

        # Prevent this route from opening non-PDF documents.
        if not (
            name.lower().endswith(".pdf")
            or storage_path.lower().endswith(".pdf")
        ):
            return jsonify({"error": "This document is not a PDF."}), 404

        if not storage_path:
            return jsonify({"error": "PDF file is unavailable."}), 404

        signed = supabase.storage.from_(BUCKET).create_signed_url(
            storage_path, 300
        )

        url = signed.get("signedURL") or signed.get("signedUrl")

        if not url:
            return jsonify({"error": "Could not create a PDF link."}), 500

        return redirect(url)

    except Exception:
        app.logger.exception("Published PDF opening failed")
        return jsonify({"error": "Could not open this PDF right now."}), 500
@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "supabase_configured": bool(supabase),
        "gemini_configured": bool(gemini),
        "gemini_model": GEMINI_MODEL,
        "note": "This checks configuration presence, not full provider authentication."
    })

@app.route("/admin", methods=["GET"])
def admin_login():
    if session.get("admin_user"):
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_login.html")

@app.post("/admin/login")
def admin_login_post():
    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        flash("Supabase Auth is not configured. Check server environment variables.", "error")
        return redirect(url_for("admin_login"))
    try:
        # Use the public/anon key for user sign-in; the service role remains server-only.
        auth_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        result = auth_client.auth.sign_in_with_password({"email": email, "password": password})
        user = result.user
        if not user:
            raise ValueError("Sign-in did not return a user.")
        profile = supabase.table("profiles").select("role,active").eq("id", user.id).maybe_single().execute().data
        if not profile or profile.get("active") is False or profile.get("role") not in ("super_admin", "admin", "coordinator", "faculty"):
            auth_client.auth.sign_out()
            flash("This account is not authorized to access the admin portal.", "error")
            return redirect(url_for("admin_login"))
        session.clear()
        session.permanent = True
        session["admin_user"] = {"id": user.id, "email": user.email, "role": profile["role"]}
        return redirect(url_for("admin_dashboard"))
    except Exception:
        flash("Sign-in failed. Check your email/password and confirm that the account has an authorized profile.", "error")
        return redirect(url_for("admin_login"))

@app.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))

@app.get("/admin/dashboard")
@admin_required
def admin_dashboard():
    try:
        docs = supabase.table("documents").select("id,name,category,status,created_at,storage_path").order("created_at", desc=True).execute().data or []
        notices = supabase.table("notices").select("id,title,category,published,created_at").order("created_at", desc=True).execute().data or []
        db_error = None
    except Exception as exc:
        docs, notices, db_error = [], [], str(exc)
    return render_template("admin_dashboard.html", docs=docs, notices=notices, db_error=db_error, admin=session["admin_user"], ai_ready=bool(gemini))

@app.post("/admin/documents")
@admin_required
def upload_document():
    file = request.files.get("file")
    category = (request.form.get("category") or "General").strip()[:80]
    if not file or not file.filename:
        flash("Choose a file first.", "error")
        return redirect(url_for("admin_dashboard"))
    if not allowed_file(file.filename):
        flash("Allowed formats: PDF, DOCX, TXT, CSV.", "error")
        return redirect(url_for("admin_dashboard"))
    filename = os.path.basename(file.filename).replace("/", "_").replace("\\", "_")
    raw = file.read()
    try:
        content = sanitize_text(extract_text(filename, raw))
        if not content.strip():
            flash("No readable text was found. Scanned PDFs may need OCR before upload.", "error")
            return redirect(url_for("admin_dashboard"))
        document_id = str(uuid.uuid4())
        storage_path = f"{document_id}/{filename}"
        supabase.storage.from_(BUCKET).upload(storage_path, raw, {"content-type": file.mimetype or "application/octet-stream", "upsert": "false"})
        supabase.table("documents").insert({
            "id": document_id, "name": filename, "category": category,
            "content": content, "status": "published", "storage_path": storage_path,
            "uploaded_by": session["admin_user"]["id"]
        }).execute()
        CACHE.clear()
        flash(f"{filename} uploaded and indexed successfully.", "success")
    except Exception as exc:
        app.logger.exception("Document upload failed")
        flash("Upload failed. Check Supabase bucket, database migration, file size, and server logs. No API key is needed for basic text extraction.", "error")
    return redirect(url_for("admin_dashboard"))

@app.get("/admin/documents/<document_id>/open")
@admin_required
def open_document(document_id):
    try:
        row = supabase.table("documents").select("storage_path,name").eq("id", document_id).single().execute().data
        signed = supabase.storage.from_(BUCKET).create_signed_url(row["storage_path"], 300)
        url = signed.get("signedURL") or signed.get("signedUrl")
        if not url:
            flash("Could not create a temporary file link.", "error")
            return redirect(url_for("admin_dashboard"))
        return redirect(url)
    except Exception:
        flash("Could not open the file. Check that the storage object exists.", "error")
        return redirect(url_for("admin_dashboard"))

@app.post("/admin/documents/<document_id>/delete")
@admin_required
def delete_document(document_id):
    try:
        row = supabase.table("documents").select("storage_path").eq("id", document_id).single().execute().data
        if row.get("storage_path"):
            try:
                supabase.storage.from_(BUCKET).remove([row["storage_path"]])
            except Exception:
                app.logger.warning("Storage deletion failed; continuing with database deletion.")
        supabase.table("documents").delete().eq("id", document_id).execute()
        CACHE.clear()
        flash("Document deleted.", "success")
    except Exception:
        app.logger.exception("Document deletion failed")
        flash("Could not delete this document. Check Supabase permissions and server logs.", "error")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/notices")
@admin_required
def add_notice():
    title = (request.form.get("title") or "").strip()[:180]
    body = (request.form.get("body") or "").strip()[:12000]
    category = (request.form.get("category") or "General").strip()[:80]
    published = request.form.get("published") == "on"
    if not title or not body:
        flash("Notice title and content are required.", "error")
        return redirect(url_for("admin_dashboard"))
    try:
        supabase.table("notices").insert({"title": title, "body": body, "category": category, "published": published, "created_by": session["admin_user"]["id"]}).execute()
        CACHE.clear()
        flash("Notice saved.", "success")
    except Exception:
        app.logger.exception("Notice creation failed")
        flash("Could not save notice. Check the database migration.", "error")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/notices/<notice_id>/delete")
@admin_required
def delete_notice(notice_id):
    try:
        supabase.table("notices").delete().eq("id", notice_id).execute()
        CACHE.clear()
        flash("Notice deleted.", "success")
    except Exception:
        flash("Could not delete notice.", "error")
    return redirect(url_for("admin_dashboard"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
