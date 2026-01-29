# Chorus

Slack bot that turns founder conversations into LinkedIn/X post suggestions.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

## Environment Variables

```
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_SIGNING_SECRET=...
OPENAI_API_KEY=sk-...
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
FOUNDER_USER_ID=U12345678
```

## Usage

- `@Chorus start listening` — Start monitoring a channel
- `@Chorus stop listening` — Stop monitoring
- `@Chorus status` — Check status

When post-worthy ideas are detected, you'll get a DM with draft suggestions. React with 👍 to save, 🔁 to rewrite, or ❌ to ignore.

## API

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Status check |
| `POST /api/trigger` | Force pipeline run |
| `GET /api/channels` | List monitored channels |
| `GET /api/suggestions` | List suggestions |
