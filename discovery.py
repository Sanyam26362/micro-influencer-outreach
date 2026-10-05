import os
import pandas as pd
from dotenv import load_dotenv
from googleapiclient.discovery import build

# Load environment variables
load_dotenv()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# Initialize the YouTube API client
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

def discover_micro_influencers(niche, target_count=50):
    print(f"Hunting for {target_count} '{niche}' micro-influencers (5k-100k subs)...")
    influencers = []
    next_page_token = None
    
    while len(influencers) < target_count:
        # 1. Search for channels matching the niche
        search_response = youtube.search().list(
            q=niche,
            part="snippet",
            type="channel",
            maxResults=50,
            pageToken=next_page_token,
            regionCode="US"
        ).execute()

        # Extract just the channel IDs from this page of results
        channel_ids = [item["snippet"]["channelId"] for item in search_response.get("items", [])]
        
        if not channel_ids:
            print("No more channels found.")
            break

        # 2. Fetch detailed statistics for this batch of channels
        channels_response = youtube.channels().list(
            id=",".join(channel_ids),
            part="snippet,statistics"
        ).execute()

        for channel in channels_response.get("items", []):
            stats = channel["statistics"]
            snippet = channel["snippet"]
            
            # Safely handle hidden subscriber counts
            sub_count = int(stats.get("subscriberCount", 0))
            
            # 3. Apply the Micro-Influencer filter
            if 5000 <= sub_count <= 100000:
                video_count = int(stats.get("videoCount", 1))
                view_count = int(stats.get("viewCount", 0))
                
                # Calculate basic engagement/performance metrics
                avg_views = view_count / video_count if video_count > 0 else 0
                
                influencers.append({
                    "Name": snippet.get("title"),
                    "Platform": "YouTube",
                    "Profile URL": f"https://www.youtube.com/channel/{channel['id']}",
                    "Followers": sub_count,
                    "Avg Views/Video": round(avg_views),
                    "Category / Niche": niche,
                    "Bio Snippet": snippet.get("description", "").replace("\n", " ")[:200]
                })
                
                # Break early if we hit our target mid-batch
                if len(influencers) >= target_count:
                    break

        print(f"Current valid profiles: {len(influencers)}/{target_count}")
        
        # 4. Handle Pagination
        next_page_token = search_response.get("nextPageToken")
        if not next_page_token:
            print("Reached the end of YouTube search results.")
            break
            
    return influencers

if __name__ == "__main__":
    target_niche = "tech reviews"
    data = discover_micro_influencers(target_niche, target_count=50)
    
    if data:
        df = pd.DataFrame(data)
        df.to_csv("discovered_influencers.csv", index=False)
        print(f"\nSuccess: Saved {len(data)} qualified profiles to discovered_influencers.csv")
    else:
        print("Failed to find any influencers matching the criteria.")