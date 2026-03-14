# 📰 NewsFlow

AI-powered personal news aggregator — runs on your home server, learns your preferences, and delivers a daily email digest written by your local Ollama model.

## Features

- **60+ Topics** across Technology, Science, Finance, Sports, Entertainment, Health, Lifestyle & more
- **Three article sources**: RSS feeds, NewsAPI.org (optional), and web scraping
- **AI Summaries**: Automatic per-article summaries via your Ollama model
- **Smart Recommendations**: Hybrid keyword scoring + Ollama AI re-ranking based on your likes
- **Like / Dislike / Hide**: Train the engine to your taste over time
- **Daily Email Digest**: AI-written HTML briefing sent on a configurable schedule
- **Multi-user**: Each user has their own feed, subscriptions, and preferences
- **Fully responsive**: Works beautifully on mobile and desktop
- **Docker**: One command deploy, runs on any Linux server
- **Easy backup**: All data lives in `./data/` — just copy the folder

---

## Quick Start

```bash
# 1. Extract the archive
tar -xzf newsflow.tar.gz
cd newsflow

# 2. Run the installer — it handles everything
bash install.sh
```

That's it. The installer will:
- ✅ Check for Docker & Docker Compose (and offer to install if missing)
- ✅ Create the `./data/` folder (where your database lives)
- ✅ Generate a cryptographically random `SECRET_KEY` in `.env`
- ✅ Ask you which port to run on (default: 3000)
- ✅ Build and start the containers
- ✅ Print your access URL and next steps

---

## First-Time Setup (after install)

1. Open `http://localhost:3000` (or your server's IP)
2. Register an account — **first user becomes admin**
3. Go to **Settings** → set your Ollama server URL (e.g. `http://192.168.1.100:11434`) → click **Test** → pick your model
4. Go to **Topics** → subscribe to what interests you
5. Click **Refresh** in the feed to fetch your first articles

---

## Backing Up Your Data

All data (SQLite database, settings, articles, likes) is stored in `./data/`:

```bash
# Simple backup
cp -r ~/newsflow/data ~/newsflow-backup-$(date +%Y%m%d)

# Or compress it
tar -czf newsflow-backup-$(date +%Y%m%d).tar.gz ~/newsflow/data
```

To restore, just copy the `data/` folder back and restart the containers.

---

## Useful Commands

```bash
# Live logs
docker compose logs -f

# Restart
docker compose restart

# Stop
docker compose down

# Update after file changes
docker compose up -d --build
```

---

## Architecture

```
┌─────────────┐     HTTP     ┌──────────────────────────────────┐
│   Browser   │ ──────────── │  Nginx (your configured port)    │
│  Mobile /   │              │  ├─ /api/* → FastAPI backend     │
│  Desktop    │              │  └─ /*    → React SPA            │
└─────────────┘              └──────────────────────────────────┘
                                       │
                               ./data/newsflow.db  ← your backup folder
                                       │
                              ┌────────┴──────────┐
                              │  APScheduler      │
                              │  ├─ RSS fetcher   │
                              │  ├─ NewsAPI       │
                              │  ├─ AI summarize  │
                              │  └─ Email digest  │
                              └────────┬──────────┘
                                       │
                              ┌────────┴──────────┐
                              │  Ollama Server    │
                              │  (your machine)   │
                              └───────────────────┘
```

---

## Troubleshooting

**No articles loading?**
- Subscribe to at least one topic, then click Refresh in the feed
- Check logs: `docker compose logs -f backend`

**Ollama not connecting?**
- Confirm Ollama is running: `ollama serve`
- Ensure port 11434 is reachable from the NewsFlow server: `curl http://OLLAMA_IP:11434/api/tags`
- Firewall on Ollama machine: `sudo ufw allow 11434`

**Email digest not sending?**
- Gmail: use an [App Password](https://support.google.com/accounts/answer/185833) (not your regular password)
- Host: `smtp.gmail.com`, Port: `587`
- Test with the **Send Now** button in the Digest page

**Server running slowly?**
- Reduce `max_articles_per_topic` in Settings
- Disable auto-summarize; use on-demand AI summaries instead
- Set refresh interval to 360+ minutes
