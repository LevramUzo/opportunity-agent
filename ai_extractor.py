import os
import json

GROQ_KEY = os.getenv("GROQ_API_KEY")

def extract_with_groq(raw_results: list, profile: dict) -> list:
    """Use Groq LLM to extract structured opportunities from raw search results."""

    if not GROQ_KEY:
        print("⚠️  GROQ_API_KEY not set. Set it with: set GROQ_API_KEY=your-key")
        return []

    from groq import Groq
    client = Groq(api_key=GROQ_KEY)

    # Prepare content (limit to avoid token overflow)
    content_chunks = []
    for r in raw_results[:8]:
        chunk = f"""TITLE: {r.get('title', 'N/A')}
URL: {r.get('url', 'N/A')}
CONTENT: {r.get('content', 'N/A')[:600]}
---"""
        content_chunks.append(chunk)

    full_content = "\n".join(content_chunks)

    prompt = f"""You are an expert opportunity matcher for students and early-career professionals.

USER PROFILE:
Nationality: {profile['nationality']}
Education: {profile['education']}
Field: {profile['field']}
Status: {profile['status']}

SEARCH RESULTS:
{full_content}

TASK:
1. Identify ONLY genuine opportunities this person can apply for.
2. FILTER OUT: expired, paywalled, news about others winning, wrong citizenship.
3. For each VALID opportunity, return:
   - title
   - organization
   - type (scholarship/fellowship/internship/grant/research)
   - deadline (or "Rolling" / "Not specified")
   - funding (or "Not specified")
   - eligibility (list of key requirements)
   - description (1-2 sentences)
   - url
   - relevance_score (0.0 to 1.0)
   - match_reason (one sentence)

Return ONLY a JSON array. No markdown, no explanation.

Example:
[
  {{
    "title": "Example Scholarship",
    "organization": "Example Org",
    "type": "scholarship",
    "deadline": "2026-03-15",
    "funding": "Full tuition + stipend",
    "eligibility": ["African nationals", "STEM background"],
    "description": "Fully funded program for African STEM students.",
    "url": "https://example.com",
    "relevance_score": 0.92,
    "match_reason": "Matches Nigerian physics grad with full funding."
  }}
]"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=2000,
        )

        text = response.choices[0].message.content.strip()

        # Clean markdown wrappers
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        opportunities = json.loads(text)
        print(f"✅ Groq extracted {len(opportunities)} opportunities")
        return opportunities

    except json.JSONDecodeError as e:
        print(f"⚠️  JSON parse error: {e}")
        print(f"Raw response: {text[:500]}")
        return []
    except Exception as e:
        print(f"⚠️  Groq error: {e}")
        return []