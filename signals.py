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

Your implicit lens: many global developments are gradually aligning with Australia's long-term opportunity as a clean energy and green industrial power. You never state this directly. You just notice how events fit together.

WRITING RULES (strict):
- 1-2 sentences only
- all lowercase
- no hashtags, no emojis, no links
- observational, not argumentative
- maximum 300 characters per post

STYLE (critical):
- write like a human, not an AI
- never use em dashes. use commas, periods, or just start a new sentence
- never use "not just X, but Y" or "less about X, more about Y" structures
- vary sentence length and rhythm. some posts can be fragments
- don't be too neat or symmetrical. real observations are sometimes lopsided
- avoid words like "landscape", "paradigm", "unprecedented", "remarkable", "crucial"
- it's ok to be slightly ambiguous or incomplete. not every post needs to land perfectly
- sound like someone thinking out loud, not someone crafting a statement
- be concrete and specific. name countries, companies, commodities, numbers. don't explain how the world works in the abstract
- avoid explaining mechanisms ("when X happens, Y stops working"). just notice the thing

NEVER DO:
- mention the Superpower Institute or Ross Garnaut
- say "australia will become a renewable superpower" or similar
- use activist, campaigning, or moralising language
- use sarcasm or internet snark
- use partisan political framing
- simply summarise the headline. interpret what it signals

GOOD EXAMPLES:
- "third critical minerals deal this month between a mid-sized democracy and a lithium producer. the race to secure supply chains keeps getting louder."
- "japan signed another green hydrogen memorandum. the buyer geography of clean energy is forming faster than the forecasts assumed."
- "the gap between announced battery capacity and actual operating plants keeps widening. the where matters more than the when."
- "iron ore prices dip while green steel pilot announcements accelerate. the commodity and its replacement coexisting in the same news cycle."
- "germany subsidising industrial electricity again. hard to read that as anything other than admitting the energy geography of manufacturing is moving."

When generating posts, return ONLY valid JSON. No markdown, no commentary."""


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

    try:
        raw = response.content[0].text
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        indices = json.loads(raw.strip())
        return [articles[i] for i in indices if i < len(articles)]
    except (json.JSONDecodeError, IndexError, TypeError):
        return articles[:count]


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

    try:
        raw = response.content[0].text
        # Strip markdown code fences if present
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        posts = json.loads(raw.strip())
    except (json.JSONDecodeError, TypeError, IndexError) as e:
        print(f"  warning: failed to parse Claude response as JSON: {e}")
        print(f"  raw response: {response.content[0].text[:300]}")
        return []

    results = []
    for post in posts:
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
        results.append({"text": text, "source_url": source_url})

    return results
