# knowItAll

Interactive daily intelligence assistant that delivers real-time founder-relevant signals, not noise.

## What It Does

knowItAll monitors the AI/CS research landscape and translates it into actionable founder intelligence:

1. **Research Signal Detection** — Monitors arXiv (and extensible to OpenReview, major labs, top conferences). Papers are scored for founder relevance and novelty, with direct links (PDF, code, project page), concise summaries, and a founder lens assessment.

2. **Research → Startup Translation** — Combines papers with market signals to generate concrete startup ideas with: target user, core technical insight, defensibility analysis, complexity rating, build timeline, required tools, and explicit flags for what's NOT worth pursuing.

3. **Real-Time Tech & Tool Awareness** — Tracks new AI tools, frameworks, model releases, and APIs. Classifies each as hype vs. genuine leverage shift with rationale, links, docs, and use cases.

4. **Founder Opportunity Radar** — Surfaces strategic timing windows, hackathons, accelerators, grants, and competitions. Prioritised by ROI, resume value, network leverage, and speed to validation.

5. **Interactive, Action-Forcing Format** — Every item is skimmable but expandable on demand, with links and follow-up actions like "Generate an MVP plan", "Assess competition", "Estimate costs", and "Draft a pitch outline".

6. **Zero-Noise Philosophy** — If it doesn't create leverage, reveal a timing asymmetry, or unlock a new product class, it doesn't get sent.

7. **Startup Opportunity Scout** — Daily web scanning across Reddit, Hacker News, Product Hunt, and other sources. Identifies tech trends, user complaints/pain points, and industry gaps. Cross-references signals to generate actionable startup ideas with target market, tech stack, and monetization strategy. Structured reports cover: top tech trends, key complaints & demands, industry gaps, and startup ideas — all sourced and quantified.

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Run the server
uvicorn knowitall.main:app --reload

# Run tests
pytest tests/ -v
```

Open [http://localhost:8000](http://localhost:8000) to view today's interactive digest.
Open [http://localhost:8000/scout](http://localhost:8000/scout) to view the startup opportunity scout report.

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Interactive HTML digest |
| `GET /scout` | Startup opportunity scout report (HTML) |
| `GET /api/digest` | JSON digest data |
| `GET /api/scout-report` | JSON scout report data |
| `GET /api/health` | Health check |

## Project Structure

```
src/knowitall/
├── main.py                  # FastAPI app entry point
├── config.py                # Configuration management
├── models/                  # Pydantic data models
│   ├── paper.py             # Research paper + founder lens
│   ├── startup_idea.py      # Startup ideas from research
│   ├── tool.py              # Tech tools + hype assessment
│   ├── opportunity.py       # Founder opportunities
│   ├── digest.py            # Daily digest assembly
│   └── scout_report.py     # Scout report models
├── services/                # Core intelligence services
│   ├── research_monitor.py  # arXiv/OpenReview monitoring
│   ├── startup_translator.py# Research-to-startup pipeline
│   ├── tool_tracker.py      # Tool/framework tracking
│   ├── opportunity_radar.py # Opportunity detection
│   ├── signal_filter.py     # Zero-noise filtering
│   ├── web_scanner.py       # Multi-source web scanning
│   └── opportunity_scout.py # Startup opportunity scout
├── api/
│   └── routes.py            # API routes + digest generation
└── templates/
    ├── digest.html          # Interactive digest UI
    └── scout_report.html    # Scout report UI
```

## Tech Stack

- **Python 3.10+** with **FastAPI**
- **Pydantic v2** for data validation
- **httpx** for async HTTP
- **Jinja2** for HTML templating
- **pytest** + **pytest-asyncio** for testing