-- ============================================================
-- Migration: Add enrichment tracking fields to leads table
-- Run in Supabase SQL editor after the initial schema.sql
-- ============================================================

-- Enrichment metadata
alter table leads
  add column if not exists x_url               text,
  add column if not exists article_urls        text[],
  add column if not exists enrichment_sources  jsonb default '{}',
  add column if not exists enrichment_confidence integer default 0;

-- confirmed_by tracks multiple sources per investor record
alter table lead_investors
  add column if not exists confirmed_by text[] default '{}';

-- Update leads_summary view to include enrichment data
create or replace view leads_summary as
select
  l.id,
  l.company_name,
  l.filing_date,
  l.state,
  l.city,
  l.amount_raised,
  l.amount_offered,
  coalesce(l.amount_raised, l.amount_offered) as best_amount,
  l.round_name,
  l.industry,
  l.num_investors,
  l.edgar_url,
  l.website,
  l.linkedin_url,
  l.x_url,
  l.enrichment_sources,
  l.enrichment_confidence,
  l.article_urls,
  -- latest outreach status
  o.status          as outreach_status,
  o.outreach_type,
  o.contact_name,
  o.last_contact_at,
  o.next_followup_at,
  -- lead investor name
  li.investor_name  as lead_investor,
  -- all investor names as array
  inv_all.investor_names,
  l.created_at,
  l.updated_at
from leads l
left join lateral (
  select * from outreach
  where lead_id = l.id
  order by updated_at desc
  limit 1
) o on true
left join lateral (
  select investor_name from lead_investors
  where lead_id = l.id and is_lead = true
  limit 1
) li on true
left join lateral (
  select array_agg(investor_name order by is_lead desc) as investor_names
  from lead_investors
  where lead_id = l.id
) inv_all on true;
