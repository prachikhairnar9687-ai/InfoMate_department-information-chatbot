-- Run this in Supabase SQL Editor. Storage bucket is created separately below.
create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  role text not null default 'faculty' check (role in ('super_admin','admin','coordinator','faculty')),
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  category text not null default 'General',
  content text not null default '',
  status text not null default 'published' check (status in ('draft','published','archived')),
  storage_path text,
  uploaded_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);

create table if not exists public.notices (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  body text not null,
  category text not null default 'General',
  published boolean not null default false,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;
alter table public.documents enable row level security;
alter table public.notices enable row level security;

-- Browser users have no direct access to tables. Flask server uses service-role key.
-- Never put SUPABASE_SERVICE_ROLE_KEY in frontend JavaScript.
revoke all on public.profiles from anon, authenticated;
revoke all on public.documents from anon, authenticated;
revoke all on public.notices from anon, authenticated;
grant all on public.profiles to service_role;
grant all on public.documents to service_role;
grant all on public.notices to service_role;
