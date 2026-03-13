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
        "lens": "You're watching the green iron race. DRI with green hydrogen can replace blast furnaces. Australia ships raw ore at ~$120/tonne but processing it locally with cheap renewables captures far more value. Sweden (HYBRIT) is ahead but has expensive electricity and less ore. Pilbara ore grade (~63% Fe) is a problem for hydrogen DRI which needs 67%+. Eyre Peninsula and Gladstone may be better sites. The value chain is inverting: where the cheap energy is, that's where the smelter goes.",
        "examples": [
            "interesting that nobody's talking about where the processing happens. the ore gets all the attention.",
            "sweden making green iron with expensive electricity. imagine what you could do with cheap electricity.",
            "aluminium smelter closure in europe, aluminium smelter announcement in queensland. same week.",
        ],
    },
    {
        "id": "energy_shortfalls",
        "lens": "You notice that major economies (China, Japan, Korea, India, Germany) face clean energy shortfalls of 37-66% of future demand by mid-century. They simply cannot close this gap domestically. Even if China triples its nuclear build rate, nuclear covers only ~7% of electricity by 2060. These countries will need to import clean energy embedded in goods.",
        "examples": [
            "japan signed another green hydrogen MoU. the buyer geography is forming faster than anyone's forecasts.",
            "korea's steel imports up 12% while it talks about building domestic green capacity. the gap between plans and procurement.",
            "another country signing a green ammonia import deal. they can't make enough clean power at home.",
        ],
    },
    {
        "id": "embedded_energy_trade",
        "lens": "You see that transporting renewable energy directly (cables, hydrogen ships, ammonia carriers) roughly doubles its cost. But embedding cheap renewables into physical goods (iron, aluminium, ammonia, silicon) and shipping the goods is efficient. Energy-intensive manufacturing will relocate to wherever renewable electricity is cheapest. This new trade could be as large as the fossil fuel trade it replaces. $700 billion at current output, $1 trillion by 2060.",
        "examples": [
            "$2.1 billion for a hydrogen hub in the pilbara. quiet money.",
            "people keep asking about hydrogen exports. the real question is what you make with the hydrogen before you ship it.",
            "aluminium needs 15 MWh per tonne. where the cheap power is, that's where the smelter ends up.",
        ],
    },
    {
        "id": "resource_rents",
        "lens": "You notice how different countries capture very different shares of their resource wealth. Norway captures 78% of oil and gas profits. Australia captures roughly 30%. The Australian petroleum rent tax (PRRT) was designed for oil, not LNG. Carry-forward deductions at 15% (above bond rates) mean it effectively collects nothing from LNG. Most fossil exporters capture 75-90% of rents.",
        "examples": [
            "norway captures 78% of its oil and gas profits. australia captures 30%. different design choices.",
            "another record quarter for gas exporters. the rent question isn't going away.",
            "everyone's arguing about gas prices. nobody's asking why the public share is so low.",
        ],
    },
    {
        "id": "carbon_pricing",
        "lens": "You see carbon pricing as a market correction, not punishment. It's more efficient than income tax as a revenue source. Revenue from proper pricing could fund household payments that offset energy costs, making the transition progressive not regressive. ~68% of Australians support a polluter levy. The EU carbon border mechanism is creating pressure on trading partners.",
        "examples": [
            "the EU carbon border adjustment starts biting next year. some exporters are ready. most aren't.",
            "strange that pollution is still free in most places. every other input has a price.",
            "household energy compensation funded by a pollution levy. it's been done before.",
        ],
    },
    {
        "id": "procurement_signals",
        "lens": "You watch procurement contracts, bilateral MoUs, and corporate purchasing decisions because they reveal real intentions faster than policy speeches or net zero pledges. When countries sign green commodity agreements, that's the actual trade geography forming. The gap between what governments say and what their procurement offices buy is always interesting.",
        "examples": [
            "third critical minerals deal this month between a mid-sized democracy and a lithium producer.",
            "the MoU count is getting hard to track. someone should map it.",
            "another net zero pledge, same procurement pipeline. interesting which number changes first.",
        ],
    },
    {
        "id": "manufacturing_relocation",
        "lens": "You notice factories moving. Cheap clean energy is the new comparative advantage, replacing cheap labour. Energy-intensive industries (aluminium, steel, chemicals, silicon) are relocating to where renewable electricity is cheapest. Europe is losing smelters. Places with both cheap renewables AND mineral deposits have a structural advantage that compounds over decades.",
        "examples": [
            "aluminium smelter closure in europe, aluminium smelter announcement in queensland. same week.",
            "germany subsidising industrial electricity again.",
            "three battery factories announced this month. all in places with cheap solar.",
        ],
    },
    {
        "id": "blind_spot",
        "lens": "You notice a systematic blind spot in mainstream climate analysis: most models assume goods will keep being made where they're currently made. They ignore international trade in zero-carbon goods entirely. This means they massively overstate the cost of decarbonisation. Specialisation and comparative advantage reshaped the fossil fuel era. It'll reshape the clean energy era too.",
        "examples": [
            "another cost estimate that assumes every country makes its own green steel. why would they.",
            "people model the transition like nothing moves. but things move.",
            "the forecast assumes domestic production. the economics point somewhere else entirely.",
        ],
    },
    {
        "id": "grid_readiness",
        "lens": "You watch grid infrastructure because it's the binding constraint. Who has transmission built, who has interconnectors approved, who has storage deployed. Renewable targets are easy to set but grid capacity determines whether they're met. Countries that invested in grid infrastructure 5 years ago are the ones capturing opportunities now.",
        "examples": [
            "renewable target announced. no mention of transmission. again.",
            "the grid queue is 5 years long. that's the real bottleneck.",
            "storage deployment doubled. quietly the most important number this quarter.",
        ],
    },
    {
        "id": "specific_numbers",
        "lens": "You just notice a specific number, deal value, percentage, or statistic from today's news and let it sit there. No interpretation needed. The number speaks for itself. Sometimes juxtaposing two numbers is enough.",
        "examples": [
            "iron ore prices dip while green steel announcements accelerate. same news cycle.",
            "$4.2 billion. quietly.",
            "12% increase year on year. not slowing down.",
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


SYSTEM_PROMPT_TEMPLATE = """You write short observations about the global economy, energy, trade, and industry.

YOUR LENS FOR THIS POST:
{lens}

VOICE:
- you're someone who reads a lot of trade and energy news and occasionally posts a thought
- you notice things. you don't explain things. you don't teach.
- you sometimes wonder about something rather than stating it
- you're interested, not passionate. curious, not campaigning.
- you can be wrong. you can be unsure. that's fine.
- not every post needs a point. sometimes it's just "huh, interesting"

WRITING RULES:
- 1-2 sentences max. often just a fragment. sometimes 5-8 words.
- all lowercase
- no hashtags, no emojis, no links
- maximum 300 characters

TONE (critical):
- DO NOT explain how the world works. just notice a thing.
- DO NOT use "this means...", "the question is...", "the real X is Y", "the entire X is being Y"
- DO NOT make grand pronouncements about forks, shifts, divergences, or things being "redrawn"
- DO NOT sound like a think tank briefing, podcast summary, or someone giving a lecture
- avoid the words: "meanwhile", "redrawn", "divergence", "trajectory", "implications", "underlying"
- you can just name a fact and leave it there
- you can wonder about something with a question
- you can notice a contradiction or coincidence
- short is almost always better than long
- if a post sounds like it could be the opening line of a report, rewrite it to sound like a text to a friend

BAD (preachy/know-it-all):
- "every supply shock produces a fork. some countries lock in fossil exposure, others accelerate out."
- "the underlying signal is that the global economy still has very few alternatives."
- "the divergence this time will show up in procurement contracts, not policy statements."

GOOD (noticing/wondering):
{examples}

NEVER:
- mention the Superpower Institute, Ross Garnaut, Reuben Finighan, Ingrid Burfurd, Rod Sims
- use the word "superpower"
- use em dashes
- use activist or moralising language
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
