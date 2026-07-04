import os
from google import genai

GEMINI_KEY = os.getenv("GEMINI_API_KEY")

def enhance_with_gemini(opportunities):
    """Optional: Use Gemini to enrich opportunities if quota allows."""
    
    if not GEMINI_KEY:
        return opportunities
    
    client = genai.Client(api_key=GEMINI_KEY)
    
    # Try to enhance just the top 3 opportunities
    for opp in opportunities[:3]:
        try:
            prompt = f"""For this opportunity, provide a 2-sentence application tip:
Title: {opp['title']}
Organization: {opp['organization']}
Description: {opp['description']}

Keep it under 100 words."""
            
            response = client.models.generate_content(
                model="gemini-1.5-flash-latest",
                contents=prompt,
            )
            opp['gemini_tip'] = response.text.strip()
        except Exception:
            opp['gemini_tip'] = "No additional tips available."
    
    return opportunities