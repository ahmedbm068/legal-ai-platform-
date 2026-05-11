# n8n — Appointment Lifecycle

Self-hosted n8n (Community Edition) wired into the Legal-AI backend.
On every appointment create / update / cancel, the backend fires a webhook to
n8n, which sends client emails and creates / updates the lawyer's Google
Calendar event. n8n calls back into the backend at `/integrations/n8n/appointments/sync`
when the lawyer reschedules in Google Calendar.

## 1. Start n8n locally

```powershell
docker compose up -d n8n
```

n8n editor: http://localhost:5678 (first run prompts for an owner account).

## 2. Expose n8n via Cloudflare Tunnel (one time)

Local URLs are not reachable by Google's OAuth callback. Use a free
Cloudflare Tunnel for a stable HTTPS hostname.

```powershell
# Install cloudflared (winget) and authenticate
winget install --id Cloudflare.cloudflared
cloudflared tunnel login
cloudflared tunnel create legal-ai-n8n
cloudflared tunnel route dns legal-ai-n8n n8n.<your-domain>
```

Grab the tunnel token from the Cloudflare Zero Trust dashboard and put it
in `.env`:

```
CLOUDFLARE_TUNNEL_TOKEN=eyJh...
N8N_PUBLIC_HOST=n8n.<your-domain>
N8N_PUBLIC_PROTOCOL=https
N8N_PUBLIC_URL=https://n8n.<your-domain>/
```

Then:

```powershell
docker compose --profile tunnel up -d cloudflared
docker compose restart n8n
```

n8n is now reachable at `https://n8n.<your-domain>` — use this URL for
Google Calendar OAuth redirect URIs.

## 3. Backend `.env` keys

```
# Outbound: backend → n8n
N8N_WORKFLOW_WEBHOOK_URL=https://n8n.<your-domain>/webhook/appointments
N8N_WEBHOOK_SECRET=<long-random-string>
N8N_REQUEST_TIMEOUT_SECONDS=15

# Email branding inside n8n templates
PORTAL_EMAIL_FROM=arbimostaisser@gmail.com
CLIENT_PORTAL_FIRM_NAME=Arbi Mostaissier
```

The same `N8N_WEBHOOK_SECRET` must be set on the n8n container side (it
already is in `docker-compose.yml`) — it's checked on both directions of
traffic.

## 4. Import the workflow

1. Open n8n → **Workflows** → **Import from File**.
2. Pick `infra/n8n/appointment_lifecycle.workflow.json`.
3. The import will warn about missing credentials — that's expected.
4. Click each `Email: …` node → **Credentials** → **Create new** → SMTP:
   - Host: `smtp.gmail.com`, Port: `587`, SSL/TLS: STARTTLS
   - User: your firm Gmail address
   - Password: **a Gmail App Password** (NOT your account password —
     enable 2FA on the Google account, then create an App Password at
     https://myaccount.google.com/apppasswords)
5. Click the `Google Calendar: create event` node → **Credentials** →
   **Create new** → OAuth2:
   - Use Google Cloud Console to create OAuth credentials for
     `https://n8n.<your-domain>/rest/oauth2-credential/callback`.
   - Scope: `https://www.googleapis.com/auth/calendar`.
   - Sign in as the lawyer whose calendar should hold the events.
6. **Activate** the workflow (top-right toggle).
7. Copy the production webhook URL from the **Webhook: appointment.\*** node
   and paste it into `.env` as `N8N_WORKFLOW_WEBHOOK_URL`.

## 5. Smoke test

```powershell
# Create a test appointment via the existing API
curl -X POST https://your-backend/calendar/case/<case_id> `
     -H "Authorization: Bearer <lawyer JWT>" `
     -H "Content-Type: application/json" `
     -d '{"title":"Test n8n","scheduled_at":"2026-05-12T14:00:00+01:00","duration_minutes":30}'
```

Expected within ~5 seconds:

1. Client receives a confirmation email.
2. An event appears in the lawyer's Google Calendar.
3. n8n's **Executions** tab shows a green run.

To test the GCal → DB callback, edit the event time in Google Calendar.
Add an n8n trigger (Google Calendar → "On event updated") that POSTs to
`https://your-backend/integrations/n8n/appointments/sync` with the
`appointment_id` (from the event description we wrote) and the new
`scheduled_at`. The DB row updates within seconds.

## 6. Operational notes

- The backend dispatches webhooks on a daemon thread — if n8n is down,
  the API request succeeds and the dispatch is logged-and-dropped. No
  retry. (Acceptable for v1; revisit when reliability matters.)
- The `Wait until T-24h` node in the imported workflow is a placeholder
  (1 minute by default for demos). Set it to a real expression once
  satisfied with the flow, e.g. `{{ $json.body.appointment.scheduled_at }}`
  with mode `Resume: At Specified Time` minus 24h.
- All inbound n8n → backend traffic must carry header
  `X-N8N-SECRET: <N8N_WEBHOOK_SECRET>`. Mismatches return 401.

## 7. Next workflows to layer on (cheap follow-ups)

- WhatsApp confirmations via Twilio (swap the email node for Twilio).
- Stripe invoice on `appointment.completed`.
- Daily digest cron → email lawyers a summary of upcoming appointments.

Each new flow is one event from the backend + one workflow in n8n. No
more backend architecture work needed.
