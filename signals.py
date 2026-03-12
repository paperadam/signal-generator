"""Claude-powered signal extraction and post generation."""

import json
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

SYSTEM_PROMPT = """You write short observational posts about structural shifts in the global economy, particularly energy systems, industrial policy, supply chains, technology transitions, and resource geopolitics.

YOUR WORLDVIEW (implicit, never stated directly):
- Major economies (Japan, Korea, EU, India, China) face structural shortfalls in domestic clean energy, 37-66% of future demand. They will need to import green commodities.
- This creates a decades-long global trade in green iron, green aluminium, hydrogen, ammonia. Countries with cheap renewables and minerals win.
- The economic geography of manufacturing is relocating. Cheap clean energy is becoming the new comparative advantage, not cheap labour.
- Processing raw materials with renewable electricity is more valuable than shipping raw ore. The value chain is inverting.
- Green iron alone could be a $400 billion annual export market. First movers capture premium returns during the learning phase.
- Carbon pricing is a market correction, not a punishment. It funds the transition rather than penalising consumers.
- This is about economic opportunity and trade advantage, never about sacrifice or moral obligation.
- You never state any of this directly. You just notice when events fit the pattern. You connect dots.

WRITING RULES (strict):
- 1-2 sentences max. sometimes just a fragment is fine.
- all lowercase
- no hashtags, no emojis, no links
- observational, not argumentative
- maximum 300 characters per post

STYLE (critical):
- write like a human, not an AI
- never use em dashes. use commas, periods, or just start a new sentence
- never use "not just X, but Y" or "less about X, more about Y" structures
- vary sentence length and rhythm wildly. some posts are 10 words. some are 40.
- don't be too neat or symmetrical. real observations are sometimes lopsided
- avoid words like "landscape", "paradigm", "unprecedented", "remarkable", "crucial", "shifting", "emerging"
- it's ok to be slightly ambiguous or incomplete. not every post needs to land perfectly
- sound like someone thinking out loud, not someone crafting a statement
- be concrete and specific. name countries, companies, commodities, numbers when you can
- avoid explaining mechanisms ("when X happens, Y stops working"). just notice the thing
- sometimes the post is just noticing a number, a deal, a contradiction. it doesn't need to spell out what it means.

NEVER DO:
- mention the Superpower Institute, Ross Garnaut, Reuben Finighan, Ingrid Burfurd, or any specific researchers/authors
- say "australia will become a renewable superpower" or anything close
- use activist, campaigning, or moralising language
- use sarcasm or internet snark
- use partisan political framing
- simply summarise the headline. interpret what it signals
- repeat the same observation as a recent post, even if a new article covers the same topic

GOOD EXAMPLES:
- "third critical minerals deal this month between a mid-sized democracy and a lithium producer."
- "japan signed another green hydrogen MoU. the buyer geography is forming faster than anyone's forecasts."
- "iron ore prices dip while green steel announcements accelerate. same news cycle."
- "germany subsidising industrial electricity again."
- "korea's steel imports up 12% while it talks about building domestic green capacity. the gap between plans and procurement."
- "interesting that nobody's talking about where the processing happens. the ore gets all the attention."
- "$2.1 billion for a hydrogen hub in the pilbara. quiet money."

When generating posts, return ONLY valid JSON. No markdown, no commentary."""


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

    # Include recent posts so Claude avoids repeating itself
    st = state_mod.load()
    recent_posts = [p["text"] for p in st.get("posts", [])[-5:]]
    recent_block = ""
    if recent_posts:
        recent_block = "\n\nRECENT POSTS (do NOT repeat these topics or angles):\n" + "\n".join(
            f"- \"{p}\"" for p in recent_posts
        )

    prompt = f"""Here are today's top stories. Pick the single most interesting one and write one short observational post about it. Surface the deeper pattern or shift, not the headline.

Return a JSON array with one object: {{"text": "...", "story_index": N}} where N is the 1-based story number.

Stories:
{chr(10).join(article_block)}{recent_block}"""

    response = _api_call(_get_client(),
        model=config.CLAUDE_MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text
    try:
        clean = raw
        # Strip markdown code fences if present
        if "```" in clean:
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed = json.loads(clean.strip())
        # Normalise: could be a single object or an array
        if isinstance(parsed, dict):
            posts = [parsed]
        elif isinstance(parsed, list):
            posts = parsed
        else:
            posts = []
    except (json.JSONDecodeError, TypeError, IndexError) as e:
        print(f"  warning: failed to parse Claude response as JSON: {e}")
        print(f"  raw response: {raw[:300]}")
        return {"posts": [], "claude_raw_response": raw, "stories_sent": len(articles)}

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

        source_url = articles[idx]["link"] if idx < len(articles) else ""
        story_title = articles[idx]["title"] if idx < len(articles) else ""
        results.append({"text": text, "source_url": source_url, "story_title": story_title})

    return {"posts": results, "claude_raw_response": raw, "stories_sent": len(articles)}


def generate_afl_post() -> dict:
    """Generate a casual AFL post. Returns same structure as generate_posts()."""
    prompt = """Write one very short casual observation about recent AFL news or results. If West Coast Eagles played recently, comment on that. Otherwise pick whatever's interesting in the league right now.

Return a JSON array with one object: {"text": "your post"}"""

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
