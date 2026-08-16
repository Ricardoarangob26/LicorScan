-- Adds the pre-discount list price so the frontend can show a promo
-- indicator (star) and strike through the original price when a
-- product is on sale. NULL means no promotion was detected at scrape
-- time.

alter table public.products
  add column if not exists list_price numeric;
