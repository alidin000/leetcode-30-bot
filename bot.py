import asyncio
import base64
import json
import logging
import os
import re
import random
import sqlite3
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
DB_PATH = os.environ.get("DB_PATH", "leetcode30.db")
PORT = int(os.environ.get("PORT", "10000"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
REMINDER_HOUR = int(os.environ.get("REMINDER_HOUR", "19"))
REMINDER_MINUTE = int(os.environ.get("REMINDER_MINUTE", "0"))
TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "Europe/Budapest"))
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_BACKUP_REPO = os.environ.get("GITHUB_BACKUP_REPO", "alidin000/leetcode-30-bot")
GITHUB_BACKUP_BRANCH = os.environ.get("GITHUB_BACKUP_BRANCH", "data-backup")
GITHUB_BACKUP_PATH = os.environ.get("GITHUB_BACKUP_PATH", "data/backup.json")

START_DATE = datetime.fromisoformat(os.environ.get("CHALLENGE_START_DATE", datetime.now(timezone.utc).date().isoformat())).date()

CHALLENGES = [
    ("Two Sum", "https://leetcode.com/problems/two-sum/"),
    ("Valid Parentheses", "https://leetcode.com/problems/valid-parentheses/"),
    ("Best Time to Buy and Sell Stock", "https://leetcode.com/problems/best-time-to-buy-and-sell-stock/"),
    ("Contains Duplicate", "https://leetcode.com/problems/contains-duplicate/"),
    ("Product of Array Except Self", "https://leetcode.com/problems/product-of-array-except-self/"),
    ("Maximum Subarray", "https://leetcode.com/problems/maximum-subarray/"),
    ("Climbing Stairs", "https://leetcode.com/problems/climbing-stairs/"),
    ("House Robber", "https://leetcode.com/problems/house-robber/"),
    ("Coin Change", "https://leetcode.com/problems/coin-change/"),
    ("Longest Increasing Subsequence", "https://leetcode.com/problems/longest-increasing-subsequence/"),
    ("Binary Search", "https://leetcode.com/problems/binary-search/"),
    ("Search in Rotated Sorted Array", "https://leetcode.com/problems/search-in-rotated-sorted-array/"),
    ("3Sum", "https://leetcode.com/problems/3sum/"),
    ("Longest Substring Without Repeating Characters", "https://leetcode.com/problems/longest-substring-without-repeating-characters/"),
    ("Minimum Window Substring", "https://leetcode.com/problems/minimum-window-substring/"),
    ("Merge Intervals", "https://leetcode.com/problems/merge-intervals/"),
    ("Insert Interval", "https://leetcode.com/problems/insert-interval/"),
    ("Number of Islands", "https://leetcode.com/problems/number-of-islands/"),
    ("Clone Graph", "https://leetcode.com/problems/clone-graph/"),
    ("Course Schedule", "https://leetcode.com/problems/course-schedule/"),
    ("Binary Tree Level Order Traversal", "https://leetcode.com/problems/binary-tree-level-order-traversal/"),
    ("Lowest Common Ancestor of a Binary Search Tree", "https://leetcode.com/problems/lowest-common-ancestor-of-a-binary-search-tree/"),
    ("Validate Binary Search Tree", "https://leetcode.com/problems/validate-binary-search-tree/"),
    ("Kth Smallest Element in a BST", "https://leetcode.com/problems/kth-smallest-element-in-a-bst/"),
    ("Subsets", "https://leetcode.com/problems/subsets/"),
    ("Permutations", "https://leetcode.com/problems/permutations/"),
    ("Combination Sum", "https://leetcode.com/problems/combination-sum/"),
    ("Word Break", "https://leetcode.com/problems/word-break/"),
    ("Maximum Product Subarray", "https://leetcode.com/problems/maximum-product-subarray/"),
    ("Trapping Rain Water", "https://leetcode.com/problems/trapping-rain-water/"),
]

LEETCODE_URL = re.compile(r"https?://(?:www\.)?leetcode\.com/(?:problems/[^/\s]+/)?submissions(?:/detail)?/[^\s)]+", re.I)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            first_name TEXT,
            PRIMARY KEY (chat_id, user_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            day INTEGER NOT NULL,
            url TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            UNIQUE(chat_id, user_id, day)
        )
    """)
    conn.commit()
    return conn


def github_request(method, path, payload=None):
    if not GITHUB_TOKEN:
        return None

    url = f"https://api.github.com/repos/{GITHUB_BACKUP_REPO}/contents/{quote(path, safe='/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "leetcode-30-bot",
    }
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"

    try:
        with urlopen(Request(url, data=data, headers=headers, method=method), timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        logging.error("GitHub API error %s for %s: %s", exc.code, path, body[:1000])
        return None
    except (URLError, TimeoutError, json.JSONDecodeError):
        logging.exception("GitHub backup request failed")
        return None


def backup_to_github():
    if not GITHUB_TOKEN:
        logging.warning("GITHUB_TOKEN is not configured; backup skipped.")
        return False

    conn = db()
    users = [
        {
            "chat_id": row[0],
            "user_id": row[1],
            "username": row[2],
            "first_name": row[3],
        }
        for row in conn.execute(
            "SELECT chat_id, user_id, username, first_name FROM users"
        ).fetchall()
    ]
    submissions = [
        {
            "chat_id": row[0],
            "user_id": row[1],
            "day": row[2],
            "url": row[3],
            "submitted_at": row[4],
        }
        for row in conn.execute(
            "SELECT chat_id, user_id, day, url, submitted_at FROM submissions"
        ).fetchall()
    ]
    conn.close()

    backup = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "users": users,
        "submissions": submissions,
    }
    content = base64.b64encode(
        (json.dumps(backup, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    ).decode("ascii")

    existing = github_request(
        "GET",
        f"{GITHUB_BACKUP_PATH}?ref={quote(GITHUB_BACKUP_BRANCH, safe='')}",
    )

    payload = {
        "message": "Update challenge data backup",
        "content": content,
        "branch": GITHUB_BACKUP_BRANCH,
    }
    if existing and existing.get("sha"):
        payload["sha"] = existing["sha"]

    result = github_request("PUT", GITHUB_BACKUP_PATH, payload)
    if result:
        logging.info("Challenge data backed up to GitHub.")
        return True

    logging.error("Challenge data backup failed.")
    return False


def restore_from_github():
    if not GITHUB_TOKEN:
        logging.warning("GITHUB_TOKEN is not configured; restore skipped.")
        return False

    conn = db()
    users_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    submissions_count = conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
    conn.close()

    if users_count or submissions_count:
        return False

    result = github_request(
        "GET",
        f"{GITHUB_BACKUP_PATH}?ref={quote(GITHUB_BACKUP_BRANCH, safe='')}",
    )
    if not result or not result.get("content"):
        return False

    try:
        backup = json.loads(base64.b64decode(result["content"]).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, KeyError):
        logging.exception("Invalid GitHub backup.")
        return False

    conn = db()
    conn.executemany(
        "INSERT OR REPLACE INTO users(chat_id,user_id,username,first_name) VALUES(?,?,?,?)",
        [
            (
                row["chat_id"],
                row["user_id"],
                row.get("username"),
                row.get("first_name"),
            )
            for row in backup.get("users", [])
        ],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO submissions(chat_id,user_id,day,url,submitted_at) VALUES(?,?,?,?,?)",
        [
            (
                row["chat_id"],
                row["user_id"],
                row["day"],
                row["url"],
                row["submitted_at"],
            )
            for row in backup.get("submissions", [])
        ],
    )
    conn.commit()
    conn.close()
    logging.info(
        "Restored %s users and %s submissions from GitHub.",
        len(backup.get("users", [])),
        len(backup.get("submissions", [])),
    )
    return True


def register_user(update):
    chat = update.effective_chat
    user = update.effective_user
    conn = db()
    conn.execute(
        "INSERT OR REPLACE INTO users(chat_id,user_id,username,first_name) VALUES(?,?,?,?)",
        (chat.id, user.id, user.username, user.first_name),
    )
    conn.commit()
    conn.close()


def challenge(day):
    shuffled = random.Random(START_DATE.toordinal()).sample(CHALLENGES, len(CHALLENGES))
    return shuffled[(day - 1) % len(shuffled)]


def current_day():
    today = datetime.now(TIMEZONE).date()
    return min(30, max(1, (today - START_DATE).days + 1))


def challenge_message(day):
    name, url = challenge(day)
    return f"🧠 Day {day}/30\n\n{name}\n{url}\n\nSend your LeetCode submission link here when you finish."


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    await update.message.reply_text(
        "🏆 Welcome to LeetCode 30!\n\n"
        "Use /today for today's problem.\n"
        "Send your LeetCode submission link after solving.\n"
        "Use /progress or /leaderboard to see the challenge."
    )


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    await update.message.reply_text(challenge_message(current_day()))


async def random_problem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    daily_name, _ = challenge(current_day())
    choices = [problem for problem in CHALLENGES if problem[0] != daily_name]
    name, url = random.choice(choices)
    await update.message.reply_text(
        f"🎲 Random LeetCode problem\n\n{name}\n{url}"
    )

async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    chat_id = update.effective_chat.id
    conn = db()
    rows = conn.execute(
        "SELECT user_id, first_name, username FROM users WHERE chat_id=? ORDER BY first_name",
        (chat_id,),
    ).fetchall()
    message = [f"🏆 Day {current_day()}/30", ""]
    for user_id, first_name, username in rows:
        solved = conn.execute(
            "SELECT COUNT(*) FROM submissions WHERE chat_id=? AND user_id=?",
            (chat_id, user_id),
        ).fetchone()[0]
        display = f"@{username}" if username else first_name
        message.append(f"{display}: {solved}/30")
    conn.close()
    await update.message.reply_text("\n".join(message))


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    chat_id = update.effective_chat.id
    conn = db()
    rows = conn.execute("""
        SELECT u.first_name, u.username, COUNT(s.id) AS solved
        FROM users u
        LEFT JOIN submissions s
          ON s.chat_id=u.chat_id AND s.user_id=u.user_id
        WHERE u.chat_id=?
        GROUP BY u.user_id
        ORDER BY solved DESC, u.first_name ASC
    """, (chat_id,)).fetchall()
    conn.close()

    message = [f"🏆 Leaderboard — Day {current_day()}/30", ""]
    for index, (first_name, username, solved) in enumerate(rows, 1):
        display = f"@{username}" if username else first_name
        message.append(f"{index}. {display} — {solved}/30")
    await update.message.reply_text("\n".join(message))


async def record_submission(update: Update, url: str):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    day = current_day()
    conn = db()
    existing = conn.execute(
        "SELECT 1 FROM submissions WHERE chat_id=? AND user_id=? AND day=?",
        (chat_id, user_id, day),
    ).fetchone()
    if existing:
        conn.close()
        await update.message.reply_text(f"⚠️ You already submitted Day {day}.")
        return
    conn.execute(
        "INSERT INTO submissions(chat_id,user_id,day,url,submitted_at) VALUES(?,?,?,?,?)",
        (chat_id, user_id, day, url, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    backup_ok = await asyncio.to_thread(backup_to_github)
    if backup_ok:
        await update.message.reply_text(f"✅ Day {day} recorded for {update.effective_user.first_name}!\n💾 Backup saved.")
    else:
        await update.message.reply_text(f"✅ Day {day} recorded for {update.effective_user.first_name}!\n⚠️ GitHub backup failed — the submission is saved locally, but it may be lost if Render restarts.")


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    ok = await asyncio.to_thread(backup_to_github)
    if ok:
        await update.message.reply_text("💾 Backup completed successfully.")
    else:
        await update.message.reply_text("❌ Backup failed. Check the Render logs and GitHub token permissions.")

async def submit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    if not context.args:
        await update.message.reply_text(
            "Send your LeetCode submission link like:\n"
            "/submit https://leetcode.com/submissions/detail/123456789/"
        )
        return
    match = LEETCODE_URL.search(context.args[0])
    if not match:
        await update.message.reply_text("❌ That doesn't look like a LeetCode submission link.")
        return
    await record_submission(update, match.group(0))


async def submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    match = LEETCODE_URL.search(update.message.text)
    if not match:
        return
    register_user(update)
    await record_submission(update, match.group(0))


async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    chats = [row[0] for row in conn.execute("SELECT DISTINCT chat_id FROM users")]
    conn.close()
    message = "⏰ Daily LeetCode challenge\n\n" + challenge_message(current_day())
    for chat_id in chats:
        try:
            await context.bot.send_message(chat_id=chat_id, text=message)
        except Exception:
            logging.exception("Failed to send reminder to %s", chat_id)


def main():
    logging.basicConfig(level=logging.INFO)
    db()
    restore_from_github()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("random", random_problem))
    app.add_handler(CommandHandler("submit", submit_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("progress", progress))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, submission))

    app.job_queue.run_daily(
        daily_reminder,
        time=time(hour=9, minute=0, tzinfo=TIMEZONE),
        name="morning_reminder",
    )
    app.job_queue.run_daily(
        daily_reminder,
        time=time(hour=14, minute=0, tzinfo=TIMEZONE),
        name="afternoon_reminder",
    )
    app.job_queue.run_daily(
        daily_reminder,
        time=time(hour=19, minute=0, tzinfo=TIMEZONE),
        name="evening_reminder",
    )

    if not RENDER_EXTERNAL_URL:
        raise RuntimeError("RENDER_EXTERNAL_URL must be set for webhook mode")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"https://{RENDER_EXTERNAL_URL.rstrip('/').removeprefix('https://').removeprefix('http://')}/{TOKEN}",
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
