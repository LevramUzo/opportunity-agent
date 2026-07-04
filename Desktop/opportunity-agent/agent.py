import os
import json
from tavily import TavilyClient

TAVILY_KEY = os.getenv("TAVILY_API_KEY")

if not TAVILY_KEY:
    print("❌ Set TAVILY_API_KEY first!")
    exit(1)

tavily = TavilyClient(api_key=TAVILY_KEY)

MY_PROFILE = {
    "name": "Your Name",
    "nationality": "Nigerian",
    "education": "BSc Physics",
    "field": "AI / Machine Learning",
    "status": "NYSC",
}

def search_opportunities(profile):
    base = f"{profile['nationality']} {profile['education']} {profile['field']} {profile['status']}"
    
    queries = [
        f"scholarships for {base} 2026",
        f"fellowships for African students {profile['field']} 2026",
        f"internships {profile['field']} remote graduates 2026",
        f"grants for {profile['status']} members technology Nigeria 2026",
    ]
    
    all_results = []
    print(f"🔍 Running {len(queries)} searches...\n")
    
    for query in queries:
        print(f"  → {query[:50]}...")
        response = tavily.search(
            query=query,
            max_results=3,
            search_depth="advanced",
        )
        all_results.extend(response.get("results", []))
    
    # Remove duplicates
    seen = set()
    unique = []
    for r in all_results:
        url = r.get("url", "")
        if url and url not in seen:
            seen.add(url)
            unique.append(r)
    
    print(f"\n✅ Found {len(unique)} unique results")
    return unique


def simple_extract(raw_results):
    """Simple extraction without Gemini — uses Tavily's structured data."""
    
    opportunities = []
    
    for r in raw_results:
        title = r.get("title", "Unknown")
        url = r.get("url", "")
        content = r.get("content", "")
        
        # Skip news articles and irrelevant results
        if any(word in title.lower() for word in ["news", "article", "blog", "wikipedia"]):
            continue
            
        # Guess type from title
        type_guess = "opportunity"
        if "scholarship" in title.lower():
            type_guess = "scholarship"
        elif "fellowship" in title.lower():
            type_guess = "fellowship"
        elif "internship" in title.lower():
            type_guess = "internship"
        elif "grant" in title.lower():
            type_guess = "grant"
        
        opportunities.append({
            "title": title,
            "organization": url.split("/")[2] if url else "Unknown",
            "type": type_guess,
            "deadline": "Check link for deadline",
            "funding": "Check link for details",
            "eligibility": ["See website"],
            "description": content[:200] + "..." if len(content) > 200 else content,
            "url": url,
            "relevance_score": 0.7,
            "match_reason": f"Matches {MY_PROFILE['nationality']} {MY_PROFILE['field']} profile"
        })
    
    return opportunities


def display_results(opportunities):
    if not opportunities:
        print("\n❌ No opportunities found.")
        return
    
    print("\n" + "=" * 65)
    print("YOUR MATCHED OPPORTUNITIES")
    print("=" * 65)
    
    for i, opp in enumerate(opportunities, 1):
        print(f"\n{'─' * 65}")
        print(f"  #{i}  {opp['title']}")
        print(f"       {opp['organization']}")
        print(f"{'─' * 65}")
        print(f"  Type:      {opp['type'].upper()}")
        print(f"  Deadline:  {opp['deadline']}")
        print(f"  Funding:   {opp['funding']}")
        print(f"  Why fits:  {opp['match_reason']}")
        print(f"  Link:      {opp['url']}")
        print(f"  About:     {opp['description']}")
    
    print(f"\n{'=' * 65}")
    print(f"Total: {len(opportunities)} opportunities")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    print("🚀 Opportunity Intelligence Agent [Simple Mode — No Gemini]")
    print(f"   Profile: {MY_PROFILE['nationality']} | {MY_PROFILE['education']} | {MY_PROFILE['field']} | {MY_PROFILE['status']}\n")
    
    raw = search_opportunities(MY_PROFILE)
    
    if not raw:
        print("❌ Search returned nothing.")
        exit(1)
    
    opportunities = simple_extract(raw)
    display_results(opportunities)

    
    if opportunities:
        with open("opportunities.json", "w") as f:
            json.dump(opportunities, f, indent=2)
        print("\n💾 Saved to opportunities.json")
        print("\n⚠️  This is a basic extraction. For AI-powered analysis with deadlines,")
        print("   funding amounts, and eligibility details, use the full agent.py")
        print("   once your Gemini quota resets.")
        
try:
    opportunities = enhance_with_gemini(opportunities)
except Exception:
    pass  # Gemini failed, but we still have our results