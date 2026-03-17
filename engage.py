"""Search Bluesky for relevant posts and generate replies."""

from __future__ import annotations

import json
import random

import anthropic

import config
import publisher

def _get_client():
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

REPLY_SYSTEM_PROMPT = """You write short replies to social media posts about energy, trade, industry, and climate economics.

YOUR WORLDVIEW (implicit, never stated directly):
You're optimistic about the economic opportunity in clean energy and green exports, especially for Australia:
- Major economies will need to import green goods. That's demand waiting to be met.
- Cheap clean energy is a competitive advantage. Countries with it can attract manufacturing.
- Processing raw materials locally with renewables captures way more value than shipping raw ore.
- Green iron, aluminium, hydrogen, ammonia are becoming real export commodities.
- Better resource rent capture could fund household payments and green investment.
- The economics of decarbonisation are better than most people think, especially when you factor in trade.
- Australia has an unusually strong hand: cheap renewables, minerals, land, proximity to Asia.

REPLY RULES (strict):
- one sentence only, keep it short. sometimes just a few words.
- all lowercase
- no hashtags, no emojis, no links
- lean positive. amplify good news, notice opportunity, add an encouraging angle.
- when someone posts about green investment, trade deals, or progress, build on it
- when someone posts about problems, look for the opportunity angle
- sometimes just agreeing is fine. "yeah this is a big deal" or "good sign" works.
- sometimes a genuine question works
- never correct, argue with, or lecture the original poster

STYLE (critical):
- write like a human, not an AI
- never use em dashes. use commas, periods, or just start a new sentence
- avoid words like "landscape", "paradigm", "unprecedented", "remarkable", "crucial", "indeed", "absolutely", "great point", "shifting", "emerging"
- don't be sycophantic. don't over-compliment.
- sound like someone adding a thought in conversation, not performing
- be warm but not gushing. interested but not fanboy.

NEVER DO:
- mention the Superpower Institute, Ross Garnaut, Reuben Finighan, Ingrid Burfurd, Rod Sims, or any researchers/think tanks
- say "australia will become a renewable superpower" or anything close
- use the word "superpower" in any context
- use activist, campaigning, or moralising language
- be cynical, doom-y, or world-weary
- use sarcasm or internet snark
- reply to inflammatory, partisan, or conspiratorial posts
- generate a reply that's similar to something you've recently said

When generating replies, return ONLY valid JSON. No markdown, no commentary."""


def _recently_replied_authors(state: dict) -> set:
    """Return authors we've replied to in the last 7 days."""
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    authors = set()
    for r in state.get("replies", []):
        if r.get("date", "") >= cutoff and r.get("author"):
            authors.add(r["author"].lower())
    return authors


def search_relevant_posts(bsky_client, state: dict) -> dict:
    """Search Bluesky for posts worth engaging with."""
    # Pick 2-3 random queries to search
    queries = random.sample(
        config.ENGAGE_SEARCH_QUERIES,
        min(3, len(config.ENGAGE_SEARCH_QUERIES)),
    )

    candidates = []
    seen_uris = set(state.get("replied_to", []))
    recent_authors = _recently_replied_authors(state)
    own_handle = config.BLUESKY_HANDLE.lower()

    for query in queries:
        try:
            posts = publisher.search_posts(bsky_client, query, limit=15)
            for p in posts:
                # Skip own posts
                if p.author.handle.lower() == own_handle:
                    continue
                # Skip already replied to
                if p.uri in seen_uris:
                    continue
                # Skip authors we've replied to recently
                if p.author.handle.lower() in recent_authors:
                    continue
                # Skip very short posts (likely not substantive)
                text = p.record.text if hasattr(p.record, "text") else ""
                if len(text) < 30:
                    continue
                # Skip posts with very high or very low engagement
                likes = p.like_count or 0
                if likes > 500:  # don't clout-chase
                    continue

                candidates.append({
                    "uri": p.uri,
                    "cid": p.cid,
                    "author": p.author.handle,
                    "text": text,
                    "likes": likes,
                    "query": query,
                })
        except Exception as e:
            print(f"  warning: search failed for '{query}': {e}")

    # Deduplicate by URI
    seen = set()
    unique = []
    for c in candidates:
        if c["uri"] not in seen:
            seen.add(c["uri"])
            unique.append(c)

    return {"candidates": unique, "queries_used": queries}


def select_and_reply(candidates: list[dict], state: dict = None) -> dict | None:
    """Use Claude to pick the best post to reply to and generate a reply.

    Returns {"post": candidate_dict, "reply": str} or None.
    """
    if not candidates:
        return None

    # Re-load state fresh right before replying to catch any concurrent writes
    import state as state_mod
    fresh_state = state_mod.load()
    recent_authors = _recently_replied_authors(fresh_state)
    fresh_replied = set(fresh_state.get("replied_to", []))

    # Filter out candidates we've already replied to (catches concurrent runs)
    candidates = [
        c for c in candidates
        if c["uri"] not in fresh_replied and c["author"].lower() not in recent_authors
    ]
    if not candidates:
        print("  all candidates filtered out after fresh state check.")
        return None

    post_block = []
    for i, c in enumerate(candidates[:20]):
        post_block.append(
            f"[{i}] @{c['author']}: {c['text'][:300]}"
        )

    # Include recent replies so Claude avoids repetition
    recent_block = ""
    recent_replies = [r.get("text", "") for r in fresh_state.get("replies", [])[-10:] if r.get("text")]
    if recent_replies:
        recent_block = "\n\nYOUR RECENT REPLIES (you MUST NOT repeat similar content, angles, or phrasing. say something genuinely different):\n" + "\n".join(
            f'- "{r}"' for r in recent_replies
        )

    prompt = f"""Here are recent Bluesky posts about energy, climate, and industrial topics. Pick the single best one to reply to. Choose a post where you can add a genuine observation, connection, or question.

RULES:
- If none are worth replying to (too shallow, inflammatory, partisan), return {{"selected": null}}.
- Your reply must be genuinely different from your recent replies listed below. Different topic, different framing, different words.
- Short replies are good. Even just a few words adding a thought.
- Don't always go for the most obvious post. Sometimes a smaller, less polished post is more interesting to engage with.

Return a JSON object: {{"selected": INDEX, "reply": "your reply text"}}

Posts:
{chr(10).join(post_block)}{recent_block}"""

    response = _get_client().messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=500,
        system=REPLY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text
    try:
        clean = raw
        if "```" in clean:
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        result = json.loads(clean.strip())
    except (json.JSONDecodeError, TypeError, IndexError) as e:
        print(f"  warning: failed to parse Claude response: {e}")
        print(f"  raw: {raw[:300]}")
        return None

    idx = result.get("selected")
    if idx is None:
        return None

    reply_text = result.get("reply", "").strip()
    if not reply_text:
        return None

    # Enforce constraints
    reply_text = reply_text.lower()
    reply_text = reply_text.replace("\u2014", ",").replace("\u2013", ",")
    reply_text = reply_text.replace("  ", " ")
    if "#" in reply_text or len(reply_text) > config.MAX_POST_LENGTH:
        return None

    if idx < len(candidates):
        return {"post": candidates[idx], "reply": reply_text, "claude_raw_response": raw}
    return None
