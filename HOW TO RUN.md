# Second Brain - How to Run

## Every Day (Normal Use)

### Step 1 — Start Ollama
Open the **Ollama app** from your Start Menu or system tray.
Wait a few seconds until it's running (you'll see the llama icon in the taskbar).

### Step 2 — Open Terminal
Open **Command Prompt** or **PowerShell** and navigate to your folder:
```
cd "C:\Users\krisb\NCL - claude"
```

### Step 3 — Launch the App
```
streamlit run brain/ui/app.py
```
Your browser will open automatically at `http://localhost:8501`.

### Step 4 — Use It
- **Ask tab** — Ask anything: *"What papers discuss cultural distance in M&A?"*
- **Help Me Write tab** — Get a literature synthesis: *"ESG spillover after M&A"*
- **Find Papers tab** — Search your Literature Review matrix instantly

### Step 5 — Close When Done
Press `Ctrl + C` in the terminal to stop the app.

---

## When You Add New Papers

Do this after dropping new PDFs into `G:\...\Bacaan\`:

```
python brain/ingest/pipeline.py
```

This scans for new files, indexes only the new ones (skips everything already done), and takes under 1 minute for a few papers.

You can also click **"Re-index Files"** in the sidebar of the web app — same thing.

---

## First Time / Full Re-index

If you want to index everything from scratch:
```
python brain/ingest/pipeline.py --force
```
This takes 15-30 minutes (runs through all 150+ files).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| App says "Ollama not running" | Open the Ollama app and wait 10 seconds |
| Browser doesn't open | Manually go to `http://localhost:8501` |
| No results found | Run `python brain/ingest/pipeline.py` first |
| App crashes on start | Make sure you're in the right folder (`cd "C:\Users\krisb\NCL - claude"`) |

---

## Quick Reference

| What | Command |
|---|---|
| Start app | `streamlit run brain/ui/app.py` |
| Add new papers | `python brain/ingest/pipeline.py` |
| Full reindex | `python brain/ingest/pipeline.py --force` |
| Stop app | `Ctrl + C` in terminal |
