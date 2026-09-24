-- db/eml_supabase_schema.sql  (run ONCE in EML Supabase SQL editor)
create table if not exists eml_emails (
  id uuid primary key default gen_random_uuid(),
  file_name text,
  subject text,
  date text,
  sender_name text,
  sender_email text,
  receiver_name text,
  receiver_email text,
  body_text text,
  has_signature boolean default false,
  created_at timestamptz default now()
);

create table if not exists eml_contacts (
  id uuid primary key default gen_random_uuid(),
  name text,
  email text,
  phone_primary text,
  phone_secondary text,
  company text,
  designation text,
  address text,
  city text,
  pincode text,
  website text,
  source_email_id uuid references eml_emails(id) on delete set null,
  source_file text,
  dedup_status text default 'NEW',
  pushed_to_crm boolean default false,
  created_at timestamptz default now()
);

create index if not exists idx_eml_contacts_email on eml_contacts (email);
create index if not exists idx_eml_contacts_phone on eml_contacts (phone_primary);
create index if not exists idx_eml_contacts_source on eml_contacts (source_email_id);

-- ─────────────────────────────────────────────────────────────────────────
-- RLS DECISION (ruling): Row Level Security remains DISABLED intentionally.
--
-- EML_SUPABASE_ANON_KEY is a SERVER-SIDE ONLY secret (Render env var) and is
-- never shipped to the browser, so anonymous browser clients cannot reach
-- these tables at all. Least-privilege is enforced by keeping the key out of
-- the frontend — not by RLS policies.
--
-- Do NOT enable RLS / add policies here: policies would block the backend's
-- anon-role inserts and break /api/eml/* entirely.
-- ─────────────────────────────────────────────────────────────────────────
