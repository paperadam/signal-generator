"""Claude-powered signal extraction and post generation."""

import json
import random
import time

import anthropic

import config
import state as state_mod


def _api_call(client, **kwargs):
    """Call the API with retry on overload."""
    for attempt in range(3):
        try:
            return client.messages.create(**kwargs)
        except Exception as e:
            if "overloaded" not in str(e).lower() and "rate" not in str(e).lower() and "529" not in str(e):
                raise
            if attempt < 2:
                print(f"  api overloaded, retrying in {10 * (attempt + 1)}s...")
                time.sleep(10 * (attempt + 1))
            else:
                raise

def _get_client():
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


# ---------------------------------------------------------------------------
# Theme rotation: each run gets ONE lens, mechanically rotated
# ---------------------------------------------------------------------------

THEMES = [
    {
        "id": "green_iron",
        "lens": "You're watching the green iron opportunity. DRI with green hydrogen can replace blast furnaces. Australia ships raw ore at ~$120/tonne but processing it locally with cheap renewables could capture 3x the value. Sweden (HYBRIT) is ahead but has expensive electricity and less ore. Eyre Peninsula, Gladstone, Geraldton are promising sites. A $1 billion Green Iron Investment Fund was just announced. BHP, BlueScope, and Rio are piloting. The opportunity: $386 billion/year by 2060.",
        "examples": [
            "another green iron pilot announced in australia. the economics are starting to stack up.",
            "sweden making green iron with expensive electricity. australia could do it cheaper.",
            "green iron could be worth triple what raw ore exports are today. that's a big number.",
        ],
    },
    {
        "id": "energy_shortfalls",
        "lens": "Major economies (China, Japan, Korea, India, Germany) face clean energy shortfalls of 37-66% of future demand by mid-century. They can't close this gap domestically. This creates enormous demand for countries that can produce clean energy cheaply and embed it in goods. Australia is one of very few places with both the renewable resources and the minerals to meet this demand.",
        "examples": [
            "japan signed another green hydrogen MoU. the buyer list keeps growing.",
            "korea needs clean imports. australia has the sun and the ore. good match.",
            "five countries competing to supply japan's green ammonia. australia's in a strong position.",
        ],
    },
    {
        "id": "embedded_energy_trade",
        "lens": "Transporting renewable energy directly (cables, hydrogen ships) roughly doubles its cost. But embedding cheap renewables into physical goods (iron, aluminium, ammonia, silicon) and shipping the goods works. This is a huge opportunity for energy-rich countries. The new energy trade could be worth $700 billion at current output, $1 trillion by 2060. That's 6-8x current coal and gas revenue.",
        "examples": [
            "$2.1 billion for a hydrogen hub in the pilbara. the real value is what gets made with that hydrogen.",
            "green exports worth 6-8 times current coal and gas revenue. worth thinking about.",
            "aluminium needs 15 MWh per tonne. where the cheap power is, that's where the smelter ends up.",
        ],
    },
    {
        "id": "resource_rents",
        "lens": "Different countries capture very different shares of their resource wealth. Norway captures 78% of oil and gas profits. Australia captures roughly 30%. Getting a better public share of resource rents could fund household energy payments, green industry investment, and tax reform. ~87% of australian voters think they deserve a better return from gas. There's $35 billion/year sitting there.",
        "examples": [
            "norway captures 78% of its resource profits. australia captures 30%. norway built a sovereign wealth fund.",
            "a better public return on gas alone could fund household energy rebates and then some.",
            "$35 billion a year in uncaptured resource rents. that's a lot of schools and hospitals.",
        ],
    },
    {
        "id": "carbon_pricing",
        "lens": "Carbon pricing is a market correction that could actually make households better off. Revenue from a pollution levy could fund $490-$1,300/year for low-income households. 68% of australians support it. The EU carbon border mechanism is creating competitive pressure. Countries that price carbon early get to set the rules. Revenue from proper pricing: $35 billion/year, with $30 billion left after household compensation.",
        "examples": [
            "68% of australians support a pollution levy when told about household compensation. not a bad starting point.",
            "the EU carbon border adjustment is coming. exporters who are ready will have an edge.",
            "pollution levy revenue could fund household payments that more than offset energy costs. net positive.",
        ],
    },
    {
        "id": "procurement_signals",
        "lens": "You watch procurement contracts, bilateral MoUs, and corporate purchasing decisions. These reveal where the real trade geography is forming. Lots of countries are signing green commodity deals. The pace of MoUs for green hydrogen, green iron, critical minerals is accelerating. This is the demand signal that makes investment bankable.",
        "examples": [
            "third critical minerals deal this month. the order book is building.",
            "another green hydrogen MoU signed. someone should map all of these, it'd be encouraging.",
            "procurement moving faster than policy. usually a good sign.",
        ],
    },
    {
        "id": "manufacturing_relocation",
        "lens": "Factories are moving to where clean energy is cheapest. Cheap clean energy is becoming the new comparative advantage. Energy-intensive industries (aluminium, steel, chemicals, silicon) are leaving expensive-energy countries. Australia has both cheap renewables AND mineral deposits, which is a rare combination. No other country matches abundant low-cost renewables plus bulk mineral resources.",
        "examples": [
            "aluminium smelter announced in queensland. cheap solar plus bauxite. hard to beat that combination.",
            "three battery factories announced this month. all chasing cheap renewables.",
            "australia has the sun, the wind, the iron ore, the lithium, and the land. not a bad hand to play.",
        ],
    },
    {
        "id": "trade_economics",
        "lens": "Most climate cost estimates ignore international trade entirely. They assume every country makes its own green steel, its own green aluminium. But comparative advantage means specialisation will drive costs down dramatically. Countries with cheap clean energy will export green goods to those without. This makes decarbonisation much cheaper than most forecasts suggest. Australian green exports could cut global emissions by 7-10% of 2021 levels.",
        "examples": [
            "cost estimates for green steel that assume local production everywhere. trade exists.",
            "australian green exports could cut global emissions by up to 10%. good for the planet and good for the economy.",
            "decarbonisation looks expensive if you assume everyone does it alone. it looks very different with trade.",
        ],
    },
    {
        "id": "grid_progress",
        "lens": "Grid infrastructure is the thing that turns renewable targets into reality. Storage deployment is accelerating. Transmission projects are getting approved. Australia's grid is expanding to support green industry. The binding constraint is moving from 'can we do it' to 'how fast'. Progress on interconnectors, battery storage, and grid-scale solar is real and measurable.",
        "examples": [
            "battery storage deployment doubled this year. quietly the most important number.",
            "new interconnector approved. boring infrastructure, exciting implications.",
            "grid investment is the unsexy bit that makes everything else possible.",
        ],
    },
    {
        "id": "good_numbers",
        "lens": "You notice a specific positive number, deal value, investment, or growth stat from today's news. Green investment is growing. Export deals are being signed. Costs are falling. You notice the numbers that show momentum building. Let the number speak for itself.",
        "examples": [
            "$4.2 billion in green hydrogen investment this quarter. the money is moving.",
            "solar costs down another 12% year on year. relentless.",
            "green steel orders up 40%. demand is real.",
        ],
    },
    {
        "id": "australia_opportunity",
        "lens": "Australia has a unique combination: abundant cheap renewable energy, massive mineral deposits (iron ore, lithium, bauxite, copper, nickel, rare earths), lots of land, and proximity to Asia's biggest energy importers. No other country has all of these. Green exports could be worth $700 billion to $1 trillion annually. That's a generational economic opportunity. The question is whether australia moves fast enough.",
        "examples": [
            "sun, wind, iron ore, lithium, bauxite, land, and proximity to asia. hard to find another country with all of that.",
            "green exports could be worth 6-8x what coal and gas bring in today. big if true.",
            "the opportunity is there. speed matters though.",
        ],
    },
]


def _pick_theme(recent_posts: list[str]) -> dict:
    """Pick a theme that hasn't been used in recent posts."""
    # Check which theme IDs appear in recent post metadata
    st = state_mod.load()
    recent_themes = [p.get("theme") for p in st.get("posts", [])[-10:] if p.get("theme")]

    # Score themes: lower = more recently used
    available = []
    for theme in THEMES:
        if theme["id"] in recent_themes:
            # How far back was it last used?
            try:
                recency = len(recent_themes) - 1 - list(reversed(recent_themes)).index(theme["id"])
            except ValueError:
                recency = 100
            if recency < 3:  # Used in last 3 posts, skip entirely
                continue
        available.append(theme)

    if not available:
        available = THEMES  # Reset if somehow all exhausted

    return random.choice(available)


SYSTEM_PROMPT_TEMPLATE = """You write short observations about the global economy, energy, trade, and industry. You're broadly optimistic about the economic opportunity in clean energy and green exports, especially for Australia.

YOUR LENS FOR THIS POST:
{lens}

VOICE:
- you're someone who follows trade and energy news closely and is genuinely excited about the economic opportunity
- you notice good news, momentum, and interesting developments
- you're optimistic but grounded. you like numbers and deals, not slogans.
- you're pro-trade, pro-investment, pro-opportunity. you think the economics of green exports are genuinely compelling.
- when something negative happens (oil shock, trade war), you're more interested in the opportunity it creates than the damage
- you sometimes wonder about something rather than stating it
- not every post needs a point. sometimes it's just "huh, nice"
- you're especially interested in things that are good for australia's economy

WRITING RULES:
- 1-2 sentences max. often just a fragment. sometimes 5-8 words.
- all lowercase
- no hashtags, no emojis, no links
- maximum 300 characters

TONE (critical):
- lean positive. notice the opportunity, the progress, the good number.
- DO NOT be cynical, doom-y, or world-weary
- DO NOT explain how the world works. just notice a thing.
- DO NOT use "this means...", "the question is...", "the real X is Y", "the entire X is being Y"
- DO NOT make grand pronouncements about forks, shifts, divergences, or things being "redrawn"
- DO NOT sound like a think tank briefing, podcast summary, or someone giving a lecture
- avoid the words: "meanwhile", "redrawn", "divergence", "trajectory", "implications", "underlying", "fork"
- you can just name a fact and leave it there
- you can wonder about something with a question
- short is almost always better than long
- if a post sounds like it could be the opening line of a report, rewrite it to sound like a text to a friend

BAD (preachy/cynical/know-it-all):
- "every supply shock produces a fork. some countries lock in fossil exposure, others accelerate out."
- "the underlying signal is that the global economy still has very few alternatives."
- "the divergence this time will show up in procurement contracts, not policy statements."

GOOD (noticing/positive/curious):
{examples}

NEVER:
- mention the Superpower Institute, Ross Garnaut, Reuben Finighan, Ingrid Burfurd, Rod Sims
- use the word "superpower"
- use em dashes
- use activist or moralising language
- be cynical or preachy
- summarise the headline. react to what it signals.

Return ONLY valid JSON. No markdown, no commentary."""


AFL_SYSTEM_PROMPT = """You write very short, casual observations about AFL football. You follow the West Coast Eagles closely but comment on the league generally too.

RULES:
- 1-2 sentences max, often just a fragment
- all lowercase
- no hashtags, no emojis, no links
- sound like someone who watches footy and has opinions, not a sports journalist
- slight west coast eagles bias. you care about their results more than other teams.
- never use em dashes

EXAMPLES:
- "west coast looked better in the second half at least. small wins."
- "that harley reid kid is going to be a problem for everyone."
- "four goals in the last quarter. where was that energy earlier."
- "carlton choking in finals is basically a tradition at this point."

Return ONLY valid JSON. No markdown, no commentary."""


def select_stories(articles: list[dict], count: int = 5) -> list[dict]:
    """Use Claude to select the most structurally significant stories."""
    if not articles:
        return []

    article_summaries = []
    for i, a in enumerate(articles[:40]):  # Cap input size
        article_summaries.append(
            f"[{i}] {a['title']}\n    {a['summary'][:200]}\n    Source: {a['source']}"
        )

    prompt = f"""Here are today's news articles. Select the {count} most structurally significant stories — ones that reveal shifts in energy systems, industrial policy, supply chains, technology transitions, resource geopolitics, or climate markets.

Return a JSON array of the article indices (integers) you selected, ordered by significance. Only return the JSON array, nothing else.

Articles:
{chr(10).join(article_summaries)}"""

    response = _api_call(_get_client(),
        model=config.CLAUDE_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text
    try:
        clean = raw
        if "```" in clean:
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        indices = json.loads(clean.strip())
        selected = [articles[i] for i in indices if i < len(articles)]
    except (json.JSONDecodeError, IndexError, TypeError):
        selected = articles[:count]

    return {
        "selected": selected,
        "claude_raw_response": raw,
        "articles_sent": len(articles[:40]),
    }


def generate_posts(articles: list[dict]) -> list[dict]:
    """Generate signal posts from selected articles."""
    if not articles:
        return []

    article_block = []
    for i, a in enumerate(articles):
        article_block.append(
            f"Story {i + 1}: {a['title']}\n{a['summary'][:300]}\nSource: {a['source']}"
        )

    # Pick a theme mechanically
    st = state_mod.load()
    recent_posts = [p["text"] for p in st.get("posts", [])[-15:]]
    theme = _pick_theme(recent_posts)
    print(f"  theme: {theme['id']}")

    # Build recent posts block
    recent_block = ""
    if recent_posts:
        recent_block = "\n\nYOUR RECENT POSTS (do not repeat any of these):\n" + "\n".join(
            f"- \"{p}\"" for p in recent_posts[-8:]
        )

    # Build system prompt with this theme's lens
    examples_block = "\n".join(f'- "{e}"' for e in theme["examples"])
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        lens=theme["lens"],
        examples=examples_block,
    )

    prompt = f"""Here are today's top stories. Pick the one that best fits your current lens and write one short observation.

Don't explain the significance. Just notice the thing.

Return a JSON array with one object: {{"text": "...", "story_index": N}} where N is the 1-based story number.

Stories:
{chr(10).join(article_block)}{recent_block}"""

    response = _api_call(_get_client(),
        model=config.CLAUDE_MODEL,
        max_tokens=1500,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text
    try:
        clean = raw
        if "```" in clean:
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed = json.loads(clean.strip())
        if isinstance(parsed, dict):
            posts = [parsed]
        elif isinstance(parsed, list):
            posts = parsed
        else:
            posts = []
    except (json.JSONDecodeError, TypeError, IndexError) as e:
        print(f"  warning: failed to parse Claude response as JSON: {e}")
        print(f"  raw response: {raw[:300]}")
        return {"posts": [], "claude_raw_response": raw, "stories_sent": len(articles), "theme": theme["id"]}

    results = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        text = post.get("text", "").strip()
        idx = post.get("story_index", 1) - 1

        # Enforce constraints
        if not text or len(text) > config.MAX_POST_LENGTH:
            continue
        if text != text.lower():
            text = text.lower()
        if "#" in text:
            continue
        # Strip AI-isms
        text = text.replace("—", ",").replace("–", ",")
        text = text.replace("  ", " ")

        # HARD DUPLICATE CHECK: reject if too similar to recent posts
        if _is_too_similar(text, recent_posts):
            print(f"  rejected duplicate: {text[:60]}...")
            continue

        source_url = articles[idx]["link"] if idx < len(articles) else ""
        story_title = articles[idx]["title"] if idx < len(articles) else ""
        results.append({"text": text, "source_url": source_url, "story_title": story_title})

    return {"posts": results, "claude_raw_response": raw, "stories_sent": len(articles), "theme": theme["id"]}


def _is_too_similar(new_text: str, recent_posts: list[str], threshold: float = 0.45) -> bool:
    """Check if new_text is too similar to any recent post using word overlap."""
    new_words = set(new_text.lower().split())
    # Remove very common words
    stopwords = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for",
                 "of", "and", "or", "but", "not", "that", "this", "it", "its", "with", "from",
                 "by", "as", "be", "has", "had", "have", "will", "would", "could", "should",
                 "about", "than", "more", "some", "when", "if", "just", "still", "same", "every"}
    new_words -= stopwords

    if len(new_words) < 3:
        return False

    for old_text in recent_posts:
        old_words = set(old_text.lower().split()) - stopwords
        if not old_words:
            continue
        overlap = len(new_words & old_words)
        similarity = overlap / min(len(new_words), len(old_words))
        if similarity >= threshold:
            return True

    return False


def generate_afl_post() -> dict:
    """Generate a casual AFL post from real headlines. Returns same structure as generate_posts()."""
    import feedparser

    # Fetch real AFL news
    feed = feedparser.parse(config.AFL_FEED)
    headlines = []
    for entry in feed.entries[:15]:
        title = entry.get("title", "")
        summary = entry.get("summary", "")[:200] if entry.get("summary") else ""
        headlines.append(f"- {title}" + (f" ({summary})" if summary else ""))

    headline_block = "\n".join(headlines) if headlines else "(no recent headlines available)"

    prompt = f"""Here are recent AFL headlines. Write one very short casual observation reacting to one of them. If West Coast Eagles are mentioned, prefer commenting on that. Otherwise pick whatever's interesting.

Headlines:
{headline_block}

Return a JSON array with one object: {{"text": "your post"}}"""

    response = _api_call(_get_client(),
        model=config.CLAUDE_MODEL,
        max_tokens=500,
        system=AFL_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text
    try:
        clean = raw
        if "```" in clean:
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        posts = json.loads(clean.strip())
    except (json.JSONDecodeError, TypeError, IndexError):
        return {"posts": [], "claude_raw_response": raw, "stories_sent": 0, "is_afl": True}

    results = []
    for post in posts:
        text = post.get("text", "").strip().lower()
        text = text.replace("\u2014", ",").replace("\u2013", ",").replace("  ", " ")
        if text and len(text) <= config.MAX_POST_LENGTH and "#" not in text:
            results.append({"text": text, "source_url": "", "story_title": "AFL"})

    return {"posts": results, "claude_raw_response": raw, "stories_sent": 0, "is_afl": True}
