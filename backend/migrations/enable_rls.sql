-- Enable RLS on all public tables to satisfy the Supabase database linter
-- (lint 0013_rls_disabled_in_public).
--
-- The catalog/analysis data is intentionally world-readable, so we add a
-- permissive SELECT policy. Writes happen only via the postgres/service_role
-- connection from the backend, which bypasses RLS, so scraping/seed are
-- unaffected.
--
-- ponytail: if a private/user-scoped table is added later, replace the
-- "USING (true)" policy with "USING (auth.uid() IS NOT NULL)" (or a
-- user-id column check) instead of a blanket allow.

DO $$
DECLARE
  t text;
BEGIN
  FOR t IN
    SELECT unnest(ARRAY[
      'alembic_version',
      'analysis_logs',
      'laptop_units',
      'pc_components',
      'raw_listings',
      'scrape_runs'
    ])
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY;', t);
    -- idempotent: drop first if a policy with this name already exists
    EXECUTE format('DROP POLICY IF EXISTS "public read" ON public.%I;', t);
    EXECUTE format(
      'CREATE POLICY "public read" ON public.%I FOR SELECT USING (true);',
      t
    );
  END LOOP;
END $$;
