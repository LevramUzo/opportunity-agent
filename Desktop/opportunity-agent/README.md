# Opportunity Intelligence Agent

An agentic AI system that searches the web for scholarships, fellowships, internships, and grants matched to your profile.

## What It Does

1. **Searches** the web for opportunities using Tavily
2. **Filters** results that match your profile
3. **Extracts** key details — deadline, requirements, eligibility, funding
4. **Scores** each opportunity by relevance
5. **Saves** structured results to a JSON file

## Tech Stack

- Python
- Tavily (web search API)
- Google Gemini (LLM for extraction & analysis)

## Setup

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/opportunity-agent.git
cd opportunity-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set API keys
export TAVILY_API_KEY="your-key"
export GEMINI_API_KEY="your-key"

# Run
python agent.py