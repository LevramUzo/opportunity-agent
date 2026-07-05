import os
import json
import re
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
from tavily import TavilyClient
from database import get_db, hash_password, verify_password

# ─── API KEYS ───
TAVILY_KEY = os.getenv("TAVILY_API_KEY")
tavily = TavilyClient(api_key=TAVILY_KEY) if TAVILY_KEY else None

# ─── APP SETUP ───
app = FastAPI(title="Opportunity Intelligence Agent")
app.add_middleware(SessionMiddleware, secret_key="your-secret-key-change-this-in-production")
templates = Jinja2Templates(directory="templates")

# ─── KEYWORD DETECTION ───
TYPE_KEYWORDS = {
    "scholarship": ["scholarship", "scholarships", "fully funded", "full tuition"],
    "fellowship": ["fellowship", "fellowships", "research fellowship"],
    "internship": ["internship", "internships", "research intern"],
    "grant": ["grant", "grants", "funding opportunity"],
}

DEADLINE_PATTERNS = [
    r'deadline[:\s]*([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
    r'(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})',
    r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})',
]

FUNDING_PATTERNS = [
    r'(\$\d{1,3}(?:,\d{3})*)',
    r'(£\d{1,3}(?:,\d{3})*)',
    r'(€\d{1,3}(?:,\d{3})*)',
    r'(full tuition)',
    r'(fully funded)',
    r'(stipend)',
    r'(up to\s+\$\d+)',
]

# ─── EXTRACTION FUNCTIONS ───
def detect_type(title, content):
    text = f"{title} {content}".lower()
    for opp_type, keywords in TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return opp_type
    return "opportunity"

def extract_deadline(content):
    for pattern in DEADLINE_PATTERNS:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return match.group(1)
    return "Not specified"

def extract_funding(title, content):
    text = f"{title} {content}"
    for pattern in FUNDING_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    if "fully funded" in text.lower() or "full tuition" in text.lower():
        return "Fully funded"
    if "stipend" in text.lower():
        return "Includes stipend"
    return "Not specified"

def extract_eligibility(content):
    text = content.lower()
    eligibility = []
    checks = [
        ("African nationals", ["african", "africa"]),
        ("Nigerian citizens", ["nigerian", "nigeria"]),
        ("STEM background", ["stem", "physics", "computer science"]),
        ("Graduate students", ["graduate", "master", "phd"]),
        ("AI/ML focus", ["artificial intelligence", "machine learning", "ai", "ml"]),
    ]
    for label, keywords in checks:
        for kw in keywords:
            if kw in text:
                eligibility.append(label)
                break
    return eligibility if eligibility else ["See website"]

def calculate_relevance(title, content, profile):
    text = f"{title} {content}".lower()
    score = 0.5
    if profile["nationality"].lower() in text:
        score += 0.15
    if any(w in text for w in ["ai", "machine learning", "artificial intelligence"]):
        score += 0.15
    if "physics" in text or "stem" in text:
        score += 0.1
    if profile["status"].lower() in text:
        score += 0.1
    return min(score, 1.0)

def generate_match_reason(title, content, profile):
    reasons = []
    text = f"{title} {content}".lower()
    if profile["nationality"].lower() in text:
        reasons.append(f"open to {profile['nationality']} applicants")
    if "stem" in text or "physics" in text:
        reasons.append("STEM background relevant")
    if any(w in text for w in ["ai", "machine learning"]):
        reasons.append("AI/ML focus matches")
    if "africa" in text or "african" in text:
        reasons.append("African-focused program")
    if reasons:
        return "Matches because: " + ", ".join(reasons)
    return "General opportunity matching your profile"

# ─── SEARCH FUNCTION ───
def search_opportunities(profile):
    base = f"{profile['nationality']} {profile['education']} {profile['field']} {profile['status']}"
    queries = [
        f"scholarships for {base} 2026",
        f"fellowships for African students {profile['field']} 2026",
        f"internships {profile['field']} remote graduates 2026",
        f"grants for {profile['status']} members technology Nigeria 2026",
        f"Google DeepMind scholarship African students 2026",
        f"Mastercard Foundation scholarship STEM Africa 2026",
    ]
    
    all_results = []
    for query in queries:
        try:
            response = tavily.search(query=query, max_results=3, search_depth="advanced")
            all_results.extend(response.get("results", []))
        except Exception:
            continue
    
    seen = set()
    unique = []
    for r in all_results:
        url = r.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique.append(r)
    
    return unique

def process_results(raw_results, profile):
    opportunities = []
    for r in raw_results:
        title = r.get("title", "Unknown")
        url = r.get("url", "")
        content = r.get("content", "")
        
        skip_words = ["news", "article", "blog", "wikipedia", "reddit", "quora", "youtube"]
        if any(w in title.lower() for w in skip_words):
            continue
        if len(content) < 100:
            continue
        
        opp = {
            "title": title,
            "organization": url.split("/")[2].replace("www.", "") if url else "Unknown",
            "type": detect_type(title, content),
            "deadline": extract_deadline(content),
            "funding": extract_funding(title, content),
            "eligibility": extract_eligibility(content),
            "description": content[:250] + "..." if len(content) > 250 else content,
            "url": url,
            "relevance_score": round(calculate_relevance(title, content, profile), 2),
            "match_reason": generate_match_reason(title, content, profile),
        }
        opportunities.append(opp)
    
    opportunities.sort(key=lambda x: x["relevance_score"], reverse=True)
    return opportunities

# ─── AUTH HELPERS ───
def get_current_user(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None

# ─── ROUTES ───
@app.get("/", response_class=HTMLResponse)
def home(request: Request, user: dict = Depends(get_current_user)):
    if user:
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={"user": user}
        )
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )

@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="signup.html",
        context={}
    )

@app.post("/signup")
def signup(request: Request, email: str = Form(...), password: str = Form(...), 
           name: str = Form(...), nationality: str = Form(...), 
           education: str = Form(...), field: str = Form(...), 
           status: str = Form(...)):
    
    conn = get_db()
    cursor = conn.cursor()
    
    existing = cursor.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")
    
    password_hash = hash_password(password)
    cursor.execute("""
        INSERT INTO users (email, password_hash, name, nationality, education, field, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (email, password_hash, name, nationality, education, field, status))
    
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    
    request.session["user_id"] = user_id
    return RedirectResponse(url="/", status_code=302)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={}
    )

@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    request.session["user_id"] = user["id"]
    return RedirectResponse(url="/", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)

@app.post("/search")
def search(request: Request, user: dict = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    if not tavily:
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"message": "TAVILY_API_KEY not set."}
        )
    
    profile = {
        "nationality": user["nationality"],
        "education": user["education"],
        "field": user["field"],
        "status": user["status"],
    }
    
    raw = search_opportunities(profile)
    opportunities = process_results(raw, profile)
    
    request.session["last_results"] = json.dumps(opportunities)
    
    return templates.TemplateResponse(
        request=request,
        name="results.html",
        context={
            "opportunities": opportunities,
            "count": len(opportunities),
            "user": user
        }
    )

@app.get("/results", response_class=HTMLResponse)
def view_results(request: Request, user: dict = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    results_json = request.session.get("last_results", "[]")
    opportunities = json.loads(results_json)
    
    return templates.TemplateResponse(
        request=request,
        name="results.html",
        context={
            "opportunities": opportunities,
            "count": len(opportunities),
            "user": user
        }
    )

@app.post("/save")
def save_opportunity(request: Request, title: str = Form(...), organization: str = Form(None),
                     type: str = Form(None), deadline: str = Form(None), funding: str = Form(None),
                     eligibility: str = Form(None), description: str = Form(None),
                     url: str = Form(...), relevance_score: float = Form(0),
                     match_reason: str = Form(None), user: dict = Depends(get_current_user)):
    
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    conn = get_db()
    conn.execute("""
        INSERT INTO saved_opportunities 
        (user_id, title, organization, type, deadline, funding, eligibility, description, url, relevance_score, match_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user["id"], title, organization, type, deadline, funding, 
          eligibility, description, url, relevance_score, match_reason))
    conn.commit()
    conn.close()
    
    return {"status": "saved"}

@app.get("/saved", response_class=HTMLResponse)
def saved_opportunities(request: Request, user: dict = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM saved_opportunities 
        WHERE user_id = ? 
        ORDER BY saved_at DESC
    """, (user["id"],)).fetchall()
    conn.close()
    
    saved = [dict(row) for row in rows]
    
    return templates.TemplateResponse(
        request=request,
        name="saved.html",
        context={"saved": saved, "user": user, "count": len(saved)}
    )

@app.get("/edit-profile", response_class=HTMLResponse)
def edit_profile_page(request: Request, user: dict = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="edit_profile.html",
        context={"user": user}
    )

@app.post("/edit-profile")
def edit_profile(request: Request, name: str = Form(...), nationality: str = Form(...),
                 education: str = Form(...), field: str = Form(...), status: str = Form(...),
                 user: dict = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    
    conn = get_db()
    conn.execute("""
        UPDATE users SET name = ?, nationality = ?, education = ?, field = ?, status = ?
        WHERE id = ?
    """, (name, nationality, education, field, status, user["id"]))
    conn.commit()
    conn.close()
    
    return RedirectResponse(url="/", status_code=302)

# ─── RUN ───
if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 8000))
    print("🌐 Starting Opportunity Intelligence Web App")
    print(f"   Running on port {port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port)