import os
import json
import re
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import uvicorn
from tavily import TavilyClient

# ─── API KEYS ───
TAVILY_KEY = os.getenv("TAVILY_API_KEY")

if not TAVILY_KEY:
    print("⚠️  Warning: TAVILY_API_KEY not set. Set it before running.")

tavily = TavilyClient(api_key=TAVILY_KEY) if TAVILY_KEY else None

# ─── APP SETUP ───
app = FastAPI(title="Opportunity Intelligence Agent")
templates = Jinja2Templates(directory="templates")

# Create templates directory if it doesn't exist
os.makedirs("templates", exist_ok=True)

# ─── PROFILE ───
MY_PROFILE = {
    "name": "Opara Marvellous",
    "nationality": "Nigerian",
    "education": "BSc Physics",
    "field": "AI / Machine Learning",
    "status": "NYSC",
    "interests": ["scholarships", "fellowships", "internships", "grants"],
}

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

# ─── ROUTES ───
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"profile": MY_PROFILE}
    )

@app.post("/search", response_class=HTMLResponse)
def search(request: Request):
    if not tavily:
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={"message": "TAVILY_API_KEY not set. Please set it and restart."}
        )
    
    raw = search_opportunities(MY_PROFILE)
    opportunities = process_results(raw, MY_PROFILE)
    
    with open("opportunities.json", "w") as f:
        json.dump(opportunities, f, indent=2)
    
    return templates.TemplateResponse(
        request=request,
        name="results.html",
        context={
            "opportunities": opportunities,
            "count": len(opportunities),
            "profile": MY_PROFILE
        }
    )

@app.get("/results", response_class=HTMLResponse)
def view_results(request: Request):
    try:
        with open("opportunities.json", "r") as f:
            opportunities = json.load(f)
    except FileNotFoundError:
        opportunities = []
    
    return templates.TemplateResponse(
        request=request,
        name="results.html",
        context={
            "opportunities": opportunities,
            "count": len(opportunities),
            "profile": MY_PROFILE
        }
    )

# ─── RUN ───
if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 8000))
    print("🌐 Starting Opportunity Intelligence Web App")
    print(f"   Running on port {port}\n")
    uvicorn.run(app, host="0.0.0.0", port=port)