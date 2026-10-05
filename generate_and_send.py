import os
import json
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from groq import Groq
from datetime import datetime

# Load environment variables
load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# SMTP Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.getenv("SMTP_EMAIL")
SENDER_PASSWORD = os.getenv("SMTP_PASSWORD")
TEST_RECEIVER_EMAIL = "tu236661@gmail.com"  # All emails route here for testing

def generate_messages(row):
    """Generates a personalized email pitch and Instagram DM using Groq."""
    prompt = f"""
    You are a brand manager for an AI-powered SaaS product. Write two personalized outreach messages for a YouTube micro-influencer:

    Influencer Name: {row['Name']}
    Followers: {row['Followers']}
    Content Themes: {row['Content Themes']}
    Niche: {row['Refined Niche']}

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
        response = client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a professional outreach manager. Always output valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        result = json.loads(response.choices[0].message.content)
        return result.get("email_body", "Error generating email"), result.get("dm_body", "Error generating DM")
    except Exception as e:
        print(f"Error generating messages for {row['Name']}: {e}")
        return "Error", "Error"

def send_email_smtp(influencer_name, subject, body):
    """Sends the email using SMTP to the designated test inbox."""
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        return "SMTP Credentials Missing"

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = TEST_RECEIVER_EMAIL
    msg['Subject'] = subject

    # Add a note to the body indicating who this was intended for
    full_body = f"[TEST MODE - Intended for: {influencer_name}]\n\n{body}"
    msg.attach(MIMEText(full_body, 'plain'))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        return "Sent via SMTP"
    except Exception as e:
        return f"SMTP Error: {str(e)}"

def process_and_send():
    try:
        df = pd.read_csv("qualified_influencers.csv")
    except FileNotFoundError:
        print("Error: qualified_influencers.csv not found. Run process_data.py first.")
        return

    # For safety while testing, limit to the first 5 records so you don't spam yourself with 46 emails at once
    # Remove `.head(5)` to process the entire list
    df = df.head(5)
    
    print(f"Generating and sending pitches for {len(df)} influencers to {TEST_RECEIVER_EMAIL}...\n")
    tracker_log = []

    for index, row in df.iterrows():
        name = row['Name']
        original_email = row.get("Contact Email", "Not Found")

        # Generate personalized Email + DM
        email_body, dm_body = generate_messages(row)
        subject = f"Collaboration Opportunity: {name} x AI Startup"

        # Execute SMTP Send
        status = "Generated Only"
        if email_body != "Error":
             status = send_email_smtp(name, subject, email_body)

        print(f"[{index+1}/{len(df)}] {name} -> {status}")

        tracker_log.append({
            "Influencer": name,
            "Original Extracted Email": original_email,
            "Test Delivery Address": TEST_RECEIVER_EMAIL,
            "Email Pitch": email_body,
            "Instagram DM": dm_body,
            "Sent Status": status,
            "Date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    # Save Outreach Tracker
    tracker_df = pd.DataFrame(tracker_log)
    tracker_df.to_csv("outreach_tracker.csv", index=False)
    print(f"\nCompleted! Outreach log saved to outreach_tracker.csv.")

if __name__ == "__main__":
    process_and_send()