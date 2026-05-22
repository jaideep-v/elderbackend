-- ── ElderWise AI — Supabase Schema (v2) ──────────────────────────
-- Run this in the Supabase SQL editor (Dashboard → SQL)
-- Includes: medicines, medicine_logs (safety memory), reminders,
--           wellness_logs, emergency_contacts

-- ── Medicines ─────────────────────────────────────────────────────
create table if not exists medicines (
  id                uuid primary key default gen_random_uuid(),
  user_id           text not null,
  name              text not null,
  dosage            text not null default '',
  frequency         text not null,        -- JSON array of HH:MM strings e.g. '["08:00","21:00"]'
  stock_count       int  not null default 30,
  daily_consumption int  not null default 1,
  refill_threshold  int  not null default 7,
  pharmacy_contact  text,
  is_active         boolean not null default true,
  created_at        timestamptz not null default now()
);

-- ── Medicine Logs (dose history — safety memory) ───────────────────
-- Records every time a medicine is taken or missed.
-- Used by the AI to detect double-dosing and answer "did I take my medicine?"
create table if not exists medicine_logs (
  id             uuid primary key default gen_random_uuid(),
  medicine_id    uuid not null references medicines(id) on delete cascade,
  user_id        text not null,
  status         text not null check (status in ('taken', 'missed', 'skipped')),
  scheduled_time timestamptz not null,   -- when it was supposed to be taken
  actual_time    timestamptz,            -- when it was actually taken (null if missed)
  notes          text,
  created_at     timestamptz not null default now()
);

-- ── Reminders ─────────────────────────────────────────────────────
create table if not exists reminders (
  id             uuid primary key default gen_random_uuid(),
  user_id        text not null,
  title          text not null,
  date           timestamptz not null,
  type           text not null default 'custom',  -- 'birthday' | 'anniversary' | 'appointment' | 'religious' | 'custom'
  is_recurring   boolean not null default false,
  recur_pattern  text,                             -- 'daily' | 'weekly' | 'monthly' | 'yearly'
  auto_greeting  boolean not null default false,
  contact_number text,
  created_at     timestamptz not null default now()
);

-- ── Wellness Logs ─────────────────────────────────────────────────
create table if not exists wellness_logs (
  id              uuid primary key default gen_random_uuid(),
  user_id         text not null,
  mood_score      int  not null check (mood_score between 1 and 5),
  sleep_quality   text not null default 'fair',   -- 'good' | 'fair' | 'poor'
  pain_level      int  not null default 0 check (pain_level between 0 and 10),
  appetite        text not null default 'fair',   -- 'good' | 'fair' | 'poor'
  notes           text,
  sentiment_score float,
  alert_triggered boolean not null default false,
  created_at      timestamptz not null default now()
);

-- ── Emergency Contacts ────────────────────────────────────────────
create table if not exists emergency_contacts (
  id                uuid primary key default gen_random_uuid(),
  user_id           text not null,
  name              text not null,
  phone             text not null,     -- E.164 format, e.g. +919876543210
  relationship      text not null,     -- 'son' | 'daughter' | 'spouse' | 'doctor' | 'pharmacy' | 'other'
  is_primary        boolean not null default false,
  whatsapp_enabled  boolean not null default true,
  created_at        timestamptz not null default now()
);

-- ── Row Level Security (enable once auth is added) ────────────────
-- alter table medicines          enable row level security;
-- alter table medicine_logs      enable row level security;
-- alter table reminders          enable row level security;
-- alter table wellness_logs      enable row level security;
-- alter table emergency_contacts enable row level security;

-- ── Indexes ───────────────────────────────────────────────────────
create index if not exists idx_medicines_user          on medicines(user_id);
create index if not exists idx_medicine_logs_user      on medicine_logs(user_id, actual_time desc);
create index if not exists idx_medicine_logs_med_user  on medicine_logs(medicine_id, user_id, actual_time desc);
create index if not exists idx_reminders_user_date     on reminders(user_id, date);
create index if not exists idx_wellness_user_created   on wellness_logs(user_id, created_at desc);
create index if not exists idx_contacts_user_primary   on emergency_contacts(user_id, is_primary desc);
