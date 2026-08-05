# Zero-cost stack: self-hosted sentiment model over LLM classification

We considered using a cheap LLM (via the Claude API) for News Sentiment classification, estimated at roughly $3–15/month. The user set a hard constraint: no recurring cost at all, and clarified that their existing claude.ai subscription cannot be used for scripted/unattended API calls — a subscription seat and the metered Claude API are separate products.

Decision: run an open-source multilingual sentiment model (e.g. an XLM-RoBERTa-based classifier) as local CPU inference inside the daily GitHub Actions job — no external API calls for the classification step. The rest of the stack follows the same constraint: GitHub Actions (free tier) for scheduling and compute, Supabase/Neon free-tier Postgres for storage, Streamlit Community Cloud (free) for the dashboard, no custom domain.

Trade-off accepted: the self-hosted model is weaker than an LLM at sarcasm, coded political language, and English/Bahasa Malaysia code-switching. Given the zero-cost constraint this is the right call; revisit if the budget constraint ever relaxes (e.g. Gemini's free API tier, or a cheap Claude API budget, become acceptable).
