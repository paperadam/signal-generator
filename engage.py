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

Your implicit lens: many global developments are gradually aligning with Australia's long-term opportunity as a clean energy and green industrial power. You never state this directly. You just notice how events fit together.

REPLY RULES (strict):
- one sentence only, keep it short
- all lowercase
- no hashtags, no emojis, no links
- add a new angle, connection, or observation. don't just agree
- sometimes noticing a connection to another event is enough
- sometimes a genuine question works
- never correct, argue with, or lecture the original poster

STYLE (critical):
- write like a human, not an AI
- never use em dashes. use commas, periods, or just start a new sentence
- avoid words like "landscape", "paradigm", "unprecedented", "remarkable", "crucial", "indeed", "absolutely", "great point"
- don't be sycophantic. don't compliment the post
- sound like someone adding a thought in conversation, not performing

NEVER DO:
- mention the Superpower Institute or Ross Garnaut
- say "australia will become a renewable superpower" or similar
- use activist, campaigning, or moralising language
- use sarcasm or internet snark
- reply to inflammatory, partisan, or conspiratorial posts

When generating replies, return ONLY valid JSON. No markdown, no commentary."""


def search_relevant_posts(bsky_client, state: dict) -> list[dict]:
    """Search Bluesky for posts worth engaging with."""
    # Pick 2-3 random queries to search
    queries = random.sample(
        config.ENGAGE_SEARCH_QUERIES,
        min(3, len(config.ENGAGE_SEARCH_QUERIES)),
    )

    candidates = []
    seen_uris = set(state.get("replied_to", []))
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

    return unique


def select_and_reply(candidates: list[dict]) -> dict | None:
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

    prompt = f"""Here are recent Bluesky posts about energy, climate, and industrial topics. Pick the single best one to reply to. Choose a post where you can add a genuine observation, connection, or question.

If none of the posts are worth replying to (too shallow, too inflammatory, too partisan), return {{"selected": null}}.

Otherwise return a JSON object: {{"selected": INDEX, "reply": "your reply text"}}

Posts:
{chr(10).join(post_block)}"""

    response = _get_client().messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=500,
        system=REPLY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        raw = response.content[0].text
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
    except (json.JSONDecodeError, TypeError, IndexError) as e:
        print(f"  warning: failed to parse Claude response: {e}")
        print(f"  raw: {response.content[0].text[:300]}")
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
        return {"post": candidates[idx], "reply": reply_text}
    return None
