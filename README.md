# LeetCode 30 Bot

A small Telegram bot for a 30-day LeetCode challenge.

## Features

- Daily challenge reminder
- Daily LeetCode problem
- Every unique LeetCode problem submitted counts during the 30-day competition
- Duplicate problems are rejected and score 0
- Difficulty scoring: Easy = 1, Medium = 2, Hard = 4
- Daily points leaderboard and end-of-day winner
- Automated end-of-day penalty report: missing a day means €1 to each other registered participant
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

- `/start` — register in the challenge
- `/revolut <username>` — register or update your Revolut username for penalty reports
- `/today`
- `/progress`
- `/track` — show each participant's submitted and missed days for the last 7 challenge days (`/track 14` shows up to 14 days)
- `/presubmit <problem-link>` — save a solved problem for a future day without scoring it yet
- `/presubmit` — list your unused pre-submissions
- `/usepresubmit [number]` — activate the oldest queued item or choose one by number
- `/help` — show the in-bot command manual
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


## Penalty report

Each participant should run `/start` in the challenge group and register their own Revolut handle using `/revolut <username>`. The automated penalty report runs at 00:10 UTC after the LeetCode day closes and lists missed participants and the €1 transfers owed to each other registered participant. The report does not initiate payments. Participants without a registered Revolut handle are called out and excluded from transfer calculations until they register.


## Command manual

Run `/help` in the Telegram group for the in-bot manual.

| Command | Purpose |
|---|---|
| `/start` | Register yourself in the group |
| `/help` | Show all bot commands and rules |
| `/revolut <username>` | Register or update your Revolut handle |
| `/revolut` | Check your saved Revolut handle |
| `/today` | Show today's challenge problem |
| `/random` | Get a random practice problem |
| `/submit <link>` | Submit a solved LeetCode/NeetCode problem |
| `/presubmit <link>` | Queue a solved problem for a future day |
| `/presubmit` | List unused queued problems |
| `/usepresubmit` | Activate the oldest queued problem |
| `/progress` | Show progress |
| `/track [7–14]` | Show recent daily participation |
| `/leaderboard` | Show competition scores |
| `/backup` | Back up challenge data |
| `/testtag` | Preview reminder mentions |

Unique problems score Easy 1 point, Medium 2, Hard 4. Each problem scores once per participant. Challenge-day boundaries follow UTC. Penalty reports list the €1 transfers owed to every other registered participant; the bot never sends money.
