"""Bluesky AT Protocol publisher."""

from atproto import Client, models

import config


def create_client() -> Client:
    """Authenticate and return a Bluesky client."""
    client = Client()
    client.login(config.BLUESKY_HANDLE, config.BLUESKY_PASSWORD)
    return client


def post(client: Client, text: str) -> str:
    """Publish a text post to Bluesky. Returns the post URI."""
    response = client.send_post(text=text)
    return response.uri


def search_posts(client: Client, query: str, limit: int = 25):
    """Search Bluesky for posts matching a query."""
    response = client.app.bsky.feed.search_posts(
        models.AppBskyFeedSearchPosts.Params(
            q=query,
            limit=limit,
            sort="latest",
        )
    )
    return response.posts


def reply_to_post(client: Client, post_uri: str, post_cid: str, text: str) -> str:
    """Reply to a specific post. Returns the reply URI."""
    ref = models.ComAtprotoRepoStrongRef.Main(uri=post_uri, cid=post_cid)
    response = client.send_post(
        text=text,
        reply_to=models.AppBskyFeedPost.ReplyRef(root=ref, parent=ref),
    )
    return response.uri
