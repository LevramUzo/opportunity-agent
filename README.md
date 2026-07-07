# 🎯 Opportunity Intelligence Agent

> AI-powered opportunity discovery for African STEM students — built with adaptive agentic search, not just retrieval.

**Live:** [https://opportunity-agent-production-3e05.up.railway.app/](https://opportunity-agent-production-3e05.up.railway.app/)  
**Built with:** Python, FastAPI, Tavily, Groq LLM, SQLite, Jinja2

---

## What This Is

Opportunity Intelligence finds scholarships, fellowships, internships, and grants matched to your profile. But unlike typical "search + display" apps, it uses an **adaptive agentic search layer** that evaluates its own results, plans next steps, and self-corrects when initial outputs are insufficient.

We don't apply on your behalf. We find the opportunities — you apply with confidence on the official site.

---

## 🧠 Why This Is Agentic (Not Just a Pipeline)

Most opportunity finders run a fixed query and return whatever they get. This system **thinks about its own output** before showing it to you.

### The Agentic Loop

```
User searches
    ↓
Round 1: Run 6 initial queries → Extract opportunities
    ↓
[AGENTIC] System evaluates its own result quality
    ↓
Count < 3? Avg relevance < 0.6? High-confidence matches < 2?
    ↓
YES → System decides to search again
    ↓
[AGENTIC] System analyzes what was found vs. what's missing
    ↓
[AGENTIC] System generates targeted refined queries (6 strategies)
    ↓
Round 2: Run refined queries → Merge + deduplicate
    ↓
Display results + transparency: "Expanded search to find more matches"
```

### What Makes It Agentic

| Capability | What It Means | How This App Demonstrates It |
|---|---|---|
| **Self-evaluation** | The system checks its own output quality | `evaluate_search_quality()` scores results on count, relevance, and confidence |
| **Planning** | The system decides what to do next based on current state | If results are weak, it plans a refinement round instead of quitting |
| **Runtime decision-making** | The system chooses actions dynamically, not from a hardcoded script | `generate_refined_queries()` selects strategies based on what was found vs. missing |
| **Self-correction** | The system retries with adjusted approach when first attempt fails | Automatically re-searches with broader, targeted, or field-specific queries |
| **Transparency** | The system explains its reasoning to the user | Results page shows: "Expanded search to find more matches" with round counts |

### The 6 Refinement Strategies

When initial results are weak, the agent selects from these strategies dynamically:

1. **Broadening** — Removes restrictive terms (e.g., "Nigerian PhD Quantum Computing" → "African students physics funding")
2. **Organization targeting** — Searches specific orgs found in round 1 for more of their programs
3. **Type filling** — Searches for missing opportunity types (scholarship vs. fellowship vs. grant vs. internship)
4. **Geographic expansion** — Widens from country-specific to regional (West Africa, Sub-Saharan Africa)
5. **Status-specific** — Targets PhD, graduate, or undergraduate programs based on user status
6. **Field-specific programs** — Targets well-known programs (Google DeepMind, CERN, IAEA, Microsoft) based on user's field

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Web App                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  Auth    │  │ Profile  │  │  Search  │  │  Admin   │    │
│  │(signup/  │  │(edit/view│  │(agentic  │  │(analytics│    │
│  │ login)   │  │  profile)│  │  loop)   │  │ dashboard│    │
│  └──────────┘  └──────────┘  └────┬─────┘  └──────────┘    │
│                                     │                       │
│                           ┌─────────▼──────────┐           │
│                           │  Adaptive Search   │           │
│                           │  Agentic Layer       │           │
│                           │  ┌──────────────┐   │           │
│                           │  │evaluate_search│  │           │
│                           │  │_quality()     │  │           │
│                           │  └──────────────┘   │           │
│                           │  ┌──────────────┐   │           │
│                           │  │generate_refined│  │           │
│                           │  │_queries()      │  │           │
│                           │  └──────────────┘   │           │
│                           └─────────┬──────────┘           │
│                                     │                       │
│                    ┌────────────────┼────────────────┐     │
│                    ▼                ▼                ▼     │
│              ┌─────────┐     ┌─────────┐     ┌─────────┐  │
│              │ Tavily  │     │  Groq   │     │ Regex   │  │
│              │ Search  │     │  LLM    │     │Fallback │  │
│              │ Engine  │     │Extractor│     │Extractor│  │
│              └─────────┘     └─────────┘     └─────────┘  │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              SQLite Database                         │   │
│  │  users │ saved_opportunities │ search_metadata      │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **User** submits profile → stored in SQLite
2. **Adaptive Search Agent** evaluates need → plans queries → executes via Tavily
3. **Extraction Layer** tries Groq LLM first, falls back to regex if unavailable
4. **Results** are scored, ranked, and displayed with transparency metadata
5. **User** can save opportunities, edit profile, or trigger new searches

---

## 🚀 Features

### Core
- ✅ **Adaptive Agentic Search** — Self-evaluating, self-correcting search with up to 2 rounds
- ✅ **AI-Powered Extraction** — Groq LLM structures raw web results into opportunities
- ✅ **Regex Fallback** — Works even when Groq is unavailable
- ✅ **Profile-Based Matching** — Filters by nationality, education, field, status
- ✅ **Deadline Tracking** — Automatic extraction from opportunity pages
- ✅ **Save & Track** — Bookmark opportunities with SQLite persistence
- ✅ **Edit Profile** — Update your criteria anytime
- ✅ **Admin Dashboard** — Analytics on users, popular fields, recent signups

### UX
- ✅ Modern dark UI with glassmorphism navigation
- ✅ Responsive design (mobile + desktop)
- ✅ Animated fade-up transitions
- ✅ Transparency banner when adaptive search triggers
- ✅ Clear messaging: "We find opportunities — you apply directly"

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI |
| Database | SQLite (users, saved_opportunities) |
| Search Engine | Tavily API |
| AI Extraction | Groq LLM (Llama 3.1 8B) |
| Fallback | Regex-based extraction |
| Frontend | Jinja2 templates, custom CSS |
| Deployment | Railway (auto-deploy from GitHub) |
| Auth | Session-based with bcrypt hashing |

---

## 📦 Installation

```bash
# Clone the repo
git clone https://github.com/LevramUzo/opportunity-agent.git
cd opportunity-agent

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Set environment variables
set TAVILY_API_KEY=tvly-your-key
set GROQ_API_KEY=gsk-your-key

# Run locally
python web_app.py
```

Visit `http://localhost:8000`

---

## 🔑 Environment Variables

| Variable | Source | Purpose |
|---|---|---|
| `TAVILY_API_KEY` | [tavily.com](https://tavily.com) | Web search engine |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) | LLM extraction |

---

## 🧪 Testing the Agentic Layer

To see the adaptive search in action, use a **narrow profile** that forces low initial results:

| Field | Value |
|---|---|
| Nationality | Nigerian |
| Education | PhD |
| Field | Quantum Computing |
| Status | Graduate |

**Expected behavior:**
```
🔍 Search quality low (only_2_results). Triggering adaptive refinement...
✅ Adaptive search complete: 2 → 7 opportunities
```

Results page will show: **"Expanded search to find more matches — Initial: 2, Final: 7"**

---

## 📁 Project Structure

```
opportunity-agent/
├── web_app.py              # Main FastAPI app (agentic search layer)
├── ai_extractor.py         # Groq LLM extraction module
├── database.py             # SQLite schema + helpers
├── requirements.txt        # Dependencies
├── templates/
│   ├── base.html           # Design system (CSS + layout)
│   ├── index.html          # Landing page with trust messaging
│   ├── signup.html         # Registration
│   ├── login.html          # Authentication
│   ├── dashboard.html      # User home
│   ├── results.html        # Search results + adaptive banner
│   ├── saved.html          # Bookmarked opportunities
│   ├── edit_profile.html   # Profile editing
│   ├── admin.html          # Admin dashboard
│   └── admin_users.html    # User management
└── README.md               # This file
```

---

## 🗺️ Roadmap

- [x] Adaptive agentic search (self-evaluating, self-correcting)
- [x] Groq LLM extraction with regex fallback
- [x] User authentication & profiles
- [x] Save/bookmark opportunities
- [x] Admin dashboard
- [x] Modern responsive UI
- [ ] Password reset via email
- [ ] Email alerts for new matching opportunities
- [ ] OAuth (Google/GitHub login)
- [ ] Rate limiting for API cost control
- [ ] Activity log for users
- [ ] Dark/light theme toggle

---

## 🤝 Contributing

This is a personal project built to demonstrate agentic AI skills. Feedback and ideas are welcome — open an issue or reach out.

---

## 📄 License

MIT License — free to use, modify, and build upon.

---

## 🙏 Acknowledgments

- [Tavily](https://tavily.com) for the search API
- [Groq](https://groq.com) for fast LLM inference
- [FastAPI](https://fastapi.tiangolo.com) for the web framework

---

> *Built to prove that agentic AI isn't just a buzzword — it's a measurable improvement in how systems find, evaluate, and deliver value.*
