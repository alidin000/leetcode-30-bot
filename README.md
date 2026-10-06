# LeetCode 30 Bot

A small Telegram bot for a 30-day LeetCode challenge.

## Features

- Daily challenge reminder
- Daily LeetCode problem
- Every unique LeetCode problem submitted counts during the 30-day competition
- Duplicate problems are rejected and score 0
- Difficulty scoring: Easy = 1, Medium = 2, Hard = 4
- Daily points leaderboard and end-of-day winner
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
