# WhatsApp Restaurant Ordering Bot — Setup Guide

## Prerequisites
- Docker Desktop installed
- ngrok installed (`brew install ngrok` / download from ngrok.com)
- A Meta Developer account with a WhatsApp Business App

---

## Step 1 — Supabase (free tier)

1. Create account at **supabase.com**
2. Click **New project** — choose a name, password, region (pick EU West for UAE latency)
3. Once the project is ready go to:
   **Settings → Database → Connection string → URI** — choose **Transaction pooler** (port 6543)
   Copy the full URI — it looks like:
   ```
   postgresql://postgres.xxxx:YOUR_PASSWORD@aws-0-eu-west-2.pooler.supabase.com:6543/postgres
   ```
4. Go to **SQL Editor** (left sidebar) and paste the entire contents of `supabase_setup.sql`
5. Click **Run** — you should see "Success. No rows returned."
6. Verify in **Table Editor** that `restaurants`, `menu_items`, `orders`, `customers` tables exist

---

## Step 2 — Anthropic API key

1. Go to **console.anthropic.com** → API Keys → Create Key
2. **Important:** Set a spending limit — go to Billing → set $10/month cap to start
3. Save the key — you will need it in the next step

---

## Step 3 — Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```env
WHATSAPP_TOKEN=        # Your permanent Meta token (see Step 4)
WHATSAPP_VERIFY_TOKEN=myverifytoken2026
ANTHROPIC_API_KEY=     # From Step 2
DATABASE_URL=          # Supabase pooler URI from Step 1
REDIS_URL=redis://redis:6379
```

---

## Step 4 — Meta WhatsApp Cloud API

1. Go to **developers.facebook.com** → My Apps → Create App → Business
2. Add **WhatsApp** product to the app
3. Go to **WhatsApp → API Setup**
4. Note the **Phone number ID** shown on that page
5. Go to **WhatsApp → Configuration → Generate permanent token**
   (or use the temporary token for testing — it expires in 24h)
6. In Supabase SQL Editor, update the demo restaurant record:
   ```sql
   UPDATE restaurants
   SET phone_number_id = 'YOUR_PHONE_NUMBER_ID_FROM_META',
       whatsapp_num    = '+YOUR_WHATSAPP_NUMBER',
       kitchen_num     = '+YOUR_KITCHEN_WHATSAPP_NUMBER'
   WHERE name = 'Al Nahda Demo Kitchen';
   ```

---

## Step 5 — Run with Docker

```bash
docker-compose up --build
```

Wait for these log lines:
```
app-1    | Redis connected
app-1    | Database pool initialised
app-1    | Ready
app-1    | Uvicorn running on http://0.0.0.0:8000
```

Test the health endpoint:
```bash
curl http://localhost:8000/health
# → {"status":"healthy"}
```

---

## Step 6 — Expose with ngrok

In a new terminal:

```bash
ngrok http 8000
```

Copy the `https://xxxx.ngrok-free.app` URL.

---

## Step 7 — Connect webhook to Meta

1. Go to **Meta Developer App → WhatsApp → Configuration → Webhook**
2. Click **Edit**
3. Set:
   - **Callback URL:** `https://YOUR-NGROK-URL/webhook`
   - **Verify Token:** `myverifytoken2026`
4. Click **Verify and Save**
5. In the **Webhook Fields** section, subscribe to: **messages**

---

## Step 8 — Test

Meta provides a test number — add your personal WhatsApp as a test recipient:
1. **WhatsApp → API Setup → To** — add your number
2. Send a WhatsApp message to the Meta test number
3. Watch logs: `docker-compose logs app -f`
4. You should see the bot reply in WhatsApp within 1-2 seconds

Try messages like:
- "Hi, what do you have?"
- "I'll take 2 chicken biryanis and a mango lassi"
- "Confirm" (after the bot shows you the total)

---

## Step 9 — Manage via Swagger

Open **http://localhost:8000/docs** in your browser.

From here you can:
- `GET /admin/orders/{restaurant_id}` — see all orders
- `PATCH /admin/orders/{order_id}/status` — mark ready (triggers customer WhatsApp)
- `GET /admin/menu/{restaurant_id}` — view full menu
- `POST /admin/menu/{restaurant_id}` — add menu items
- `PATCH /admin/menu/item/{item_id}/toggle` — enable/disable items
- `POST /admin/broadcast/{restaurant_id}` — send promotion to all customers
- `GET /admin/stats/{restaurant_id}` — revenue and order counts

To find your `restaurant_id`, run in Supabase SQL Editor:
```sql
SELECT id, name FROM restaurants;
```

---

## Production deployment (when ready)

Replace ngrok with a real server:
- Deploy to any VPS (DigitalOcean, Hetzner, etc.) with Docker
- Set up a domain with HTTPS (Caddy or Nginx + Let's Encrypt)
- Replace the webhook URL in Meta with your production HTTPS URL

---

## Cost estimate per restaurant (monthly)

| Service       | Cost         |
|---------------|-------------|
| Supabase free | $0           |
| Claude Haiku  | ~$2–5/month  |
| VPS (shared)  | ~$5–10/month |
| WhatsApp API  | $0 (1000 free conversations/month, then ~$0.05/conv) |
| **Your margin** | **AED 500/month − ~$15 costs = ~AED 445 profit/restaurant** |
