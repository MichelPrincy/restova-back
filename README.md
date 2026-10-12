# Restova — backend (FastAPI + PostgreSQL)

Implémente le contrat des étapes 1 à 3 : authentification et profil, catégories, menu, stock,
commandes, liens d'accès / QR client, paiement et suivi. Les routes, les noms de champs, les
codes d'erreur et le format `{"error": {code, message, details?}}` suivent le README du contrat.

**Stack** : Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL (psycopg 3), JWT (PyJWT), Argon2.

## Démarrage rapide

```bash
cp .env.example .env            # puis éditer JWT_SECRET
docker compose up -d db         # PostgreSQL local
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head            # crée les tables
uvicorn app.main:app --reload   # http://localhost:8000/docs
pytest                          # tests (SQLite temporaire, pas besoin de Postgres)
```

Ou tout en Docker : `docker compose up --build` (les migrations sont lancées au démarrage).

## Arborescence

```
app/
  main.py            application, CORS, routers, /health
  config.py          variables d'environnement
  database.py        moteur SQLAlchemy (Postgres, Supabase pooler, SQLite pour les tests)
  models.py          tables
  schemas.py         validation des corps de requête
  serializers.py     objets JSON du contrat (camelCase)
  errors.py          format d'erreur unique + codes
  security.py        Argon2 + JWT
  ratelimit.py       limitation de débit (en mémoire)
  deps.py            authentification / rôle
  routers/           auth, restaurant, categories, menu_items, stock, orders,
                     access_links, public, payments (webhook + simulateur dev)
  services/          orders (prix recalculés, numérotation), payments (passerelle)
alembic/             migrations (0001 = schéma initial)
supabase/enable_rls.sql
tests/
```

## Décisions de conception

- **Isolation** : l'enseigne vient toujours du jeton (ou du lien d'accès), jamais du corps. Un id d'une
  autre enseigne répond `404`. Un jeton de lien n'ouvre aucune route admin.
- **Prix** : à la commande, nom, prix et extras sont relus en base ; les prix envoyés par le front sont
  ignorés. Le prix unitaire (extras inclus) est figé dans la ligne de commande. `tax = subtotal × TAX_RATE`.
- **Numéros de commande** : `#R-101, #R-102…` par enseigne, via un `UPDATE … RETURNING` atomique.
- **Stock** : `delta` appliqué atomiquement en SQL, plancher à 0 ; `lastUpdated` mis à jour par le serveur.
- **Table** : pour `sur_place`, la table du lien l'emporte sur celle du corps.
- **Carte client** : les plats masqués (`isAvailable=false`) ne sont pas renvoyés ; l'e-mail du compte,
  le stock et les liens ne sont jamais exposés.
- **Sécurité** : mots de passe Argon2, JWT avec liste de révocation (`/auth/logout`), même réponse pour
  e-mail inconnu / mot de passe faux, limitation de débit (connexion, inscription, routes publiques,
  anti-énumération de jetons → `429`), CORS restreint à `CORS_ORIGINS`, démarrage refusé en production
  sans `JWT_SECRET` solide.

### Choix à valider (le contrat laissait de la marge)

| Sujet | Choix actuel | Pour changer |
|---|---|---|
| Jetons de lien et de suivi | stockés **en clair** (l'admin doit pouvoir réafficher le QR, et `GET /orders` renvoie `trackingToken`) | stocker une empreinte + chiffrer la valeur affichable |
| `GET /orders` | plafonné à `ORDERS_LIST_MAX` (500) plus récentes ; `?limit=&offset=` possibles | variable d'environnement |
| Transitions de statut | seules les commandes `livree` / `annulee` sont figées (`409 INVALID_STATUS_TRANSITION`) | `services/orders.py › change_status` |
| Préparation sans paiement | autorisée ; `REQUIRE_PAYMENT_BEFORE_PREPARATION=true` impose `paid`/`cash` (`409 PAYMENT_REQUIRED`) | variable d'environnement |
| Nom de catégorie en double | `409 CATEGORY_ALREADY_EXISTS` (insensible à la casse) | `routers/categories.py` |
| `sur_place` sans table (lien sans table et corps sans table) | accepté, `tableNumber = null` | `services/orders.py` |
| Rate limiting | en mémoire (1 instance) | Redis si plusieurs instances |

## Paiement — ce qui est fourni et ce qui reste à brancher

Le front ne décide jamais du paiement : tout est dans `isPaid`, `paymentStatus`, `paymentInstructions`,
`paymentRedirectUrl`.

- `especes` → `paymentStatus: "cash"`.
- Mobile Money / carte → la commande est enregistrée **puis** `PaymentGateway.initiate()` est appelé
  (`services/payments.py`). Si le prestataire est en panne, la commande est conservée avec `paymentStatus: "failed"`.
- **Seul `MockGateway` (développement) est fourni.** Les API MVola, Orange Money, Airtel Money et du
  prestataire de cartes exigent des comptes marchands et des identifiants : il faut écrire un adaptateur
  par prestataire (classe avec `initiate(order, restaurant)`) puis l'activer via `PAYMENT_PROVIDER`.
- Confirmation : `POST /webhooks/payments` (corps `{"transactionId", "status": "paid"|"failed"}`, signé
  HMAC-SHA256 dans `X-Signature` avec `PAYMENT_WEBHOOK_SECRET`). Chaque opérateur ayant son propre format
  et sa propre signature, adaptez-la selon leur documentation. Désactivée tant que le secret est vide.
- En développement (`PAYMENT_PROVIDER=mock`), `/dev/payments/<txn>/checkout` simule la page du prestataire
  (réussite / échec), puis redirige vers `FRONTEND_URL/?t=<jeton>`. Ces routes n'existent pas en production.

## Migration vers Supabase

Le code n'utilise que du PostgreSQL standard (pas d'extension, pas de fonction propriétaire) : migrer,
c'est changer `DATABASE_URL` et déplacer les données.

1. Créer le projet Supabase, copier la chaîne de connexion (*Project Settings → Database*). Préférer le
   *session pooler* (IPv4) ou la connexion directe ; le *transaction pooler* (port 6543) est géré
   automatiquement (pas de requêtes préparées, `NullPool`).
2. Mettre `DATABASE_URL=postgresql://postgres.<ref>:<mot-de-passe>@aws-0-<region>.pooler.supabase.com:5432/postgres`.
3. `alembic upgrade head` (crée le schéma dans Supabase).
4. Copier les données si besoin :
   ```bash
   pg_dump --data-only --inserts --exclude-table=alembic_version "$LOCAL_URL" > data.sql
   psql "$SUPABASE_URL" -f data.sql
   ```
5. **Exécuter `supabase/enable_rls.sql`** : Supabase expose le schéma `public` via une API REST publique ;
   sans RLS, les tables seraient lisibles avec la clé `anon`. Le backend, lui, se connecte avec le rôle
   `postgres` et n'est pas concerné par RLS.
6. Ne jamais mettre la clé `service_role` dans le front.

L'authentification reste celle du backend (table `users`, JWT maison) : rien n'oblige à passer par
Supabase Auth, ce serait une migration distincte.

## Points d'attention avant la production

- `ENV=production`, `JWT_SECRET` aléatoire (≥ 32 caractères), `CORS_ORIGINS` = origine exacte du front.
- Lancer `uvicorn --proxy-headers` derrière un reverse proxy (HTTPS) pour que la limitation de débit
  voie l'IP réelle.
- Brancher de vrais adaptateurs de paiement avant d'accepter autre chose que `especes`.
- Sauvegardes de la base (Supabase les gère, en local : `pg_dump`).



base pass: XnyMichelPrincy.2709