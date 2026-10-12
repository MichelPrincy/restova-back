-- À exécuter UNE FOIS dans le SQL Editor de Supabase, après `alembic upgrade head`.
--
-- Supabase expose automatiquement les tables du schéma `public` via son API REST (PostgREST),
-- accessible avec la clé « anon » publique. Notre backend accède à la base directement (rôle
-- `postgres`, qui contourne RLS) et applique lui-même l'isolation par enseigne.
-- Activer RLS SANS aucune politique = l'API REST Supabase ne peut rien lire ni écrire.
-- (Ne pas exécuter sur un PostgreSQL classique si le backend s'y connecte avec un rôle non-propriétaire.)

ALTER TABLE public.users           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.restaurants     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.revoked_tokens  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.categories      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.menu_items      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stock_items     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.access_links    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_items     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY;
