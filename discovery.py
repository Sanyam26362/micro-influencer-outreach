import os
from typing import Callable, Optional

import pandas as pd
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variables from .env if present
load_dotenv()


def get_youtube_client(api_key: Optional[str] = None):
    """Lazily initialize the YouTube Data API v3 client."""
    key = (api_key or os.getenv("YOUTUBE_API_KEY") or "").strip()
    if not key:
        raise ValueError(
            "YOUTUBE_API_KEY is missing. Set it in your .env file, Streamlit secrets, or UI sidebar."
        )
    return build("youtube", "v3", developerKey=key)


def discover_micro_influencers(
    niche: str,
    target_count: int = 50,
    min_subs: int = 5000,
    max_subs: int = 100000,
    region_code: str = "US",
    api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> list[dict]:
    """Search YouTube for channels matching a niche within subscriber bounds."""
    youtube = get_youtube_client(api_key)
    print(
        f"Hunting for {target_count} '{niche}' micro-influencers "
        f"({min_subs:,}-{max_subs:,} subs)..."
    )

    influencers: list[dict] = []
    seen_channel_ids: set[str] = set()
    next_page_token: Optional[str] = None

    while len(influencers) < target_count:
        try:
            search_kwargs = {
                "q": niche,
                "part": "snippet",
                "type": "channel",
                "maxResults": 50,
                "pageToken": next_page_token,
            }
            if region_code:
                search_kwargs["regionCode"] = region_code

            search_response = youtube.search().list(**search_kwargs).execute()
        except HttpError as err:
            raise RuntimeError(f"YouTube Search API error: {err}") from err

        # Extract unique channel IDs from this page of results
        channel_ids = [
            item["snippet"]["channelId"]
            for item in search_response.get("items", [])
            if item.get("snippet", {}).get("channelId")
            and item["snippet"]["channelId"] not in seen_channel_ids
        ]

        if not channel_ids:
            next_page_token = search_response.get("nextPageToken")
            if not next_page_token:
                print("No more channels found.")
                break
            continue

        seen_channel_ids.update(channel_ids)

        try:
            channels_response = (
                youtube.channels()
                .list(id=",".join(channel_ids), part="snippet,statistics")
                .execute()
            )
        except HttpError as err:
            raise RuntimeError(f"YouTube Channels API error: {err}") from err

        for channel in channels_response.get("items", []):
            stats = channel.get("statistics", {})
            snippet = channel.get("snippet", {})

            # Safely handle hidden subscriber counts
            sub_count = int(stats.get("subscriberCount", 0))

            # Apply the Micro-Influencer filter
            if min_subs <= sub_count <= max_subs:
                video_count = int(stats.get("videoCount", 0))
                view_count = int(stats.get("viewCount", 0))

                avg_views = view_count / video_count if video_count > 0 else 0

                influencers.append(
                    {
                        "Name": snippet.get("title", "Unknown"),
                        "Platform": "YouTube",
                        "Profile URL": f"https://www.youtube.com/channel/{channel['id']}",
                        "Followers": sub_count,
                        "Avg Views/Video": round(avg_views),
                        "Category / Niche": niche,
                        "Bio Snippet": snippet.get("description", "")
                        .replace("\n", " ")
                        .strip()[:200],
                    }
                )

                if progress_callback:
                    progress_callback(
                        len(influencers),
                        target_count,
                        f"Found {len(influencers)}/{target_count}: {snippet.get('title', 'Unknown')}",
                    )

                if len(influencers) >= target_count:
                    break

        print(f"Current valid profiles: {len(influencers)}/{target_count}")

        next_page_token = search_response.get("nextPageToken")
        if not next_page_token:
            print("Reached the end of YouTube search results.")
            break

    return influencers


if __name__ == "__main__":
    target_niche = os.getenv("TARGET_NICHE", "tech reviews")
    target_count = int(os.getenv("TARGET_COUNT", "50"))
    data = discover_micro_influencers(target_niche, target_count=target_count)

    if data:
        df = pd.DataFrame(data)
        df.to_csv("discovered_influencers.csv", index=False)
        print(
            f"\nSuccess: Saved {len(data)} qualified profiles to discovered_influencers.csv"
        )
    else:
        print("Failed to find any influencers matching the criteria.")
