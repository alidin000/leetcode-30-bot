# LeetCode 30 Bot

A small Telegram bot for a 30-day LeetCode challenge.

## Features

- Daily challenge reminder
- Daily LeetCode problem
- Every unique LeetCode problem submitted counts during the 30-day competition
- Duplicate problems are rejected and score 0
- Difficulty scoring: Easy = 1, Medium = 2, Hard = 4
- Daily points leaderboard and end-of-day winner
- UTC-based challenge-day boundaries, matching LeetCode's Daily Challenge calendar
- Pre-submission queue for travel days
- Submission links recorded from the group
- Progress and leaderboard
- SQLite storage
- Ready for Render

## Local setup

1. Create a Telegram bot with BotFather and get the token.
2. Set `TELEGRAM_BOT_TOKEN`.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run:

```bash
python bot.py
```

## Commands

- `/start`
- `/today`
- `/progress`
- `/track` — show each participant's submitted and missed days for the last 7 challenge days (`/track 14` shows up to 14 days)
- `/presubmit <problem-link>` — save a solved problem for a future day without scoring it yet
- `/presubmits` — list your unused pre-submissions
- `/usepresubmit [number]` — activate one saved problem for today's participation; each saved item can be used once
- `/leaderboard`

Send a LeetCode submission URL in the challenge group after solving a problem.

## Render

Use a Background Worker with:

```
python bot.py
```

Environment variable:

```
TELEGRAM_BOT_TOKEN
```
