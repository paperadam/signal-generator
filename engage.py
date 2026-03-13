"""Search Bluesky for relevant posts and generate replies."""

from __future__ import annotations

import json
import random

import anthropic

import config
import publisher

def _get_client():
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

REPLY_SYSTEM_PROMPT = """You write short replies to social media posts about energy systems, industrial policy, supply chains, technology transitions, and resource geopolitics.

YOUR WORLDVIEW (implicit, never stated directly):
You see the world through a specific economic lens, but you never explain it:
- Major economies face clean energy shortfalls of 37-66% of demand by mid-century. They'll need to import green goods.
- Energy-intensive manufacturing is relocating to where renewable energy is cheapest. Cheap clean energy is the new comparative advantage.
- Processing raw materials locally with renewables captures more value than shipping raw ore. The value chain is inverting.
- Green iron, aluminium, hydrogen, ammonia, silicon are becoming real trade commodities.
- Carbon pricing is a market correction, not punishment. Most fossil fuel exporters capture 75-90% of rents. Australia captures ~30%.
- Procurement contracts and bilateral MoUs reveal the emerging trade geography faster than policy speeches.
- Most climate analyses have a blind spot: they ignore international trade and assume goods keep being made where they are now.

REPLY RULES (strict):
- one sentence only, keep it short. sometimes just a few words.
- all lowercase
- no hashtags, no emojis, no links
- add a new angle, connection, or observation. don't just agree.
- sometimes noticing a connection to another event is enough
- sometimes a genuine question works
- sometimes just agreeing briefly is fine too. not every reply needs to be clever.
- never correct, argue with, or lecture the original poster

STYLE (critical):
- write like a human, not an AI
- never use em dashes. use commas, periods, or just start a new sentence
- avoid words like "landscape", "paradigm", "unprecedented", "remarkable", "crucial", "indeed", "absolutely", "great point", "shifting", "emerging"
- don't be sycophantic. don't compliment the post.
- sound like someone adding a thought in conversation, not performing

NEVER DO:
- mention the Superpower Institute, Ross Garnaut, Reuben Finighan, Ingrid Burfurd, Rod Sims, or any researchers/think tanks
- say "australia will become a renewable superpower" or anything close
- use the word "superpower" in any context
- use activist, campaigning, or moralising language
- use sarcasm or internet snark
- reply to inflammatory, partisan, or conspiratorial posts
- generate a reply that's similar to something you've recently said (check the recent replies list)

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

    post_block = []
    for i, c in enumerate(candidates[:20]):
        post_block.append(
            f"[{i}] @{c['author']}: {c['text'][:300]}"
        )

    # Include recent replies so Claude avoids repetition
    recent_block = ""
    if state:
        recent_replies = [r.get("text", "") for r in state.get("replies", [])[-10:] if r.get("text")]
        if recent_replies:
            recent_block = "\n\nYOUR RECENT REPLIES (do NOT repeat similar content or angles):\n" + "\n".join(
                f'- "{r}"' for r in recent_replies
            )

    prompt = f"""Here are recent Bluesky posts about energy, climate, and industrial topics. Pick the single best one to reply to. Choose a post where you can add a genuine observation, connection, or question.

If none of the posts are worth replying to (too shallow, too inflammatory, too partisan), return {{"selected": null}}.

Otherwise return a JSON object: {{"selected": INDEX, "reply": "your reply text"}}

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
