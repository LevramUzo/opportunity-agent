from dotenv import load_dotenv
load_dotenv()  # Loads .env file automatically
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
GROQ_KEY = os.getenv("GROQ_API_KEY")

tavily = TavilyClient(api_key=TAVILY_KEY) if TAVILY_KEY else None

# ─── APP SETUP ───
app = FastAPI(title="Opportunity Intelligence Agent")
app.add_middleware(SessionMiddleware, secret_key="your-secret-key-change-this-in-production")
templates = Jinja2Templates(directory="templates")

# ─── KEYWORD DETECTION (Fallback) ───
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

# ─── ADAPTIVE SEARCH REFINEMENT (Agentic Layer) ───
REFINEMENT_TRIGGERS = {
    "low_count": 3,           # Fewer than 3 results triggers refinement
    "low_confidence": 0.6,    # Avg relevance below 0.6 triggers refinement
    "max_rounds": 2,          # Maximum search rounds (initial + 1 refinement)
}

def evaluate_search_quality(opportunities: list) -> dict:
    """
    Evaluate the quality of search results.
    Returns dict with quality metrics and whether refinement is needed.
    """
    if not opportunities:
        return {"needs_refinement": True, "reason": "no_results", "avg_score": 0.0, "count": 0}

    count = len(opportunities)
    scores = [opp.get("relevance_score", 0) for opp in opportunities]
    avg_score = sum(scores) / len(scores) if scores else 0
    high_confidence = sum(1 for s in scores if s >= 0.7)

    quality = {
        "count": count,
        "avg_score": round(avg_score, 2),
        "high_confidence": high_confidence,
        "needs_refinement": False,
        "reason": None,
    }

    if count < REFINEMENT_TRIGGERS["low_count"]:
        quality["needs_refinement"] = True
        quality["reason"] = f"only_{count}_results"
    elif avg_score < REFINEMENT_TRIGGERS["low_confidence"]:
        quality["needs_refinement"] = True
        quality["reason"] = f"low_avg_score_{avg_score:.2f}"
    elif high_confidence < 2:
        quality["needs_refinement"] = True
        quality["reason"] = f"only_{high_confidence}_high_confidence"

    return quality

def generate_refined_queries(profile: dict, original_queries: list, opportunities: list) -> list:
    """
    Generate refined search queries based on what we learned from initial results.
    This is where the agentic decision-making happens.
    """
    nationality = profile["nationality"]
    education = profile["education"]
    field = profile["field"]
    status = profile["status"]

    # Analyze what types we found vs what might be missing
    found_types = set()
    found_orgs = set()
    for opp in opportunities:
        found_types.add(opp.get("type", "opportunity"))
        org = opp.get("organization", "")
        if org and org != "Unknown":
            found_orgs.add(org.split(".")[0])

    refined = []

    # Strategy 1: Broaden by removing restrictive terms if we got few results
    if len(opportunities) < 3:
        refined.extend([
            f"{nationality} students {field} funding 2026",
            f"African students {education} {field} opportunities",
            f"{field} scholarships developing countries 2026",
        ])

    # Strategy 2: Target specific orgs if we found some but want more
    if found_orgs and len(opportunities) < 5:
        for org in list(found_orgs)[:2]:
            refined.append(f"{org} {field} {nationality} 2026")

    # Strategy 3: Try different opportunity types we haven't found
    all_types = {"scholarship", "fellowship", "internship", "grant"}
    missing_types = all_types - found_types
    for opp_type in missing_types:
        refined.append(f"{opp_type} {nationality} {field} {education} 2026")

    # Strategy 4: Geographic expansion if nationality-specific was too narrow
    if "nigerian" in nationality.lower() or "nigeria" in nationality.lower():
        refined.extend([
            f"West African students {field} scholarship 2026",
            f"Sub-Saharan Africa {field} funding",
        ])

    # Strategy 5: Status-specific searches
    if "graduate" in status.lower() or "phd" in status.lower():
        refined.extend([
            f"PhD {field} funding Africa 2026",
            f"graduate research {field} fellowship",
        ])
    elif "undergraduate" in status.lower():
        refined.extend([
            f"undergraduate {field} scholarship Africa 2026",
            f"bachelor degree {field} funding developing countries",
        ])

    # Strategy 6: Field-specific well-known programs
    field_lower = field.lower()
    if "ai" in field_lower or "machine learning" in field_lower or "artificial intelligence" in field_lower:
        refined.extend([
            "Google AI scholarship Africa 2026",
            "DeepMind scholarship African students",
            "AI4D Africa artificial intelligence funding",
        ])
    elif "physics" in field_lower:
        refined.extend([
            "IAEA fellowship physics developing countries",
            "CERN summer student programme Africa",
            "physics research grant Africa 2026",
        ])
    elif "computer" in field_lower or "software" in field_lower:
        refined.extend([
            "GitHub scholarship technology students",
            "Microsoft scholarship Africa STEM 2026",
            "coding bootcamp scholarship Africa",
        ])

    # Remove duplicates and limit
    seen = set(original_queries)
    unique_refined = []
    for q in refined:
        if q not in seen:
            seen.add(q)
            unique_refined.append(q)

    return unique_refined[:4]  # Max 4 refined queries

def adaptive_search(profile: dict, max_rounds: int = REFINEMENT_TRIGGERS["max_rounds"]) -> tuple:
    """
    Agentic search: search, evaluate quality, refine if needed, merge results.
    Returns (all_opportunities, search_metadata) where metadata includes
    info about refinement rounds for transparency.
    """
    base = f"{profile['nationality']} {profile['education']} {profile['field']} {profile['status']}"

    # Round 1: Initial search
    initial_queries = [
        f"scholarships for {base} 2026",
        f"fellowships for African students {profile['field']} 2026",
        f"internships {profile['field']} remote graduates 2026",
        f"grants for {profile['status']} members technology Nigeria 2026",
        f"Google DeepMind scholarship African students 2026",
        f"Mastercard Foundation scholarship STEM Africa 2026",
    ]

    all_raw_results = []
    all_queries_used = list(initial_queries)

    for query in initial_queries:
        try:
            response = tavily.search(query=query, max_results=3, search_depth="advanced")
            all_raw_results.extend(response.get("results", []))
        except Exception as e:
            print(f"⚠️  Tavily error for query '{query}': {e}")
            continue

    # Deduplicate by URL
    seen = set()
    unique_results = []
    for r in all_raw_results:
        url = r.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique_results.append(r)

    # Extract opportunities from round 1
    opportunities = process_results(unique_results, profile)

    # Evaluate quality
    quality = evaluate_search_quality(opportunities)

    metadata = {
        "rounds": 1,
        "initial_count": len(opportunities),
        "initial_quality": quality,
        "refined": False,
        "refinement_reason": None,
        "refined_queries": [],
        "final_count": len(opportunities),
    }

    # Round 2: Refinement if needed
    if quality["needs_refinement"] and max_rounds > 1:
        print(f"🔍 Search quality low ({quality['reason']}). Triggering adaptive refinement...")

        refined_queries = generate_refined_queries(profile, all_queries_used, opportunities)
        metadata["refined_queries"] = refined_queries

        if refined_queries:
            refined_results = []
            for query in refined_queries:
                try:
                    response = tavily.search(query=query, max_results=3, search_depth="advanced")
                    refined_results.extend(response.get("results", []))
                except Exception as e:
                    print(f"⚠️  Tavily error for refined query '{query}': {e}")
                    continue

            # Deduplicate refined results against round 1
            for r in refined_results:
                url = r.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    unique_results.append(r)

            # Re-extract from merged results
            opportunities = process_results(unique_results, profile)

            metadata["rounds"] = 2
            metadata["refined"] = True
            metadata["refinement_reason"] = quality["reason"]
            metadata["final_count"] = len(opportunities)

            print(f"✅ Adaptive search complete: {metadata['initial_count']} → {metadata['final_count']} opportunities")

    return opportunities, metadata

# ─── FALLBACK EXTRACTION (Regex-based) ───
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

def fallback_extract(raw_results, profile):
    """Extract opportunities using regex when Groq is unavailable."""
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

# ─── GROQ EXTRACTION (Primary) ───
def groq_extract(raw_results, profile):
    """Try Groq first, fall back to regex if it fails."""
    try:
        from ai_extractor import extract_with_groq
        opportunities = extract_with_groq(raw_results, profile)
        if opportunities:
            return opportunities
    except Exception as e:
        print(f"⚠️  Groq failed: {e}, using fallback")

    return fallback_extract(raw_results, profile)

def process_results(raw_results, profile):
    """Process results: try Groq first, fallback to regex."""
    if GROQ_KEY:
        return groq_extract(raw_results, profile)
    return fallback_extract(raw_results, profile)

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
            context={"message": "TAVILY_API_KEY not set. Please contact the administrator."}
        )

    profile = {
        "nationality": user["nationality"],
        "education": user["education"],
        "field": user["field"],
        "status": user["status"],
    }

    # ─── AGENTIC SEARCH ───
    opportunities, metadata = adaptive_search(profile)

    request.session["last_results"] = json.dumps(opportunities)
    request.session["search_metadata"] = json.dumps(metadata)

    return templates.TemplateResponse(
        request=request,
        name="results.html",
        context={
            "opportunities": opportunities,
            "count": len(opportunities),
            "user": user,
            "metadata": metadata,
        }
    )

@app.get("/results", response_class=HTMLResponse)
def view_results(request: Request, user: dict = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    results_json = request.session.get("last_results", "[]")
    metadata_json = request.session.get("search_metadata", "{}")
    opportunities = json.loads(results_json)
    metadata = json.loads(metadata_json)

    return templates.TemplateResponse(
        request=request,
        name="results.html",
        context={
            "opportunities": opportunities,
            "count": len(opportunities),
            "user": user,
            "metadata": metadata,
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

# ─── ADMIN ROUTES ───
ADMIN_EMAIL = "arcstoneacademy@gmail.com"

def get_admin_user(request: Request):
    user = get_current_user(request)
    if not user or user.get("email") != ADMIN_EMAIL:
        return None
    return user

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, admin: dict = Depends(get_admin_user)):
    if not admin:
        return RedirectResponse(url="/", status_code=302)

    conn = get_db()
    total_users = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()["count"]
    total_saved = conn.execute("SELECT COUNT(*) as count FROM saved_opportunities").fetchone()["count"]
    recent_signups = conn.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT 10").fetchall()
    popular_fields = conn.execute("SELECT field, COUNT(*) as count FROM users GROUP BY field ORDER BY count DESC LIMIT 5").fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "admin": admin,
            "total_users": total_users,
            "total_saved": total_saved,
            "recent_signups": [dict(r) for r in recent_signups],
            "popular_fields": [dict(r) for r in popular_fields],
        }
    )

@app.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request, admin: dict = Depends(get_admin_user)):
    if not admin:
        return RedirectResponse(url="/", status_code=302)

    conn = get_db()
    users = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin_users.html",
        context={"admin": admin, "users": [dict(u) for u in users], "count": len(users)}
    )

@app.get("/debug")
def debug_user(request: Request):
    user = get_current_user(request)
    if not user:
        return {"logged_in": False}
    return {
        "logged_in": True,
        "email": user.get("email"),
        "admin_email": ADMIN_EMAIL,
        "is_admin": user.get("email") == ADMIN_EMAIL
    }

# ─── RUN ───
if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 8000))
    print("🌐 Starting Opportunity Intelligence Web App")
    print(f"   Groq AI: {'✅ Enabled' if GROQ_KEY else '❌ Disabled (fallback mode)'}")
    print(f"   Tavily: {'✅ Enabled' if TAVILY_KEY else '❌ Disabled'}")
    print(f"   Adaptive Search: ✅ Enabled")
    print(f"   Port: {port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port)