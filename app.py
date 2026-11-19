import os
import time
from datetime import datetime
import pandas as pd
import streamlit as st

from discovery import discover_micro_influencers
from process_data import process_dataset
from generate_and_send import process_and_send

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
        st.session_state.tracker_df = pd.read_csv("outreach_tracker.csv")
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
        help="Get from console.groq.com for ultra-fast Llama/Qwen inference.",
    )

    with st.expander("📧 SMTP Email Settings", expanded=False):
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

    st.divider()
    st.markdown(
        """
        **System Status:**
        - Discovery: 🟢 Ready
        - AI Vetting: 🟢 Ready
        - Dispatch: 🟢 Ready
        """
    )
    st.caption("v1.0.0 • Production Ready")

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
                ["llama-3.3-70b-versatile", "qwen/qwen3.8-27b", "llama3-8b-8192", "mixtral-8x7b-32768"],
                index=0,
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

                with st.spinner("Analyzing channel bios and themes with Groq LLM..."):
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
                        q_text.success(
                            f"✅ Vetting complete! {len(qualified)}/{len(enriched)} creators Qualified."
                        )
                    except Exception as e:
                        st.error(f"Enrichment Error: {e}")

        if not st.session_state.enriched_df.empty:
            st.divider()
            en_df = st.session_state.enriched_df
            qu_df = st.session_state.qualified_df

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Analyzed", len(en_df))
            c2.metric("Qualified Leads", len(qu_df), delta=f"{len(qu_df)/len(en_df)*100:.1f}%")
            emails_found = en_df[en_df["Contact Email"] != "Not Found"]
            c3.metric("Emails Extracted", len(emails_found))
            rejected_count = len(en_df) - len(qu_df)
            c4.metric("Rejected Channels", rejected_count)

            sub_tab1, sub_tab2 = st.tabs(["✅ Qualified Leads", "❌ Rejected Channels"])
            with sub_tab1:
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

    if st.session_state.qualified_df.empty:
        st.info("ℹ️ Please run **Phase 2: AI Qualification** first or upload `qualified_influencers.csv` below.")
        uploaded_qual = st.file_uploader("Upload qualified_influencers.csv", type=["csv"], key="upload_qual")
        if uploaded_qual:
            st.session_state.qualified_df = pd.read_csv(uploaded_qual)
            st.rerun()
    else:
        out_col1, out_col2 = st.columns([1, 1])
        with out_col1:
            outreach_mode = st.radio(
                "Execution Mode",
                options=["dry_run", "test", "live"],
                format_func=lambda x: {
                    "dry_run": "🛡️ Dry Run (Generate copy only, do NOT send emails)",
                    "test": f"🧪 Test Mode (Send emails safely to: {test_receiver_email or 'Test Inbox'})",
                    "live": "🚀 Live Mode (Send directly to extracted creator emails)",
                }[x],
                help="Dry run preview copy; test mode audits deliverability without emailing creators; live mode sends to real creators.",
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
                help="Process the first N qualified influencers (great for testing).",
            )
            email_subject_template = st.text_input(
                "Email Subject Line Template",
                value="Collaboration Opportunity: {name} x AI Startup",
                help="Supports {name} placeholder.",
            )
            llm_copy_model = st.selectbox(
                "Copy Synthesis Model",
                ["llama-3.3-70b-versatile", "qwen/qwen3.8-27b", "llama3-8b-8192"],
                index=0,
                key="copy_model",
            )

        run_outreach = st.button("✉️ Generate Pitches & Dispatch", type="primary", use_container_width=True)

        if run_outreach:
            if not groq_api_key.strip():
                st.error("❌ Groq API Key is missing.")
            elif outreach_mode in ("test", "live") and (not smtp_email.strip() or not smtp_password.strip()):
                st.error("❌ SMTP Sender Email or Password missing for email sending. Fill in sidebar.")
            elif outreach_mode == "test" and not test_receiver_email.strip():
                st.error("❌ Test Receiver Email is missing. Fill in sidebar.")
            else:
                o_bar = st.progress(0.0)
                o_text = st.empty()

                def update_outreach_prog(c, t, m):
                    o_bar.progress(min(c / max(t, 1), 1.0))
                    o_text.text(m)

                with st.spinner("Generating personalized pitches & dispatching..."):
                    try:
                        tracker_result = process_and_send(
                            df=st.session_state.qualified_df.copy(),
                            brand_context=brand_context,
                            subject_template=email_subject_template,
                            model=llm_copy_model,
                            limit=int(outreach_batch_limit),
                            mode=outreach_mode,
                            test_receiver_email=test_receiver_email.strip(),
                            groq_api_key=groq_api_key.strip(),
                            smtp_email=smtp_email.strip(),
                            smtp_password=smtp_password.strip(),
                            delay_seconds=1.0,
                            progress_callback=update_outreach_prog,
                        )
                        st.session_state.tracker_df = tracker_result
                        o_bar.progress(1.0)
                        o_text.success("🎉 Outreach batch executed successfully!")
                    except Exception as e:
                        st.error(f"Outreach Error: {e}")

        if not st.session_state.tracker_df.empty:
            st.divider()
            st.subheader("Generated Copy & Delivery Audit")
            t_df = st.session_state.tracker_df

            for idx, r in t_df.iterrows():
                with st.expander(f"👤 {r['Influencer']} — Status: {r['Sent Status']}"):
                    ecol1, ecol2 = st.columns([2, 1])
                    with ecol1:
                        st.markdown(f"**Subject:** `{r['Subject']}`")
                        st.markdown(f"**Target Address:** `{r['Delivery Address']}` (Extracted: `{r['Original Extracted Email']}`)")
                        st.markdown("**Personalized Email Pitch (60–90 words):**")
                        st.info(r['Email Pitch'])
                    with ecol2:
                        st.markdown("**Companion Instagram DM (15–30 words):**")
                        st.success(r['Instagram DM'])
                        st.caption(f"Logged at: {r['Date']}")

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
