import json
import os
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Callable, Optional

import pandas as pd
from dotenv import load_dotenv
from groq import Groq

# Load environment variables
load_dotenv()

DEFAULT_SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
DEFAULT_SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))


def get_groq_client(api_key: Optional[str] = None) -> Groq:
    """Lazily initialize the Groq client."""
    key = (api_key or os.getenv("GROQ_API_KEY") or "").strip()
    if not key:
        raise ValueError(
            "GROQ_API_KEY is missing. Set it in your .env file, secrets, or UI."
        )
    return Groq(api_key=key)


def generate_messages(
    row: dict,
    brand_context: str = "an AI-powered SaaS product",
    model: str = "llama-3.3-70b-versatile",
    client: Optional[Groq] = None,
) -> tuple[str, str]:
    """Generates a personalized email pitch and Instagram DM using Groq."""
    prompt = f"""
    You are a brand manager for {brand_context}. Write two personalized outreach messages for a YouTube micro-influencer:

    Influencer Name: {row.get('Name', 'Creator')}
    Followers: {row.get('Followers', 'N/A')}
    Content Themes: {row.get('Content Themes', 'General Content')}
    Niche: {row.get('Refined Niche', row.get('Category / Niche', 'Tech'))}

    Requirements:
    1. "email_body": A professional collaboration email pitch (60-90 words). Reference their niche and content themes naturally.
    2. "dm_body": A short, friendly Instagram DM (15-30 words) following up on the email.

    Return ONLY a valid JSON object matching this structure:
    {{
        "email_body": "string",
        "dm_body": "string"
    }}
    """

    try:
        active_client = client or get_groq_client()
        response = active_client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional outreach manager. Always output valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        result = json.loads(response.choices[0].message.content)
        return (
            result.get("email_body", "Error generating email"),
            result.get("dm_body", "Error generating DM"),
        )
    except Exception as e:
        print(f"Error generating messages for {row.get('Name', 'Unknown')}: {e}")
        return f"Error: {str(e)[:80]}", "Error"


def send_email_smtp(
    influencer_name: str,
    subject: str,
    body: str,
    recipient_email: str,
    test_mode: bool = True,
    sender_email: Optional[str] = None,
    sender_password: Optional[str] = None,
    smtp_server: str = DEFAULT_SMTP_SERVER,
    smtp_port: int = DEFAULT_SMTP_PORT,
) -> str:
    """Sends an email using authenticated SMTP with STARTTLS."""
    from_email = (sender_email or os.getenv("SMTP_EMAIL") or "").strip()
    password = (sender_password or os.getenv("SMTP_PASSWORD") or "").strip()

    if not from_email or not password:
        return "SMTP Credentials Missing"

    if not recipient_email or recipient_email == "Not Found":
        return "Skipped (No Recipient Email)"

    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = recipient_email
    msg["Subject"] = subject

    if test_mode:
        full_body = f"[TEST MODE - Intended for: {influencer_name}]\n\n{body}"
    else:
        full_body = body

    msg.attach(MIMEText(full_body, "plain"))

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=20) as server:
            server.starttls()
            server.login(from_email, password)
            server.send_message(msg)
        return "Sent via SMTP (Test Mode)" if test_mode else "Sent via SMTP (Live)"
    except Exception as e:
        return f"SMTP Error: {str(e)}"


def process_and_send(
    df: Optional[pd.DataFrame] = None,
    input_csv: str = "qualified_influencers.csv",
    output_csv: Optional[str] = "outreach_tracker.csv",
    brand_context: str = "an AI-powered SaaS product",
    subject_template: str = "Collaboration Opportunity: {name} x AI Startup",
    model: str = "llama-3.3-70b-versatile",
    limit: Optional[int] = 5,
    mode: str = "test",  # "dry_run", "test", or "live"
    test_receiver_email: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    smtp_email: Optional[str] = None,
    smtp_password: Optional[str] = None,
    smtp_server: str = DEFAULT_SMTP_SERVER,
    smtp_port: int = DEFAULT_SMTP_PORT,
    delay_seconds: float = 1.0,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> pd.DataFrame:
    """Generate personalized copy and optionally dispatch via SMTP."""
    if df is None:
        if not os.path.exists(input_csv):
            raise FileNotFoundError(
                f"{input_csv} not found. Run process_data.py first."
            )
        df = pd.read_csv(input_csv)

    if limit and limit > 0:
        df = df.head(limit).copy()
    else:
        df = df.copy()

    groq_client = get_groq_client(groq_api_key)
    resolved_test_email = (
        test_receiver_email or os.getenv("TEST_RECEIVER_EMAIL") or ""
    ).strip()

    total = len(df)
    tracker_log: list[dict] = []

    for i, (_, row) in enumerate(df.iterrows(), start=1):
        name = row.get("Name", "Creator")
        original_email = row.get("Contact Email", "Not Found")
        if pd.isna(original_email) or not str(original_email).strip():
            original_email = "Not Found"

        email_body, dm_body = generate_messages(
            row=row.to_dict(),
            brand_context=brand_context,
            model=model,
            client=groq_client,
        )
        subject = subject_template.format(name=name)

        target_address = "N/A (Dry Run)"
        if email_body.startswith("Error"):
            status = "Generation Failed"
        elif mode == "dry_run":
            status = "Generated Only (Dry Run)"
        elif mode == "test":
            target_address = resolved_test_email
            if not resolved_test_email:
                status = "Test Receiver Email Missing"
            else:
                status = send_email_smtp(
                    influencer_name=name,
                    subject=subject,
                    body=email_body,
                    recipient_email=resolved_test_email,
                    test_mode=True,
                    sender_email=smtp_email,
                    sender_password=smtp_password,
                    smtp_server=smtp_server,
                    smtp_port=smtp_port,
                )
        elif mode == "live":
            target_address = original_email
            status = send_email_smtp(
                influencer_name=name,
                subject=subject,
                body=email_body,
                recipient_email=original_email,
                test_mode=False,
                sender_email=smtp_email,
                sender_password=smtp_password,
                smtp_server=smtp_server,
                smtp_port=smtp_port,
            )
        else:
            status = f"Unknown Mode: {mode}"

        if progress_callback:
            progress_callback(i, total, f"[{i}/{total}] {name} -> {status}")
        else:
            print(f"[{i}/{total}] {name} -> {status}")

        tracker_log.append(
            {
                "Influencer": name,
                "Original Extracted Email": original_email,
                "Delivery Address": target_address,
                "Subject": subject,
                "Email Pitch": email_body,
                "Instagram DM": dm_body,
                "Sent Status": status,
                "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

        # Rate-limit delay between live/test SMTP sends
        if mode in ("test", "live") and delay_seconds > 0 and i < total:
            time.sleep(delay_seconds)

    tracker_df = pd.DataFrame(tracker_log)
    if output_csv:
        tracker_df.to_csv(output_csv, index=False)
        print(f"\nCompleted! Outreach log saved to {output_csv}.")

    return tracker_df


if __name__ == "__main__":
    default_mode = os.getenv("OUTREACH_MODE", "test")
    default_limit = int(os.getenv("OUTREACH_LIMIT", "5"))
    default_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    process_and_send(mode=default_mode, limit=default_limit, model=default_model)
