import os
from dotenv import load_dotenv

load_dotenv(override=True)

# --- Claude API ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-6"

# --- Bluesky ---
BLUESKY_HANDLE = os.getenv("BLUESKY_HANDLE", "")
BLUESKY_PASSWORD = os.getenv("BLUESKY_PASSWORD", "")

# --- RSS Feeds ---
FEEDS = [
    # Australian
    "https://www.abc.net.au/news/feed/2942460/rss.xml",          # ABC News Top Stories
    "https://www.theguardian.com/australia-news/rss",             # Guardian Australia
    "https://www.afr.com/rss",                                    # AFR

    # International
    "https://feeds.reuters.com/reuters/worldNews",                # Reuters World
    "https://feeds.reuters.com/reuters/businessNews",             # Reuters Business
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",    # NYT World
    "https://rss.nytimes.com/services/xml/rss/nyt/Climate.xml",  # NYT Climate

    # Energy / Climate / Industry
    "https://www.theguardian.com/environment/climate-crisis/rss", # Guardian Climate
    "https://www.theguardian.com/business/rss",                   # Guardian Business
    "https://feeds.reuters.com/reuters/environment",              # Reuters Environment
]

# --- Topic keywords for relevance filtering ---
TOPIC_KEYWORDS = [
    "energy", "renewable", "solar", "wind", "battery", "hydrogen",
    "lithium", "critical mineral", "rare earth", "green steel",
    "electrification", "grid", "transmission", "storage",
    "industrial policy", "manufacturing", "supply chain",
    "trade", "tariff", "subsidy", "ira", "inflation reduction",
    "climate", "emissions", "carbon", "net zero", "decarbonisation",
    "lng", "gas", "coal", "oil", "fossil",
    "geopolitics", "china", "india", "eu", "united states",
    "iron ore", "aluminium", "copper", "nickel", "cobalt",
    "electric vehicle", "ev", "semiconductor", "chip",
    "australia", "pacific", "indo-pacific",
]

# --- Posting ---
MAX_POSTS_PER_RUN = 1
MAX_POSTS_PER_DAY = 5
MAX_POST_LENGTH = 300  # characters

# --- Engagement ---
MAX_REPLIES_PER_DAY = 2
ENGAGE_SEARCH_QUERIES = [
    "energy transition",
    "critical minerals",
    "green hydrogen",
    "battery supply chain",
    "renewable energy Australia",
    "green steel",
    "industrial policy energy",
    "lithium mining",
    "solar manufacturing",
    "decarbonisation",
]

# --- Timing / humanisation ---
SKIP_CHANCE = 0.4           # 40% of scheduled runs do nothing (simulates being busy)
DELAY_MIN_MINUTES = 5       # random delay before acting
DELAY_MAX_MINUTES = 45
ENGAGE_GAP_MIN_MINUTES = 10  # gap between posting and replying
ENGAGE_GAP_MAX_MINUTES = 30
WAKE_HOUR_UTC = 20          # 6am AEDT (UTC+11) — won't post before this
SLEEP_HOUR_UTC = 12         # 11pm AEDT (UTC+11) — won't post after this

# --- State ---
STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")
ARTICLE_LOOKBACK_HOURS = 24
