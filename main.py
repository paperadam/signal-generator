#!/usr/bin/env python3
"""Daily Social Signal Generator — CLI entry point."""

import argparse
import sys

import config
import feeds
import signals
import state as state_mod
import publisher
import engage


def run(dry_run: bool = False, fetch_only: bool = False) -> None:
    st = state_mod.load()
    state_mod.cleanup_old(st)

    # --- Fetch ---
    print("fetching rss feeds...")
    all_articles = feeds.fetch_all_feeds()
    print(f"  found {len(all_articles)} articles")

    relevant = feeds.filter_relevant(all_articles)
    print(f"  {len(relevant)} match topic filters")

    # Remove already-seen articles
    new_articles = [a for a in relevant if not state_mod.is_article_seen(st, a["link"])]
    print(f"  {len(new_articles)} are new")

    if fetch_only:
        print("\n--- articles ---")
        for a in new_articles[:20]:
            print(f"  [{a['source']}] {a['title']}")
            print(f"    {a['link']}")
        return

    if not new_articles:
        print("no new relevant articles. nothing to do.")
        return

    # --- Check daily limit ---
    posted_today = state_mod.posts_today(st)
    remaining = config.MAX_POSTS_PER_DAY - posted_today
    if remaining <= 0:
        print(f"already posted {posted_today} times today (limit: {config.MAX_POSTS_PER_DAY}). skipping.")
        return
    posts_this_run = min(config.MAX_POSTS_PER_RUN, remaining)

    # --- Select + Generate ---
    print("selecting stories with claude...")
    selected = signals.select_stories(new_articles, count=posts_this_run + 2)
    print(f"  selected {len(selected)} stories")

    print("generating signal posts...")
    posts = signals.generate_posts(selected)
    posts = posts[:posts_this_run]
    print(f"  generated {len(posts)} posts")

    if not posts:
        print("no posts generated. check article quality or try again later.")
        return

    # --- Mark articles as seen ---
    for a in new_articles:
        state_mod.mark_article_seen(st, a["link"])

    # --- Publish or dry-run ---
    if dry_run:
        print("\n--- dry run (not posting) ---")
        for i, p in enumerate(posts, 1):
            print(f"\n  [{i}] {p['text']}")
            print(f"      source: {p['source_url']}")
    else:
        print("posting to bluesky...")
        bsky = publisher.create_client()
        for i, p in enumerate(posts, 1):
            try:
                uri = publisher.post(bsky, p["text"])
                state_mod.record_post(st, p["text"], p["source_url"])
                print(f"  [{i}] posted: {p['text'][:80]}...")
                print(f"      uri: {uri}")
            except Exception as e:
                print(f"  [{i}] failed to post: {e}")

    state_mod.save(st)
    print("\ndone.")


def run_engage(dry_run: bool = False) -> None:
    st = state_mod.load()
    state_mod.cleanup_old(st)

    # --- Check daily limit ---
    replied_today = state_mod.replies_today(st)
    if replied_today >= config.MAX_REPLIES_PER_DAY:
        print(f"already replied {replied_today} times today (limit: {config.MAX_REPLIES_PER_DAY}). skipping.")
        return

    # --- Search ---
    print("searching bluesky for relevant posts...")
    bsky = publisher.create_client()
    candidates = engage.search_relevant_posts(bsky, st)
    print(f"  found {len(candidates)} candidate posts")

    if not candidates:
        print("no suitable posts found to engage with.")
        return

    # --- Select + Generate reply ---
    print("selecting post and generating reply...")
    result = engage.select_and_reply(candidates)

    if not result:
        print("claude decided none of the posts were worth replying to. fair enough.")
        return

    post_info = result["post"]
    reply_text = result["reply"]

    if dry_run:
        print("\n--- engage dry run (not posting) ---")
        print(f"\n  original post by @{post_info['author']}:")
        print(f"    {post_info['text'][:200]}")
        print(f"\n  reply:")
        print(f"    {reply_text}")
        print(f"\n  post uri: {post_info['uri']}")
    else:
        print("posting reply to bluesky...")
        try:
            uri = publisher.reply_to_post(bsky, post_info["uri"], post_info["cid"], reply_text)
            state_mod.record_reply(st, post_info["uri"], reply_text)
            print(f"  replied to @{post_info['author']}: {reply_text[:80]}...")
            print(f"  reply uri: {uri}")
        except Exception as e:
            print(f"  failed to post reply: {e}")

    state_mod.save(st)
    print("\ndone.")


def main():
    parser = argparse.ArgumentParser(description="Daily Social Signal Generator")
    parser.add_argument("--dry-run", action="store_true", help="Generate posts but don't publish")
    parser.add_argument("--fetch-only", action="store_true", help="Only show today's relevant articles")
    parser.add_argument("--engage", action="store_true", help="Search and reply to relevant Bluesky posts")
    parser.add_argument("--engage-dry-run", action="store_true", help="Preview engagement without posting")
    parser.add_argument("--scheduled", action="store_true", help="Cloud mode: post a signal then engage")
    args = parser.parse_args()

    needs_claude = not args.fetch_only
    needs_bluesky = not args.dry_run and not args.fetch_only and not args.engage_dry_run

    if needs_claude and not config.ANTHROPIC_API_KEY:
        print("error: ANTHROPIC_API_KEY not set. check your .env file.")
        sys.exit(1)

    if (needs_bluesky or args.engage or args.engage_dry_run or args.scheduled):
        if not config.BLUESKY_HANDLE or not config.BLUESKY_PASSWORD:
            print("error: BLUESKY_HANDLE and BLUESKY_PASSWORD must be set. check your .env file.")
            sys.exit(1)

    if args.scheduled:
        print("=== scheduled run ===")
        run(dry_run=False)
        print()
        run_engage(dry_run=False)
    elif args.engage or args.engage_dry_run:
        run_engage(dry_run=args.engage_dry_run)
    else:
        run(dry_run=args.dry_run, fetch_only=args.fetch_only)


if __name__ == "__main__":
    main()
