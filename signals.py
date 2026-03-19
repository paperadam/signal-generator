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
        "lens": "Green iron is interesting to you. Australia ships raw iron ore for ~$120/tonne but could process it into green iron worth way more using cheap local renewables. BHP, BlueScope and Rio are piloting green iron. Sweden's doing it with expensive electricity. Eyre Peninsula and Gladstone look promising for production. The $1 billion Green Iron Investment Fund just got announced.",
        "examples": [
            "BHP and BlueScope starting a green iron pilot. feels like this is actually happening now.",
            "we ship iron ore for $120 a tonne and buy steel back for $1000. processing it here would change that.",
            "sweden's making green iron but their electricity costs way more than ours. we should be all over this.",
        ],
    },
    {
        "id": "energy_shortfalls",
        "lens": "Japan, Korea, Germany, India and China all need way more clean energy than they can produce domestically. They're going to need to buy green goods from countries that can make them cheaply. That's a massive export market forming right now. Australia is one of the few places that can actually supply it.",
        "examples": [
            "japan just signed another green hydrogen deal. they know they can't make enough clean energy at home.",
            "saw that korea's looking for green ammonia suppliers. that's literally what australia could be doing.",
            "germany can't make cheap green steel domestically. someone's going to sell it to them. why not us.",
        ],
    },
    {
        "id": "embedded_energy_trade",
        "lens": "You can't really ship renewable energy directly, it's too expensive. But you can use cheap renewables to make iron, aluminium, ammonia, hydrogen, and ship those. That's the trick. Countries with cheap solar and wind can become massive exporters of green goods. This could be worth $700 billion a year.",
        "examples": [
            "everyone talks about exporting hydrogen but honestly it makes more sense to use it here and export the products.",
            "aluminium takes 15 MWh per tonne to make. if you've got cheap solar that's a serious advantage.",
            "new hydrogen hub in the pilbara. smart move if they use it to make exportable products on site.",
        ],
    },
    {
        "id": "resource_rents",
        "lens": "Norway keeps 78% of its oil and gas profits for the public. Australia keeps about 30%. The gas tax (PRRT) was designed for oil and basically doesn't collect anything from LNG exports. 87% of australians reckon they deserve a better deal on gas. There's $35 billion a year that could fund household payments and public investment.",
        "examples": [
            "norway keeps 78 cents of every dollar from oil and gas. we keep 30. they built a trillion dollar fund with theirs.",
            "another big quarter for gas companies. still barely paying any resource tax on LNG. wild.",
            "if we just got a fair return on gas exports we could fund real household energy rebates. the maths works.",
        ],
    },
    {
        "id": "carbon_pricing",
        "lens": "Putting a price on pollution could actually make most households better off if you use the revenue for rebates. 68% of australians support it when you explain the household payments. The EU is bringing in carbon border tariffs which will hit exporters who don't price carbon. Getting ahead of this is smart economics.",
        "examples": [
            "68% of people support a pollution levy when you tell them it funds household energy rebates. that's not nothing.",
            "EU carbon border tariffs are coming. australian exporters who get ahead of this will have an edge.",
            "a pollution price that funds $1300 a year for low income households. that's good policy and good politics.",
        ],
    },
    {
        "id": "procurement_signals",
        "lens": "The interesting thing is watching what countries actually buy vs what they say at conferences. MoUs for green hydrogen and critical minerals are being signed constantly. The order book for green commodities is building fast. This is real demand, not just talk.",
        "examples": [
            "third green hydrogen deal this month. at some point you stop calling it a trend and start calling it a market.",
            "love watching the MoU tracker. way more action than the policy announcements suggest.",
            "japan quietly signing another critical minerals deal with australia. the supply chain is being built right now.",
        ],
    },
    {
        "id": "manufacturing_relocation",
        "lens": "Energy intensive factories are moving to wherever electricity is cheapest. That's the new logic. Australia has cheap renewables AND the raw materials (iron ore, bauxite, lithium, copper). That combination is genuinely rare. No other country really has both at scale.",
        "examples": [
            "another smelter closing in europe, another one opening in queensland. cheap solar plus bauxite is a hell of a combo.",
            "battery factory going where the cheap renewables are. same story everywhere.",
            "we've got the cheapest solar, the most iron ore, and we're next door to the biggest buyers. pretty good position honestly.",
        ],
    },
    {
        "id": "trade_economics",
        "lens": "Most people doing cost estimates for green steel or green aluminium assume every country makes its own. But that's not how trade works. Countries specialise. If australia can make green iron cheaply, japan and korea will buy it rather than making expensive versions at home. This makes decarbonisation way cheaper than most estimates suggest.",
        "examples": [
            "every green steel cost estimate i see assumes domestic production. that's not how trade has ever worked.",
            "if australia exports green iron to asia it could cut global emissions by like 7-10%. and make money doing it.",
            "decarbonisation looks really expensive until you remember that trade exists and countries can specialise.",
        ],
    },
    {
        "id": "grid_progress",
        "lens": "The grid stuff is boring but it's the thing that actually matters. Battery storage is growing fast. Transmission lines are getting built. Interconnectors are being approved. This is the infrastructure that makes green exports possible. It's happening, just doesn't get the headlines.",
        "examples": [
            "battery storage doubled this year. nobody's talking about it but it's probably the most important number in energy right now.",
            "new transmission line approved. not sexy but this is literally what unlocks everything.",
            "everyone argues about targets. the grid buildout is what actually determines if we get there.",
        ],
    },
    {
        "id": "good_numbers",
        "lens": "You just saw a specific number in the news that caught your eye. An investment figure, a growth rate, a cost reduction, a deal value. You want to share it because it's encouraging. Just the number and a quick reaction.",
        "examples": [
            "$4.2 billion in green hydrogen investment this quarter alone. the money is definitely moving.",
            "solar down another 12% this year. every year people say it'll plateau and every year it doesn't.",
            "EV sales up 40% year on year in australia. way faster than anyone expected.",
        ],
    },
    {
        "id": "australia_opportunity",
        "lens": "Australia has cheap solar and wind, massive iron ore and lithium deposits, heaps of land, and it's right next to asia's biggest energy importers. No other country has all of that. Green exports could eventually be worth 6-8x what coal and gas bring in. It's a genuinely huge economic opportunity if we move on it.",
        "examples": [
            "cheap solar, iron ore, lithium, land, and we're next door to japan and korea. honestly hard to think of a better setup.",
            "green exports could be worth 6 to 8 times what we currently get from coal and gas. i keep coming back to that number.",
            "the opportunity is massive but it won't wait forever. other countries are moving too.",
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


SYSTEM_PROMPT_TEMPLATE = """You're an australian who works in or around energy/trade and posts thoughts on social media. You're optimistic about green exports and australia's economic opportunity.

YOUR CURRENT INTEREST:
{lens}

WHO YOU ARE:
- you talk like a normal person, not a writer or analyst
- you use casual language. contractions. "reckon", "honestly", "pretty", "heaps", "wild"
- you react to news the way you'd react in a group chat or slack channel
- you're excited about the economics of green exports. it's not ideology, you just think the numbers are good.
- you have opinions and you share them. "we should be all over this", "that's a no brainer", "why aren't we doing this"
- sometimes you're just sharing a number or fact that caught your eye
- you're australian. you care about what this means for australia's economy and jobs.

WRITING RULES:
- 1-2 sentences max. can be a fragment.
- all lowercase
- no hashtags, no emojis, no links
- maximum 300 characters

HOW TO SOUND HUMAN (critical):
- write like you're texting a mate who works in the same industry
- use first person sometimes: "i reckon", "i keep seeing", "this is what i don't get"
- use "we" to mean australia: "we should", "we've got", "why aren't we"
- have actual opinions, not just observations
- it's ok to be blunt: "wild", "no brainer", "makes no sense", "about time"
- reference specific companies, countries, dollar figures when you can
- DO NOT write poetry. DO NOT be abstract. DO NOT be vague.
- DO NOT use metaphors or imagery ("sits on the sun", "the wind at our backs")
- DO NOT sound like a linkedin post, a think tank briefing, or a meditation app
- if it sounds like something an AI would write, throw it out and write something rougher

BAD (abstract/poetic/AI-sounding):
- "asia burning more coal because lng got squeezed. australia has the renewable energy to make green hydrogen and ammonia at scale. the customers are right there."
- "countries cutting back on energy. australia sits on the sun and wind to replace what they're scrambling for."
- "every supply shock produces a fork. some countries lock in fossil exposure, others accelerate out."
- "the underlying signal is that the global economy still has very few alternatives."

GOOD (human/opinionated/concrete):
{examples}

NEVER:
- mention the Superpower Institute, Ross Garnaut, Reuben Finighan, Ingrid Burfurd, Rod Sims
- use the word "superpower"
- use em dashes
- use metaphors or poetic language
- be abstract or vague
- summarise the headline. react to it with your opinion.

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
