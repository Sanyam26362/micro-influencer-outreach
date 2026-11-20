import json
import os
import re
from typing import Callable, Optional

import pandas as pd
from dotenv import load_dotenv
from groq import Groq

# Load environment variables
load_dotenv()

FALLBACK_GROQ_MODELS = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]


def get_groq_client(api_key: Optional[str] = None) -> Groq:
    """Initialize Groq client from argument or environment."""
    key = (api_key or os.getenv("GROQ_API_KEY") or "").strip()
    if not key:
        raise ValueError(
            "GROQ_API_KEY is missing. Set it in your .env file, secrets, or UI."
        )
    return Groq(api_key=key)


def extract_email(text: str) -> str:
    """Regex to find emails in text (bio snippet)."""
    if not text or pd.isna(text):
        return "Not Found"

    email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    match = re.search(email_pattern, str(text))
    return match.group(0) if match else "Not Found"


def enrich_and_classify_profile(
    bio: str,
    channel_name: str,
    target_niche_label: str = "Technology / Tech Reviews",
    model: str = "qwen/qwen3.8-27b",
    client: Optional[Groq] = None,
) -> dict:
    """Uses Groq natively to classify niche and extract themes."""
    if not bio or pd.isna(bio) or len(str(bio).strip()) < 10:
        return {
            "Status": "Rejected",
            "Reason": "Bio too short or missing (< 10 chars)",
            "Niche": "Unknown",
            "Themes": "Unknown",
        }

    prompt = f"""
    Analyze the following YouTube channel bio for '{channel_name}':
    "{bio}"

    Tasks:
    1. Determine if this channel fits the "{target_niche_label}" niche. (True/False)
    2. Extract 2-3 specific content themes (e.g., "Smartphones, PC Builds, Audio Gear").
    3. If not relevant, explain why in rejection_reason.

    Return ONLY a valid JSON object matching this schema:
    {{
        "is_niche_match": true,
        "content_themes": "string of themes",
        "rejection_reason": null
    }}
    """

    try:
        active_client = client or get_groq_client()
        messages = [
            {
                "role": "system",
                "content": "You are a data enrichment assistant for influencer marketing. Output valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ]

        # Attempt with specified model, with automatic fallback if model doesn't exist
        try:
            response = active_client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=messages,
                temperature=0.1,
            )
        except Exception as model_err:
            err_msg = str(model_err).lower()
            if "404" in err_msg or "model" in err_msg or "does not exist" in err_msg:
                # Try fallback models
                fallback_used = False
                for fb in FALLBACK_GROQ_MODELS:
                    if fb != model:
                        try:
                            response = active_client.chat.completions.create(
                                model=fb,
                                response_format={"type": "json_object"},
                                messages=messages,
                                temperature=0.1,
                            )
                            fallback_used = True
                            break
                        except Exception:
                            continue
                if not fallback_used:
                    raise model_err
            else:
                raise model_err

        result = json.loads(response.choices[0].message.content)

        is_match = result.get("is_niche_match") or result.get("is_tech_niche")
        if is_match:
            return {
                "Status": "Qualified",
                "Reason": "Passed Niche Check",
                "Niche": target_niche_label.split("/")[0].strip(),
                "Themes": result.get("content_themes") or "General Tech Reviews",
            }
        else:
            return {
                "Status": "Rejected",
                "Reason": result.get(
                    "rejection_reason", f"Not in {target_niche_label}"
                ),
                "Niche": "Other",
                "Themes": "N/A",
            }

    except Exception as e:
        print(f"Error enriching {channel_name}: {e}")
        return {
            "Status": "Error",
            "Reason": f"API Failure: {str(e)[:50]}",
            "Niche": "Unknown",
            "Themes": "Unknown",
        }


def process_dataset(
    df: Optional[pd.DataFrame] = None,
    input_csv: str = "discovered_influencers.csv",
    output_csv: str = "enriched_influencers.csv",
    min_views_threshold: int = 300,
    target_niche_label: str = "Technology / Tech Reviews",
    model: str = "qwen/qwen3.8-27b",
    groq_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Process influencers, apply engagement floor and LLM enrichment."""
    if df is None:
        if not os.path.exists(input_csv):
            raise FileNotFoundError(f"{input_csv} not found. Run discovery first.")
        df = pd.read_csv(input_csv)

    total = len(df)
    print(f"Processing {total} profiles using Groq ({model})...")

    groq_client = get_groq_client(groq_api_key)

    statuses, reasons, niches, themes, emails = [], [], [], [], []

    for index, row in df.iterrows():
        name = row.get("Name", "Unknown")
        bio = row.get("Bio Snippet", "")
        avg_views = row.get("Avg Views/Video", 0)

        # Basic engagement floor filter
        if pd.isna(avg_views) or avg_views < min_views_threshold:
            statuses.append("Rejected")
            reasons.append(f"Low average views (< {min_views_threshold})")
            niches.append("Unknown")
            themes.append("N/A")
            emails.append(extract_email(bio))
            if progress_callback:
                progress_callback(
                    index + 1, total, f"[{index+1}/{total}] {name} -> Rejected (Low Views)"
                )
            continue

        # AI Classification & Enrichment
        ai_data = enrich_and_classify_profile(
            bio=bio,
            channel_name=name,
            target_niche_label=target_niche_label,
            model=model,
            client=groq_client,
        )

        statuses.append(ai_data["Status"])
        reasons.append(ai_data["Reason"])
        niches.append(ai_data["Niche"])
        themes.append(ai_data["Themes"])
        emails.append(extract_email(bio))

        if progress_callback:
            progress_callback(
                index + 1, total, f"[{index+1}/{total}] {name} -> {ai_data['Status']}"
            )

    df["Status"] = statuses
    df["Rejection Reason"] = reasons
    df["Refined Niche"] = niches
    df["Content Themes"] = themes
    df["Contact Email"] = emails

    if output_csv:
        df.to_csv(output_csv, index=False)

    qualified_df = df[df["Status"] == "Qualified"].copy()
    if output_csv:
        qualified_df.to_csv("qualified_influencers.csv", index=False)

    return df, qualified_df


if __name__ == "__main__":
    enriched_df, qualified_df = process_dataset()
    print(f"\nProcessing complete!")
    print(f"Total Profiles: {len(enriched_df)}")
    print(f"Qualified Profiles: {len(qualified_df)}")
    print(
        "Data saved to enriched_influencers.csv and qualified_influencers.csv"
    )
