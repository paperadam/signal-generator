#!/usr/bin/env python3
"""Daily Social Signal Generator — CLI entry point."""

import argparse
import random
import sys
import time
from datetime import datetime, timezone

import config
import feeds
import signals
import state as state_mod
import publisher
import engage
from run_log import RunLog


def _is_sleep_hours() -> bool:
    """Check if it's outside the 'author's' waking hours."""
    hour = datetime.now(timezone.utc).hour
    # Handle wrap-around (e.g. wake=20 UTC, sleep=12 UTC means active 20-23, 0-11)
    if config.WAKE_HOUR_UTC <= config.SLEEP_HOUR_UTC:
        return not (config.WAKE_HOUR_UTC <= hour < config.SLEEP_HOUR_UTC)
    else:
        return config.SLEEP_HOUR_UTC <= hour < config.WAKE_HOUR_UTC


def _random_delay(min_min: int, max_min: int, label: str) -> float:
    """Sleep for a random duration to humanise timing. Returns minutes slept."""
    minutes = random.uniform(min_min, max_min)
    print(f"{label}: waiting {minutes:.0f} minutes...")
    time.sleep(minutes * 60)
    return minutes


def _run_afl(dry_run: bool = False, log: RunLog = None) -> None:
    """Generate and post a casual AFL observation."""
    st = state_mod.load()

    posted_today = state_mod.posts_today(st)
    if posted_today >= config.MAX_POSTS_PER_DAY:
        print(f"already posted {posted_today} times today. skipping AFL post.")
        return

    print("generating afl post...")
    generation = signals.generate_afl_post()
    posts = generation["posts"][:1]

    if log:
        log.record_post_generation(
            stories_sent=0,
            posts=posts,
            claude_raw=generation["claude_raw_response"],
        )

    if not posts:
        print("no afl post generated.")
        return

    if dry_run:
        print(f"\n--- afl dry run ---\n  {posts[0]['text']}")
        if log:
            log.record_publish_result(posts[0]["text"], "", uri="(dry run)", success=True)
            log.set_outcome("dry_run")
    else:
        print("posting afl to bluesky...")
        bsky = publisher.create_client()
        try:
            uri = publisher.post(bsky, posts[0]["text"])
            state_mod.record_post(st, posts[0]["text"], "")
            print(f"  posted: {posts[0]['text']}")
            if log:
                log.record_publish_result(posts[0]["text"], "", uri=uri, success=True)
                log.set_outcome("posted")
        except Exception as e:
            print(f"  failed to post afl: {e}")
            if log:
                log.record_publish_result(posts[0]["text"], "", success=False, error=str(e))
                log.add_error(f"afl post failed: {e}")

    state_mod.save(st)
    print("done.")


def run(dry_run: bool = False, fetch_only: bool = False, log: RunLog = None) -> None:
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

    if log:
        log.record_feed_intake(len(all_articles), len(relevant), len(new_articles), new_articles)

    if fetch_only:
        print("\n--- articles ---")
        for a in new_articles[:20]:
            print(f"  [{a['source']}] {a['title']}")
            print(f"    {a['link']}")
        return

    if not new_articles:
        print("no new relevant articles. nothing to do.")
        if log:
            log.set_outcome("skipped_no_articles")
        return

    # --- Check daily limit ---
    posted_today = state_mod.posts_today(st)
    remaining = config.MAX_POSTS_PER_DAY - posted_today
    if remaining <= 0:
        print(f"already posted {posted_today} times today (limit: {config.MAX_POSTS_PER_DAY}). skipping.")
        if log:
            log.set_outcome("skipped_daily_limit")
        return
    posts_this_run = min(config.MAX_POSTS_PER_RUN, remaining)

    # --- Select + Generate ---
    print("selecting stories with claude...")
    selection = signals.select_stories(new_articles, count=posts_this_run + 2)
    selected = selection["selected"]
    print(f"  selected {len(selected)} stories")

    if log:
        log.record_story_selection(
            considered=selection["articles_sent"],
            selected_stories=selected,
            claude_raw=selection["claude_raw_response"],
        )

    print("generating signal posts...")
    generation = signals.generate_posts(selected)
    posts = generation["posts"][:posts_this_run]
    theme_id = generation.get("theme", "")
    print(f"  generated {len(posts)} posts")

    if log:
        log.record_post_generation(
            stories_sent=generation["stories_sent"],
            posts=posts,
            claude_raw=generation["claude_raw_response"],
        )

    if not posts:
        print("no posts generated. check article quality or try again later.")
        if log:
            log.set_outcome("skipped_no_posts")
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
        if log:
            for p in posts:
                log.record_publish_result(p["text"], p["source_url"], uri="(dry run)", success=True)
            log.set_outcome("dry_run")
    else:
        print("posting to bluesky...")
        bsky = publisher.create_client()
        for i, p in enumerate(posts, 1):
            try:
                uri = publisher.post(bsky, p["text"])
                state_mod.record_post(st, p["text"], p["source_url"], theme=theme_id)
                print(f"  [{i}] posted: {p['text'][:80]}...")
                print(f"      uri: {uri}")
                if log:
                    log.record_publish_result(p["text"], p["source_url"], uri=uri, success=True)
            except Exception as e:
                print(f"  [{i}] failed to post: {e}")
                if log:
                    log.record_publish_result(p["text"], p["source_url"], success=False, error=str(e))
                    log.add_error(f"post failed: {e}")
        if log and not log.data["outcome"]:
            log.set_outcome("posted")

    state_mod.save(st)
    print("\ndone.")


def run_engage(dry_run: bool = False, log: RunLog = None) -> None:
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
    search_result = engage.search_relevant_posts(bsky, st)
    candidates = search_result["candidates"]
    queries_used = search_result["queries_used"]
    print(f"  found {len(candidates)} candidate posts")

    if not candidates:
        print("no suitable posts found to engage with.")
        if log:
            log.record_engagement(queries=queries_used, candidates=[])
        return

    # --- Select + Generate reply ---
    print("selecting post and generating reply...")
    result = engage.select_and_reply(candidates, state=st)

    if not result:
        print("claude decided none of the posts were worth replying to. fair enough.")
        if log:
            log.record_engagement(queries=queries_used, candidates=candidates)
        return

    post_info = result["post"]
    reply_text = result["reply"]
    claude_raw = result.get("claude_raw_response", "")

    if dry_run:
        print("\n--- engage dry run (not posting) ---")
        print(f"\n  original post by @{post_info['author']}:")
        print(f"    {post_info['text'][:200]}")
        print(f"\n  reply:")
        print(f"    {reply_text}")
        print(f"\n  post uri: {post_info['uri']}")
        if log:
            log.record_engagement(
                queries=queries_used, candidates=candidates,
                selected_post=post_info, reply_text=reply_text,
                reply_uri="(dry run)", claude_raw=claude_raw,
            )
    else:
        print("posting reply to bluesky...")
        try:
            uri = publisher.reply_to_post(bsky, post_info["uri"], post_info["cid"], reply_text)
            state_mod.record_reply(st, post_info["uri"], reply_text, author=post_info.get("author", ""))
            print(f"  replied to @{post_info['author']}: {reply_text[:80]}...")
            print(f"  reply uri: {uri}")
            if log:
                log.record_engagement(
                    queries=queries_used, candidates=candidates,
                    selected_post=post_info, reply_text=reply_text,
                    reply_uri=uri, claude_raw=claude_raw,
                )
        except Exception as e:
            print(f"  failed to post reply: {e}")
            if log:
                log.record_engagement(
                    queries=queries_used, candidates=candidates,
                    selected_post=post_info, reply_text=reply_text,
                    reply_success=False, reply_error=str(e), claude_raw=claude_raw,
                )
                log.add_error(f"reply failed: {e}")

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
        log = RunLog()
        log.set_run_type("scheduled")

        # Don't post during sleep hours
        if _is_sleep_hours():
            print("sleep hours. skipping.")
            log.set_timing(sleep_hours=True)
            log.set_outcome("skipped_sleep")
            log.push_to_github()
            return

        # Randomly skip some runs to avoid clockwork regularity
        if random.random() < config.SKIP_CHANCE:
            print("randomly skipping this run. (simulating being busy)")
            log.set_timing(skipped=True)
            log.set_outcome("skipped_random")
            log.push_to_github()
            return

        # Random delay so posts don't land exactly on the hour
        pre_delay = _random_delay(config.DELAY_MIN_MINUTES, config.DELAY_MAX_MINUTES, "pre-post delay")

        # ~12% chance of an AFL post instead of energy/trade
        if random.random() < 0.12:
            print("rolling the dice... afl post today.")
            _run_afl(dry_run=False, log=log)
        else:
            run(dry_run=False, log=log)

        # Gap between posting and replying
        engage_gap = _random_delay(config.ENGAGE_GAP_MIN_MINUTES, config.ENGAGE_GAP_MAX_MINUTES, "post-to-reply gap")

        run_engage(dry_run=False, log=log)

        log.set_timing(pre_delay=pre_delay, engage_gap=engage_gap)
        log.push_to_github()

    elif args.engage or args.engage_dry_run:
        run_engage(dry_run=args.engage_dry_run)
    else:
        run(dry_run=args.dry_run, fetch_only=args.fetch_only)


if __name__ == "__main__":
    main()
