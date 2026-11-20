import os
import time
from datetime import datetime
import pandas as pd
import streamlit as st
from groq import Groq

from discovery import discover_micro_influencers
from process_data import process_dataset, extract_email
from generate_and_send import (
    process_and_send,
    send_email_smtp,
    generate_messages,
    get_groq_client,
)


def normalize_tracker_df(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure tracker DataFrame always has the expected column names regardless of CSV version."""
    # Handle old schema: 'Email' → 'Original Extracted Email'
    if "Email" in df.columns and "Original Extracted Email" not in df.columns:
        df = df.rename(columns={"Email": "Original Extracted Email"})
    # Add missing columns with defaults
    for col, default in [
        ("Original Extracted Email", "Not Found"),
        ("Delivery Address", "N/A"),
        ("Subject", "Collaboration Opportunity"),
        ("Email Pitch", ""),
        ("Instagram DM", ""),
        ("Sent Status", "Unknown"),
        ("Date", ""),
    ]:
        if col not in df.columns:
            df[col] = default
    return df

# Page configuration
st.set_page_config(
    page_title="Micro-Influencer Outreach Pipeline",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 15px;
        border-left: 5px solid #ff4b4b;
        margin-bottom: 10px;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 48px;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Helper function to dynamically list models supported by the user's Groq key
def get_supported_groq_models(api_key: str) -> list[str]:
    defaults = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    if not api_key:
        return defaults
    try:
        client = Groq(api_key=api_key)
        fetched = [
            m.id
            for m in client.models.list().data
            if not m.id.startswith("whisper") and "guard" not in m.id
        ]
        if "qwen/qwen3.8-27b" in fetched:
            fetched.remove("qwen/qwen3.8-27b")
            fetched.insert(0, "qwen/qwen3.8-27b")
        return fetched if fetched else defaults
    except Exception:
        return defaults

# Session state initialization
if "discovered_df" not in st.session_state:
    if os.path.exists("discovered_influencers.csv"):
        st.session_state.discovered_df = pd.read_csv("discovered_influencers.csv")
    else:
        st.session_state.discovered_df = pd.DataFrame()

if "enriched_df" not in st.session_state:
    if os.path.exists("enriched_influencers.csv"):
        st.session_state.enriched_df = pd.read_csv("enriched_influencers.csv")
    else:
        st.session_state.enriched_df = pd.DataFrame()

if "qualified_df" not in st.session_state:
    if os.path.exists("qualified_influencers.csv"):
        st.session_state.qualified_df = pd.read_csv("qualified_influencers.csv")
    else:
        st.session_state.qualified_df = pd.DataFrame()

if "tracker_df" not in st.session_state:
    if os.path.exists("outreach_tracker.csv"):
        st.session_state.tracker_df = normalize_tracker_df(pd.read_csv("outreach_tracker.csv"))
    else:
        st.session_state.tracker_df = pd.DataFrame()

# ---------------------------------------------------------
# Sidebar: Credentials & Global Settings
# ---------------------------------------------------------
with st.sidebar:
    st.image(
        "https://img.icons8.com/fluency/96/rocket.png",
        width=60,
    )
    st.title("Outreach Engine")
    st.caption("AI-Powered YouTube Micro-Influencer Discovery & Outreach")
    st.divider()

    st.subheader("🔑 API & Credentials")

    default_yt = os.getenv("YOUTUBE_API_KEY", "")
    default_groq = os.getenv("GROQ_API_KEY", "")
    default_smtp_email = os.getenv("SMTP_EMAIL", "")
    default_smtp_pwd = os.getenv("SMTP_PASSWORD", "")
    default_test_receiver = os.getenv("TEST_RECEIVER_EMAIL", "")

    # Try reading from Streamlit Secrets if deployed
    try:
        if not default_yt and "YOUTUBE_API_KEY" in st.secrets:
            default_yt = st.secrets["YOUTUBE_API_KEY"]
        if not default_groq and "GROQ_API_KEY" in st.secrets:
            default_groq = st.secrets["GROQ_API_KEY"]
        if not default_smtp_email and "SMTP_EMAIL" in st.secrets:
            default_smtp_email = st.secrets["SMTP_EMAIL"]
        if not default_smtp_pwd and "SMTP_PASSWORD" in st.secrets:
            default_smtp_pwd = st.secrets["SMTP_PASSWORD"]
        if not default_test_receiver and "TEST_RECEIVER_EMAIL" in st.secrets:
            default_test_receiver = st.secrets["TEST_RECEIVER_EMAIL"]
    except Exception:
        pass

    youtube_api_key = st.text_input(
        "YouTube API Key",
        value=default_yt,
        type="password",
        help="Get from Google Cloud Console with YouTube Data API v3 enabled.",
    )
    groq_api_key = st.text_input(
        "Groq Cloud API Key",
        value=default_groq,
        type="password",
        help="Get from console.groq.com. Uses qwen/qwen3.8-27b.",
    )

    with st.expander("📧 SMTP Email Settings", expanded=True):
        smtp_email = st.text_input(
            "Sender Email (Gmail)",
            value=default_smtp_email,
            help="Your Gmail address.",
        )
        smtp_password = st.text_input(
            "Gmail App Password",
            value=default_smtp_pwd,
            type="password",
            help="16-character App Password generated in Google Account Security.",
        )
        test_receiver_email = st.text_input(
            "Test Mode Receiver Inbox",
            value=default_test_receiver or "tu236661@gmail.com",
            help="All test emails will be safely routed here.",
        )

        test_smtp_btn = st.button("🧪 Send Test Email (Verify SMTP)", use_container_width=True)
        if test_smtp_btn:
            if not smtp_email.strip() or not smtp_password.strip():
                st.error("Sender email and App Password are required.")
            elif not test_receiver_email.strip():
                st.error("Test receiver email is required.")
            else:
                with st.spinner("Connecting to smtp.gmail.com:587 with STARTTLS..."):
                    res = send_email_smtp(
                        influencer_name="Admin Test",
                        subject="SMTP Handshake Test - Micro-Influencer Pipeline",
                        body="This is an automated verification test confirming your Gmail SMTP credentials and STARTTLS handshake are functioning properly.",
                        recipient_email=test_receiver_email.strip(),
                        test_mode=True,
                        sender_email=smtp_email.strip(),
                        sender_password=smtp_password.strip(),
                    )
                    if "Sent via SMTP" in res:
                        st.success(f"✅ Handshake verified! Email sent to `{test_receiver_email.strip()}`")
                    else:
                        st.error(f"❌ {res}")

    st.divider()
    st.markdown(
        """
        **System Status:**
        - Discovery: 🟢 Ready
        - AI Vetting: 🟢 Ready
        - Dispatch: 🟢 Ready
        """
    )
    st.caption("v1.2.0 • Qwen Engine & Direct Dispatch")

# Fetch available models from Groq
groq_models_list = get_supported_groq_models(groq_api_key.strip())

# ---------------------------------------------------------
# Main Page Header
# ---------------------------------------------------------
st.title("🎯 Micro-Influencer Discovery & Outreach Pipeline")
st.markdown(
    "Automate YouTube creator discovery, verify engagement and topical alignment with **Groq LLMs**, "
    "and synthesize hyper-personalized multi-channel copy ready for dispatch."
)

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "1️⃣ Discovery (YouTube)",
        "2️⃣ AI Qualification & Themes",
        "3️⃣ Copy & Outreach Dispatch",
        "📊 Campaign Tracker",
    ]
)

# ---------------------------------------------------------
# TAB 1: Channel Discovery
# ---------------------------------------------------------
with tab1:
    st.subheader("Phase 1: Precision YouTube Micro-Influencer Discovery")
    st.markdown(
        "Searches channels by niche, filters by subscriber bracket (5k–100k), and calculates average views per video."
    )

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        niche_query = st.text_input(
            "Target Search Niche",
            value="tech reviews",
            help="Keywords to find relevant creators (e.g. 'tech reviews', 'pc build', 'fitness workout').",
        )
    with col2:
        target_count = st.number_input(
            "Target Creators Count", min_value=5, max_value=100, value=20, step=5
        )
    with col3:
        region_code = st.selectbox(
            "Region Code",
            ["US", "IN", "GB", "CA", "AU", "DE", "ALL"],
            index=0,
            help="Filter search to specific country code.",
        )

    sub_col1, sub_col2 = st.columns(2)
    with sub_col1:
        min_subs = st.number_input(
            "Min Subscribers", min_value=1000, max_value=50000, value=5000, step=1000
        )
    with sub_col2:
        max_subs = st.number_input(
            "Max Subscribers", min_value=10000, max_value=500000, value=100000, step=5000
        )

    run_discovery = st.button("🚀 Run YouTube Discovery", type="primary", use_container_width=True)

    if run_discovery:
        if not youtube_api_key.strip():
            st.error("❌ YouTube API Key is missing. Please provide it in the sidebar.")
        else:
            progress_bar = st.progress(0.0)
            status_text = st.empty()

            def update_disc_progress(current, total, msg):
                progress = min(current / max(total, 1), 1.0)
                progress_bar.progress(progress)
                status_text.text(msg)

            with st.spinner("Connecting to YouTube Data API v3..."):
                try:
                    reg = None if region_code == "ALL" else region_code
                    results = discover_micro_influencers(
                        niche=niche_query,
                        target_count=int(target_count),
                        min_subs=int(min_subs),
                        max_subs=int(max_subs),
                        region_code=reg,
                        api_key=youtube_api_key.strip(),
                        progress_callback=update_disc_progress,
                    )
                    if results:
                        df_res = pd.DataFrame(results)
                        st.session_state.discovered_df = df_res
                        df_res.to_csv("discovered_influencers.csv", index=False)
                        progress_bar.progress(1.0)
                        status_text.success(
                            f"✅ Successfully discovered {len(results)} micro-influencers!"
                        )
                    else:
                        st.warning("No channels matched your criteria. Try broadening your subscriber bounds or search term.")
                except Exception as e:
                    st.error(f"Discovery Error: {e}")

    if not st.session_state.discovered_df.empty:
        st.divider()
        st.subheader("Discovered Creators Dataset")
        df_show = st.session_state.discovered_df.copy()
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Creators", len(df_show))
        m2.metric("Avg Subscribers", f"{int(df_show['Followers'].mean()):,}")
        m3.metric("Avg Views/Video", f"{int(df_show['Avg Views/Video'].mean()):,}")

        st.dataframe(
            df_show,
            use_container_width=True,
            column_config={
                "Profile URL": st.column_config.LinkColumn("YouTube Channel"),
                "Followers": st.column_config.NumberColumn(format="%d subs"),
                "Avg Views/Video": st.column_config.NumberColumn(format="%d views"),
            },
        )

        st.download_button(
            "📥 Download discovered_influencers.csv",
            data=df_show.to_csv(index=False).encode("utf-8"),
            file_name="discovered_influencers.csv",
            mime="text/csv",
        )

# ---------------------------------------------------------
# TAB 2: AI Qualification & Theme Extraction
# ---------------------------------------------------------
with tab2:
    st.subheader("Phase 2: AI Qualification, Email Extraction & Theme Analysis")
    st.markdown(
        "Filters out inactive channels (low average views), parses contact emails from bio snippets using regex, "
        "and uses **Groq LLM** to verify niche fit and extract granular content themes."
    )

    if st.session_state.discovered_df.empty:
        st.info("ℹ️ Please run **Phase 1: Discovery** first or upload an existing `discovered_influencers.csv` below.")
        uploaded_disc = st.file_uploader("Upload discovered_influencers.csv", type=["csv"], key="upload_disc")
        if uploaded_disc:
            st.session_state.discovered_df = pd.read_csv(uploaded_disc)
            st.rerun()
    else:
        q_col1, q_col2, q_col3 = st.columns([1, 1, 1])
        with q_col1:
            min_views = st.number_input(
                "Min Average Views Floor",
                min_value=50,
                max_value=5000,
                value=300,
                step=50,
                help="Weeds out dead channels whose videos get fewer than this threshold.",
            )
        with q_col2:
            groq_model = st.selectbox(
                "Groq LLM Model",
                groq_models_list,
                index=0,
                help="Recommended: qwen/qwen3.8-27b (tested & reliable on Groq).",
            )
        with q_col3:
            target_niche_label = st.text_input(
                "Target Niche Verification",
                value="Technology / Tech Reviews",
                help="The thematic criteria checked by the LLM.",
            )

        run_qualification = st.button("🧠 Run AI Qualification & Enrichment", type="primary", use_container_width=True)

        if run_qualification:
            if not groq_api_key.strip():
                st.error("❌ Groq API Key is missing. Please provide it in the sidebar.")
            else:
                q_bar = st.progress(0.0)
                q_text = st.empty()

                def update_qual_progress(cur, tot, msg):
                    q_bar.progress(min(cur / max(tot, 1), 1.0))
                    q_text.text(msg)

                with st.spinner(f"Analyzing channel bios and themes with Groq ({groq_model})..."):
                    try:
                        enriched, qualified = process_dataset(
                            df=st.session_state.discovered_df.copy(),
                            min_views_threshold=int(min_views),
                            target_niche_label=target_niche_label,
                            model=groq_model,
                            groq_api_key=groq_api_key.strip(),
                            progress_callback=update_qual_progress,
                        )
                        st.session_state.enriched_df = enriched
                        st.session_state.qualified_df = qualified
                        q_bar.progress(1.0)
                        if len(qualified) > 0:
                            q_text.success(
                                f"✅ Vetting complete! {len(qualified)}/{len(enriched)} creators Qualified."
                            )
                        else:
                            q_text.warning(
                                f"⚠️ Vetting finished: 0/{len(enriched)} creators qualified. Check the 'Rejected Channels' tab for error details."
                            )
                    except Exception as e:
                        st.error(f"Enrichment Error: {e}")

        if not st.session_state.enriched_df.empty:
            st.divider()
            en_df = st.session_state.enriched_df
            qu_df = st.session_state.qualified_df

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Analyzed", len(en_df))
            pct_qual = f"{len(qu_df)/len(en_df)*100:.1f}%" if len(en_df) > 0 else "0%"
            c2.metric("Qualified Leads", len(qu_df), delta=pct_qual)
            emails_found = en_df[en_df["Contact Email"] != "Not Found"]
            c3.metric("Emails Extracted", len(emails_found))
            rejected_count = len(en_df) - len(qu_df)
            c4.metric("Rejected / Errors", rejected_count)

            sub_tab1, sub_tab2 = st.tabs(["✅ Qualified Leads", "❌ Rejected Channels"])
            with sub_tab1:
                if not qu_df.empty:
                    st.dataframe(
                        qu_df[["Name", "Followers", "Avg Views/Video", "Content Themes", "Contact Email", "Profile URL"]],
                        use_container_width=True,
                        column_config={"Profile URL": st.column_config.LinkColumn("YouTube")},
                    )
                    st.download_button(
                        "📥 Download qualified_influencers.csv",
                        data=qu_df.to_csv(index=False).encode("utf-8"),
                        file_name="qualified_influencers.csv",
                        mime="text/csv",
                    )
                else:
                    st.warning("No qualified creators found yet. Check the 'Rejected Channels' tab to see why they failed.")
            with sub_tab2:
                rej_df = en_df[en_df["Status"] != "Qualified"]
                st.dataframe(
                    rej_df[["Name", "Followers", "Avg Views/Video", "Status", "Rejection Reason", "Profile URL"]],
                    use_container_width=True,
                    column_config={"Profile URL": st.column_config.LinkColumn("YouTube")},
                )

# ---------------------------------------------------------
# TAB 3: Copy Generation & Outreach Dispatch
# ---------------------------------------------------------
with tab3:
    st.subheader("Phase 3: Hyper-Personalized Copy Synthesis & SMTP Outreach")
    st.markdown(
        "Synthesizes tailored collaboration pitches (60–90 words) referencing specific channel themes, "
        "along with punchy companion Instagram DMs (15–30 words), and sends them via SMTP."
    )

    # Direct Manual Email Dispatcher expander (Always available regardless of pipeline state)
    with st.expander("✉️ Direct Quick Email Sender (Send Any Email Now)", expanded=False):
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            direct_recipient = st.text_input("Send To:", value=test_receiver_email.strip())
            direct_subj = st.text_input("Subject:", value="Collaboration Inquiry - Tech Creator Partnership")
        with d_col2:
            direct_name = st.text_input("Creator / Recipient Name:", value="Creator")
        
        direct_body = st.text_area(
            "Email Message Body:",
            value="Hi there,\n\nI really enjoy your tech reviews and breakdown videos. We have built an AI-powered SaaS tool that helps creators streamline production and would love to offer you a free premium tier.\n\nBest regards,\nPartnership Team",
            height=120,
        )
        if st.button("📨 Send Direct Email Now", type="secondary"):
            if not smtp_email.strip() or not smtp_password.strip():
                st.error("❌ SMTP Sender Email or Gmail App Password is missing in sidebar.")
            elif not direct_recipient.strip():
                st.error("❌ Recipient email is required.")
            else:
                with st.spinner("Dispatching email..."):
                    res = send_email_smtp(
                        influencer_name=direct_name,
                        subject=direct_subj,
                        body=direct_body,
                        recipient_email=direct_recipient.strip(),
                        test_mode=False,
                        sender_email=smtp_email.strip(),
                        sender_password=smtp_password.strip(),
                    )
                    if "Sent via SMTP" in res:
                        st.success(f"✅ Email successfully delivered to `{direct_recipient.strip()}`!")
                    else:
                        st.error(f"❌ {res}")

    st.divider()

    # Fallback / Shortcut if Phase 2 failed or has 0 qualified leads
    if st.session_state.qualified_df.empty:
        st.warning(
            "⚠️ **No Qualified Creators Found in Phase 2.**\n\n"
            "If you got `API Failure: Error code: 404`, it was because `llama-3.3-70b-versatile` was selected. "
            "Please go back to **Tab 2**, select **`qwen/qwen3.8-27b`**, and re-run AI Qualification!"
        )

        if not st.session_state.discovered_df.empty:
            st.info(
                f"💡 **Shortcut**: You have **{len(st.session_state.discovered_df)} discovered channels** from Phase 1. "
                "Click the button below to promote them directly to Qualified Leads and generate/send emails immediately!"
            )
            if st.button("⚡ Promote Discovered Creators Directly to Outreach (Bypass Vetting)", type="primary"):
                promoted = st.session_state.discovered_df.copy()
                promoted["Status"] = "Qualified"
                promoted["Refined Niche"] = promoted.get("Category / Niche", "Technology")
                promoted["Content Themes"] = "Tech Hardware, Gadgets & Consumer Electronics"
                promoted["Contact Email"] = promoted["Bio Snippet"].apply(extract_email)
                st.session_state.qualified_df = promoted
                promoted.to_csv("qualified_influencers.csv", index=False)
                st.success("✅ Promoted all discovered creators to Qualified! Re-opening Outreach options...")
                st.rerun()

        uploaded_qual = st.file_uploader("Or upload qualified_influencers.csv", type=["csv"], key="upload_qual")
        if uploaded_qual:
            st.session_state.qualified_df = pd.read_csv(uploaded_qual)
            st.rerun()
    else:
        out_col1, out_col2 = st.columns([1, 1])
        with out_col1:
            outreach_mode = st.radio(
                "Default Outreach Mode",
                options=["test", "live", "dry_run"],
                format_func=lambda x: {
                    "test": f"🧪 Test Mode (Safely routes emails to: {test_receiver_email or 'Test Inbox'})",
                    "live": "🚀 Live Mode (Sends directly to each creator's extracted email address)",
                    "dry_run": "🛡️ Dry Run / Preview Only (Generates copy without sending emails)",
                }[x],
                help="Test mode lets you verify email deliverability safely. Live mode delivers to real creator inboxes.",
            )
            brand_context = st.text_area(
                "Brand / Product Value Proposition",
                value="an AI-powered SaaS product that automates video editing and content repurposing for creators",
                help="Context fed into LLM so the pitch highlights your exact product value.",
            )

        with out_col2:
            outreach_batch_limit = st.slider(
                "Batch Limit",
                min_value=1,
                max_value=len(st.session_state.qualified_df),
                value=min(5, len(st.session_state.qualified_df)),
                help="Number of qualified influencers to generate copy for.",
            )
            email_subject_template = st.text_input(
                "Email Subject Line Template",
                value="Collaboration Opportunity: {name} x AI Startup",
                help="Supports {name} placeholder.",
            )
            llm_copy_model = st.selectbox(
                "Copy Synthesis Model",
                groq_models_list,
                index=0,
                key="copy_model",
            )

        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            run_batch_btn = st.button(
                "🚀 Generate & Send Batch Now",
                type="primary",
                use_container_width=True,
                help="Generates pitches and sends emails for the entire batch according to selected mode.",
            )
        with col_btn2:
            run_preview_only_btn = st.button(
                "📝 Generate Copy Only (Preview Without Sending)",
                use_container_width=True,
                help="Only generates the email pitches and DMs so you can inspect/edit before sending.",
            )

        # Trigger batch generation & optional sending
        if run_batch_btn or run_preview_only_btn:
            selected_mode = "dry_run" if run_preview_only_btn else outreach_mode

            if not groq_api_key.strip():
                st.error("❌ Groq API Key is missing. Enter it in the sidebar.")
            elif selected_mode in ("test", "live") and (not smtp_email.strip() or not smtp_password.strip()):
                st.error("❌ SMTP Sender Email or Gmail App Password is missing in the sidebar.")
            elif selected_mode == "test" and not test_receiver_email.strip():
                st.error("❌ Test Mode Receiver Email is missing in the sidebar.")
            else:
                o_bar = st.progress(0.0)
                o_text = st.empty()

                def update_outreach_prog(c, t, m):
                    o_bar.progress(min(c / max(t, 1), 1.0))
                    o_text.text(m)

                action_desc = "Generating copy..." if selected_mode == "dry_run" else f"Generating & sending via SMTP ({selected_mode} mode)..."
                with st.spinner(action_desc):
                    try:
                        tracker_result = process_and_send(
                            df=st.session_state.qualified_df.copy(),
                            brand_context=brand_context,
                            subject_template=email_subject_template,
                            model=llm_copy_model,
                            limit=int(outreach_batch_limit),
                            mode=selected_mode,
                            test_receiver_email=test_receiver_email.strip(),
                            groq_api_key=groq_api_key.strip(),
                            smtp_email=smtp_email.strip(),
                            smtp_password=smtp_password.strip(),
                            delay_seconds=1.0,
                            progress_callback=update_outreach_prog,
                        )
                        st.session_state.tracker_df = tracker_result
                        o_bar.progress(1.0)
                        if selected_mode == "dry_run":
                            o_text.success("✅ Copy generated! You can now review and send individual emails below.")
                        else:
                            o_text.success(f"🎉 Batch dispatched! Mode: {selected_mode.upper()}")
                    except Exception as e:
                        st.error(f"Outreach Error: {e}")

        # -----------------------------------------------------
        # INDIVIDUAL EMAIL INSPECTION & 1-CLICK SEND OPTION
        # -----------------------------------------------------
        if not st.session_state.tracker_df.empty:
            st.divider()
            st.subheader("📬 Review & Send Emails to Creators")
            st.markdown(
                "You can review each synthesized pitch, edit the recipient or subject, and click **'Send Email Now'** to deliver it directly!"
            )

            # Global batch send button for all previewed emails
            send_all_col1, send_all_col2 = st.columns([2, 1])
            with send_all_col1:
                st.caption(f"Currently viewing {len(st.session_state.tracker_df)} generated pitches.")
            with send_all_col2:
                if st.button("📨 Send All Pending Emails via SMTP", use_container_width=True):
                    if not smtp_email.strip() or not smtp_password.strip():
                        st.error("❌ SMTP credentials missing in sidebar.")
                    else:
                        send_progress = st.progress(0.0)
                        for s_idx, s_row in st.session_state.tracker_df.iterrows():
                            # Determine destination email
                            dest_email = s_row["Original Extracted Email"]
                            is_test = (outreach_mode == "test") or (dest_email == "Not Found")
                            final_to = test_receiver_email.strip() if is_test else dest_email

                            res_status = send_email_smtp(
                                influencer_name=s_row["Influencer"],
                                subject=s_row["Subject"],
                                body=s_row["Email Pitch"],
                                recipient_email=final_to,
                                test_mode=is_test,
                                sender_email=smtp_email.strip(),
                                sender_password=smtp_password.strip(),
                            )
                            st.session_state.tracker_df.at[s_idx, "Sent Status"] = res_status
                            st.session_state.tracker_df.at[s_idx, "Delivery Address"] = final_to
                            send_progress.progress((s_idx + 1) / len(st.session_state.tracker_df))
                            time.sleep(0.5)

                        st.session_state.tracker_df.to_csv("outreach_tracker.csv", index=False)
                        st.success("✅ All emails have been processed via SMTP!")
                        st.rerun()

            for idx, r in st.session_state.tracker_df.iterrows():
                card_title = f"👤 {r['Influencer']} — Status: {r['Sent Status']}"
                with st.expander(card_title, expanded=(idx < 2)):
                    col_lead, col_dm = st.columns([2, 1])

                    with col_lead:
                        default_to = (
                            r["Original Extracted Email"]
                            if r["Original Extracted Email"] != "Not Found"
                            else test_receiver_email.strip()
                        )
                        target_to = st.text_input(
                            f"Send Email To:",
                            value=default_to,
                            key=f"to_{idx}",
                            help="Edit the destination email address.",
                        )
                        edit_subject = st.text_input(
                            f"Subject Line:",
                            value=r["Subject"],
                            key=f"subj_{idx}",
                        )
                        edit_pitch = st.text_area(
                            f"Personalized Email Pitch (Editable):",
                            value=r["Email Pitch"],
                            height=130,
                            key=f"pitch_{idx}",
                        )

                        # Individual Send Mail Button
                        send_single_btn = st.button(
                            f"📨 Send Email to {r['Influencer']}",
                            key=f"btn_send_{idx}",
                            type="primary",
                        )

                        if send_single_btn:
                            if not smtp_email.strip() or not smtp_password.strip():
                                st.error("❌ Please provide Sender Email & App Password in the sidebar.")
                            elif not target_to.strip() or target_to == "Not Found":
                                st.error("❌ Recipient email address is missing.")
                            else:
                                with st.spinner(f"Sending email to {target_to}..."):
                                    is_test_send = (target_to == test_receiver_email.strip())
                                    send_result = send_email_smtp(
                                        influencer_name=r["Influencer"],
                                        subject=edit_subject,
                                        body=edit_pitch,
                                        recipient_email=target_to.strip(),
                                        test_mode=is_test_send,
                                        sender_email=smtp_email.strip(),
                                        sender_password=smtp_password.strip(),
                                    )
                                    if "Sent via SMTP" in send_result:
                                        st.success(f"✅ Email successfully delivered to `{target_to}`!")
                                        st.session_state.tracker_df.at[idx, "Sent Status"] = send_result
                                        st.session_state.tracker_df.at[idx, "Delivery Address"] = target_to.strip()
                                        st.session_state.tracker_df.at[idx, "Subject"] = edit_subject
                                        st.session_state.tracker_df.at[idx, "Email Pitch"] = edit_pitch
                                        st.session_state.tracker_df.to_csv("outreach_tracker.csv", index=False)
                                    else:
                                        st.error(f"❌ Failed: {send_result}")

                    with col_dm:
                        st.markdown("**Companion Instagram DM:**")
                        st.text_area(
                            "Instagram DM (15-30 words)",
                            value=r["Instagram DM"],
                            height=100,
                            key=f"dm_{idx}",
                            disabled=True,
                        )
                        st.caption(f"📅 Logged: {r.get('Date', 'Today')}")
                        st.caption(f"📍 Original Extracted Email: `{r['Original Extracted Email']}`")

# ---------------------------------------------------------
# TAB 4: Campaign Tracker & Audit Logs
# ---------------------------------------------------------
with tab4:
    st.subheader("Campaign History & Outbound Logs")
    st.markdown("All generated copy, extraction results, and SMTP dispatch records are audited here.")

    if st.session_state.tracker_df.empty:
        st.info("No outreach tracker records yet. Run Phase 3 to generate records.")
    else:
        tr_df = st.session_state.tracker_df
        t1, t2, t3 = st.columns(3)
        t1.metric("Total Messages Synthesized", len(tr_df))
        successful_sends = len(tr_df[tr_df["Sent Status"].str.contains("Sent via SMTP", na=False)])
        t2.metric("Sent via SMTP", successful_sends)
        dry_runs = len(tr_df[tr_df["Sent Status"].str.contains("Dry Run|Generated Only", na=False)])
        t3.metric("Dry Run / Previewed", dry_runs)

        st.dataframe(tr_df, use_container_width=True)

        st.download_button(
            "📥 Download outreach_tracker.csv",
            data=tr_df.to_csv(index=False).encode("utf-8"),
            file_name="outreach_tracker.csv",
            mime="text/csv",
        )
