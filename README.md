# Form D Lead Tracker

SEC EDGAR → Supabase → Next.js web app for tracking recently funded tech startups.

---

## Architecture

```
SEC EDGAR (free API)
      ↓
ingestor/ingest.py   ← run manually or on a schedule
      ↓
Supabase (PostgreSQL)
      ↓
frontend/ (Next.js)  ← deployed on Vercel or run locally
```

---

## Step 1: Supabase Setup

1. Create a free project at https://supabase.com
2. Go to **SQL Editor** and run `supabase/schema.sql`
3. Copy your project credentials from **Settings → API**:
   - Project URL
   - `anon` public key (for frontend)
   - `service_role` secret key (for ingestor — never expose in browser)

---

## Step 2: Run the Ingestor

```bash
cd ingestor
pip install -r requirements.txt

# Set credentials
export SUPABASE_URL=https://your-project-ref.supabase.co
export SUPABASE_SERVICE_KEY=your-service-role-key

# Run — last 9 months, CA/NY/TX, Series A/B range
python ingest.py --days 270 --states CA NY TX

# Or just get a CSV without Supabase (for testing)
python ingest.py --csv-only --days 90
```

The first run against 9 months of data will take ~20–40 minutes due to EDGAR
rate limits. Subsequent runs are faster since most filings will already exist
(upsert by accession_no skips unchanged records).

---

## Step 3: Run the Frontend

```bash
cd frontend
npm install

# Configure environment
cp .env.example .env.local
# Edit .env.local with your Supabase URL and anon key

npm run dev
# → http://localhost:3000
```

---

## Step 4: Deploy to Vercel (optional but recommended)

```bash
npm install -g vercel
cd frontend
vercel
```

Add your env vars in the Vercel dashboard under **Settings → Environment Variables**.

---

## Automating the Ingestor (optional)

### Cron via GitHub Actions

Create `.github/workflows/ingest.yml`:

```yaml
name: Ingest Form D Filings
on:
  schedule:
    - cron: '0 8 * * 1'   # every Monday at 8am UTC
  workflow_dispatch:

jobs:
  ingest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r ingestor/requirements.txt
      - run: python ingestor/ingest.py --days 14
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
```

Add your secrets in **GitHub → Settings → Secrets**.

---

## Roadmap

### Near-term
- [ ] TechCrunch cross-reference to fill in round name + lead investor
- [ ] SQLite cache in ingestor to skip already-fetched accession numbers
- [ ] Supabase Auth (email login) so only you can access the app

### Mid-term
- [ ] Salesforce CRM integration (push leads via Salesforce REST API)
- [ ] HubSpot integration (alternative CRM)
- [ ] LinkedIn enrichment (company page URL, description)
- [ ] Email/Slack alert when new filings match saved filters

### Longer-term
- [ ] Multi-user with team outreach coordination
- [ ] Chrome extension to log outreach from LinkedIn directly
- [ ] AI summary of company based on public data (TechCrunch, LinkedIn, website)

---

## Key Data Notes

**What Form D tells you:**
- Company legal name, city, state
- Amount raised and total offering size
- Named executives and directors (great for direct outreach)
- Date the round started
- Number of investors (total count, not names)

**What Form D does NOT tell you:**
- Round name — inferred from amount ($3–15M = Series A, $15–50M = Series B)
- Investor/VC names — must be enriched from TechCrunch or manual input
- Post-money valuation
- Product description

**Amount → Round mapping used:**
| Amount | Inferred Round |
|---|---|
| < $1M | Pre-Seed |
| $1M – $3M | Seed |
| $3M – $15M | Series A |
| $15M – $50M | Series B |
| > $50M | Series C+ |
