-- Supabase schema for LicorScan catalog
-- Run this in the Supabase SQL Editor or apply it with the Supabase CLI.

create extension if not exists pg_trgm;

create table if not exists public.products (
  id text primary key,
  store text not null,
  store_name text,
  title text not null,
  price numeric,
  img text,
  url text,
  category text,
  pricing_context jsonb not null default '{}'::jsonb,
  history jsonb not null default '[]'::jsonb,
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists products_store_idx on public.products (store);
create index if not exists products_category_idx on public.products (category);
create index if not exists products_price_idx on public.products (price);
create index if not exists products_title_trgm_idx on public.products using gin (title gin_trgm_ops);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_products_updated_at on public.products;
create trigger trg_products_updated_at
before update on public.products
for each row
execute function public.set_updated_at();

alter table public.products enable row level security;

drop policy if exists "read products" on public.products;
create policy "read products"
on public.products
for select
using (true);

drop policy if exists "insert products" on public.products;
create policy "insert products"
on public.products
for insert
with check (true);

drop policy if exists "update products" on public.products;
create policy "update products"
on public.products
for update
using (true)
with check (true);
