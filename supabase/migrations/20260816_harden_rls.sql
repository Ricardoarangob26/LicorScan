-- Harden RLS: the public anon/publishable key should only be able to read.
-- Writes go through the backend using the direct Postgres connection
-- (which bypasses RLS as the postgres role), so public insert/update
-- policies are not needed and were an unnecessary write-access hole
-- in the original schema.

drop policy if exists "insert products" on public.products;
drop policy if exists "update products" on public.products;
