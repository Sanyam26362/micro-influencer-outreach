import os
import json
import pandas as pd
from dotenv import load_dotenv
from groq import Groq
import re

# Load environment variables
load_dotenv()

# Initialize the Groq client natively
# Make sure GROQ_API_KEY is set in your .env file
client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

def extract_email(text):
    """Regex to find emails in the bio snippet."""
    if not text or pd.isna(text):
        return "Not Found"
    
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    match = re.search(email_pattern, text)
    return match.group(0) if match else "Not Found"

def enrich_and_classify_profile(bio, channel_name):
    """Uses Groq (Llama 3.3 70B) natively to classify niche and extract themes."""
    if not bio or pd.isna(bio) or len(str(bio).strip()) < 10:
        return {
            "Status": "Rejected", 
            "Reason": "Bio too short or missing", 
            "Niche": "Unknown", 
            "Themes": "Unknown"
        }

    prompt = f"""
    Analyze the following YouTube channel bio for '{channel_name}':
    "{bio}"
    
    Tasks:
    1. Determine if this channel fits the "Technology / Tech Reviews" niche. (True/False)
    2. Extract 2-3 specific content themes (e.g., "Smartphones, PC Builds").
    
    Return ONLY a valid JSON object exactly matching this structure:
    {{
        "is_tech_niche": true,
        "content_themes": "string of themes",
        "rejection_reason": null
    }}
    """

    try:
        response = client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a data enrichment assistant for influencer marketing. Output valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        
        result = json.loads(response.choices[0].message.content)
        
        if result.get("is_tech_niche"):
            return {
                "Status": "Qualified",
                "Reason": "Passed Niche Check",
                "Niche": "Technology",
                "Themes": result.get("content_themes", "Tech Hardware")
            }
        else:
            return {
                "Status": "Rejected",
                "Reason": result.get("rejection_reason", "Not a tech channel"),
                "Niche": "Other",
                "Themes": "N/A"
            }
            
    except Exception as e:
        print(f"Error enriching {channel_name}: {e}")
        return {"Status": "Error", "Reason": "API Failure", "Niche": "Unknown", "Themes": "Unknown"}

def process_dataset(input_csv="discovered_influencers.csv", output_csv="enriched_influencers.csv"):
    try:
        df = pd.read_csv(input_csv)
    except FileNotFoundError:
        print(f"Error: {input_csv} not found. Run discovery.py first.")
        return

    print(f"Processing {len(df)} profiles using Groq Llama 3.3...")
    
    statuses, reasons, niches, themes, emails = [], [], [], [], []

    for index, row in df.iterrows():
        name = row['Name']
        bio = row.get('Bio Snippet', '')
        
        # Basic view filter
        if row.get('Avg Views/Video', 0) < 300:
             statuses.append("Rejected")
             reasons.append("Low average views (< 300)")
             niches.append("Unknown")
             themes.append("N/A")
             emails.append(extract_email(bio))
             print(f"[{index+1}/{len(df)}] {name} -> Rejected (Low Views)")
             continue
            
        # AI Classification & Enrichment
        ai_data = enrich_and_classify_profile(bio, name)
        
        statuses.append(ai_data["Status"])
        reasons.append(ai_data["Reason"])
        niches.append(ai_data["Niche"])
        themes.append(ai_data["Themes"])
        emails.append(extract_email(bio))
        
        print(f"[{index+1}/{len(df)}] {name} -> {ai_data['Status']}")

    # Compile and save
    df['Status'] = statuses
    df['Rejection Reason'] = reasons
    df['Refined Niche'] = niches
    df['Content Themes'] = themes
    df['Contact Email'] = emails

    df.to_csv(output_csv, index=False)
    
    qualified_df = df[df['Status'] == 'Qualified'].copy()
    qualified_df.to_csv("qualified_influencers.csv", index=False)
    
    print(f"\nProcessing complete!")
    print(f"Total Profiles: {len(df)}")
    print(f"Qualified Profiles: {len(qualified_df)}")
    print(f"Data saved to {output_csv} and qualified_influencers.csv")

if __name__ == "__main__":
    process_dataset()