-- LicorScan · Fase 3 · Esquema de la plataforma de datos de precios
--
-- Se crea AL LADO de la tabla `products` actual, sin tocarla: el frontend
-- en produccion todavia lee de ella. La convivencia termina cuando el
-- frontend migre a la API (Fase 6).
--
-- Nota de nombres: la tabla canonica nueva se llama `catalog_products`
-- justamente para no chocar con la `products` heredada.

create extension if not exists pg_trgm;

-- ---------------------------------------------------------------------
-- Tiendas
-- ---------------------------------------------------------------------
create table if not exists public.stores (
  id            serial primary key,
  -- Un pais no tiene atributos propios que se necesiten hoy; cuando los
  -- tenga (moneda, impuestos) se promueve a tabla sin romper nada.
  country_code  char(2) not null default 'CO',
  slug          text unique not null,
  name          text not null,
  website       text,
  platform      text not null default 'vtex',
  -- base_url, category_ids, sales_channel, delay_seconds
  config        jsonb not null default '{}'::jsonb,
  active        boolean not null default true,
  created_at    timestamptz not null default now()
);

create table if not exists public.store_locations (
  id          serial primary key,
  store_id    int not null references public.stores(id) on delete cascade,
  name        text not null,
  city        text,
  department  text,
  address     text,
  latitude    numeric,
  longitude   numeric,
  created_at  timestamptz not null default now()
);
create index if not exists store_locations_store_idx on public.store_locations (store_id);

-- ---------------------------------------------------------------------
-- Marcas y categorias
-- ---------------------------------------------------------------------
create table if not exists public.brands (
  id    serial primary key,
  slug  text unique not null,
  name  text not null
);

create table if not exists public.categories (
  id         serial primary key,
  parent_id  int references public.categories(id) on delete set null,
  slug       text unique not null,
  name       text not null
);
create index if not exists categories_parent_idx on public.categories (parent_id);

-- ---------------------------------------------------------------------
-- Producto canonico
-- ---------------------------------------------------------------------
create table if not exists public.catalog_products (
  id              bigserial primary key,
  -- EAN. Nullable a proposito: no toda tienda lo entrega.
  barcode         text unique,
  brand_id        int references public.brands(id) on delete set null,
  category_id     int references public.categories(id) on delete set null,
  name            text not null,
  normalized_name text not null,
  quantity        numeric,
  unit            text,
  image_url       text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create index if not exists catalog_products_brand_idx on public.catalog_products (brand_id);
create index if not exists catalog_products_category_idx on public.catalog_products (category_id);
create index if not exists catalog_products_name_trgm_idx
  on public.catalog_products using gin (normalized_name gin_trgm_ops);

-- ---------------------------------------------------------------------
-- Corridas de scraping (observabilidad)
-- ---------------------------------------------------------------------
create table if not exists public.scrape_runs (
  id             bigserial primary key,
  store_id       int not null references public.stores(id) on delete cascade,
  adapter        text not null default 'vtex',
  started_at     timestamptz not null default now(),
  finished_at    timestamptz,
  status         text not null default 'running'
                 check (status in ('running', 'completed', 'failed')),
  products_found int not null default 0,
  products_new   int not null default 0,
  prices_written int not null default 0,
  errors         int not null default 0,
  notes          text
);
create index if not exists scrape_runs_store_started_idx
  on public.scrape_runs (store_id, started_at desc);

-- ---------------------------------------------------------------------
-- Ficha del producto en cada tienda
-- ---------------------------------------------------------------------
create table if not exists public.store_products (
  id                  bigserial primary key,
  store_id            int not null references public.stores(id) on delete cascade,
  -- NULL hasta que la cascada de identidad lo resuelva. Nunca se fuerza.
  product_id          bigint references public.catalog_products(id) on delete set null,
  sku                 text not null,
  store_product_id    text,
  title               text not null,
  normalized_title    text not null default '',
  url                 text not null,
  image_url           text,
  store_category_path text,
  barcode             text,
  match_method        text check (match_method in ('barcode','shared_product_id','attributes','similarity','manual')),
  match_confidence    numeric check (match_confidence >= 0 and match_confidence <= 1),
  needs_review        boolean not null default false,
  raw                 jsonb,
  first_seen_at       timestamptz not null default now(),
  last_seen_at        timestamptz not null default now(),
  unique (store_id, sku)
);
create index if not exists store_products_product_idx on public.store_products (product_id);
create index if not exists store_products_store_idx on public.store_products (store_id);
create index if not exists store_products_barcode_idx on public.store_products (barcode);
create index if not exists store_products_review_idx
  on public.store_products (needs_review) where needs_review;

-- ---------------------------------------------------------------------
-- Precios · APPEND-ONLY
-- Nunca se hace UPDATE aqui. Cada observacion es una fila nueva; de ahi
-- salen historial, minimo, maximo, promedio y variacion sin trabajo extra.
-- ---------------------------------------------------------------------
create table if not exists public.prices (
  id               bigserial primary key,
  store_product_id bigint not null references public.store_products(id) on delete cascade,
  location_id      int references public.store_locations(id) on delete set null,
  price            numeric not null check (price >= 0),
  list_price       numeric check (list_price >= 0),
  currency         char(3) not null default 'COP',
  available        boolean not null default true,
  teasers          jsonb,
  scrape_run_id    bigint references public.scrape_runs(id) on delete set null,
  captured_at      timestamptz not null default now()
);
-- El indice que hace rapido tanto el historial como el "precio actual".
create index if not exists prices_sp_captured_idx
  on public.prices (store_product_id, captured_at desc);
create index if not exists prices_captured_idx on public.prices (captured_at desc);

-- Precio vigente por ficha de tienda.
create or replace view public.current_prices as
select distinct on (store_product_id)
  store_product_id, price, list_price, currency, available, teasers, captured_at
from public.prices
order by store_product_id, captured_at desc;

-- ---------------------------------------------------------------------
-- RLS: lectura publica, escritura solo por el backend (rol postgres,
-- que no esta sujeto a RLS). Mismo criterio que aplicamos a `products`.
-- ---------------------------------------------------------------------
alter table public.stores            enable row level security;
alter table public.store_locations   enable row level security;
alter table public.brands            enable row level security;
alter table public.categories        enable row level security;
alter table public.catalog_products  enable row level security;
alter table public.store_products    enable row level security;
alter table public.prices            enable row level security;
alter table public.scrape_runs       enable row level security;

do $$
declare t text;
begin
  foreach t in array array[
    'stores','store_locations','brands','categories',
    'catalog_products','store_products','prices','scrape_runs'
  ] loop
    execute format('drop policy if exists "public read %1$s" on public.%1$I', t);
    execute format(
      'create policy "public read %1$s" on public.%1$I for select using (true)', t
    );
  end loop;
end $$;
