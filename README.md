# InfoMate — Computer Department Academic Assistant

A Flask + Supabase + Gemini starter application with:
- Public student chatbot (no student login)
- Separate Supabase Auth admin login
- Admin upload, view/open, and delete files without using the Supabase dashboard
- Notice creation and deletion
- PDF/DOCX/TXT/CSV text extraction
- Lightweight keyword retrieval that works without embeddings
- Optional Gemini answer generation with fallback when Gemini is unavailable
- Dark navy UI with purple/pink accents inspired by the provided screenshots

## Important notes
1. This is a starter project. Test it with non-sensitive sample documents before using real student records.
2. A 401 `API key not valid` is a credential problem, not an agent-availability problem. Generate a valid Gemini API key, update the environment variable, and redeploy. Creating a new API key in code will not fix a restricted Google project.
3. This project intentionally does not call Gemini embeddings during upload. Upload and basic text retrieval therefore do not depend on Gemini being available.
4. Scanned PDFs without a text layer are not OCR'd. Convert them to searchable PDFs or add OCR later.
5. Supabase service-role key is server-side only. Never commit `.env` or expose that key in HTML/JavaScript.
6. Student questions are grounded in published documents/notices; the assistant is instructed not to invent academic dates or seat numbers.

## A. Create Supabase project
1. Open https://supabase.com and create a project.
2. In Project Settings → API, copy the Project URL, publishable/anon key, and service_role/secret key.
3. Open SQL Editor, create a query, paste `migrations/001_schema.sql`, and run it.
4. Go to Storage and create a **private** bucket named `department-documents`.
5. In Authentication → Users, create the first administrator user with email and password.
6. Copy that user's UUID. In SQL Editor run the following, replacing values:
   ```sql
   insert into public.profiles (id, email, role, active)
   values ('PASTE-AUTH-USER-UUID-HERE', 'admin@example.com', 'super_admin', true)
   on conflict (id) do update set role = 'super_admin', active = true;
   ```
7. Keep the bucket private. File opening uses a short-lived signed URL.

## B. Configure locally (Windows PowerShell)
Use Python 3.12 for compatibility. In the extracted project folder:
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```
Edit `.env` and fill every Supabase value plus a valid Gemini API key. Create a long random `FLASK_SECRET_KEY`. Do not include quotes around values unless needed.

If PowerShell blocks activation, run this for the current terminal only:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```
Alternative without activation:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```
Start:
```powershell
python app.py
```
Open http://127.0.0.1:5000. Admin portal: http://127.0.0.1:5000/admin. Health: http://127.0.0.1:5000/health.

## C. Test before deployment
- Landing page loads.
- Chat says hello to `hi` even if Gemini key is missing.
- Ask a question that matches an uploaded document.
- Upload a PDF/DOCX/TXT/CSV in admin portal.
- Open and delete a sample document from the admin dashboard.
- Create and delete a sample notice.
- `/health` should show whether Supabase and Gemini environment values are present. This is not a full authentication test.

## D. Create GitHub repository
1. Create a new repository called `infomate-department-chatbot`.
2. Keep it private if it contains college-specific material.
3. Extract this ZIP; do not add `.env` or real credentials.
4. In PowerShell in the project folder:
   ```powershell
   git init
   git add .
   git commit -m "Initial InfoMate department chatbot"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/infomate-department-chatbot.git
   git push -u origin main
   ```
5. If Git asks you to sign in, use GitHub's browser authentication flow. Never paste tokens into source code.

## E. Deploy on Render
1. Open https://render.com and connect your GitHub account.
2. Choose New → Web Service and select your repository.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Add environment variables from `.env` in Render → Environment. Do not upload `.env` to GitHub.
6. Deploy. Open the Render URL and `/health`.
7. Every push to the connected branch can trigger a redeploy.

## F. Fixing Gemini errors
### 401 UNAUTHENTICATED / API key not valid
- Generate a fresh key in Google AI Studio: https://aistudio.google.com/app/apikey
- Confirm the key is for the Gemini API and its Google project is eligible to use the API.
- If a key was exposed in a public repository or blocked, replace it.
- Update `GEMINI_API_KEY` locally and in Render's Environment settings, then restart/redeploy.
- Check `GEMINI_MODEL` is a model currently available to your API key. If `gemini-3.8-flash` is unavailable in your account, choose a supported text-generation model shown by the current model list.
- Do not keep retrying a 401. Retries cannot fix invalid credentials.
- The app does not use embeddings during upload, so a bad key should not prevent document uploads or greetings.

### 503 UNAVAILABLE / 429 rate limit
- These are often transient capacity or quota issues. Wait and retry with backoff; do not spam requests.
- The UI receives a friendly message instead of a server crash.
- Student greetings and keyword-based source retrieval do not require Gemini.
- Review usage/quota in Google AI Studio. A new key in the same restricted project may not restore eligibility.

### If chatbot says “information not found”
- Verify that the file is uploaded and visible in the admin dashboard.
- Ensure the document status is `published`.
- Text extraction does not work for image-only/scanned PDFs.
- Ask using terms present in the document (e.g., “SY timetable” rather than “when are classes?”). This starter uses keyword retrieval, not semantic embeddings.

## Security checklist
- Keep `.env` private.
- Keep the Supabase service-role key only on Flask server/Render.
- Use a strong `FLASK_SECRET_KEY`.
- Keep Storage bucket private.
- Create admin users only through Supabase Auth and add their IDs to `profiles`.
- For production, add CSRF protection, audit logging, rate limiting, and automated backups before handling sensitive data.
