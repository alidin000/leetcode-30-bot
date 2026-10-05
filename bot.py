import logging
import os
import re
import sqlite3
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
DB_PATH = os.environ.get("DB_PATH", "leetcode30.db")
PORT = int(os.environ.get("PORT", "10000"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
REMINDER_HOUR = int(os.environ.get("REMINDER_HOUR", "19"))
REMINDER_MINUTE = int(os.environ.get("REMINDER_MINUTE", "0"))
TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "Europe/Budapest"))
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

LEETCODE_URL = re.compile(r"https?://(?:www\.)?leetcode\.com/submissions/detail/[\w-]+/?", re.I)


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
    return CHALLENGES[(day - 1) % len(CHALLENGES)]


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


async def submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    match = LEETCODE_URL.search(update.message.text)
    if not match:
        return

    register_user(update)
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    day = current_day()
    url = match.group(0)

    conn = db()
    existing = conn.execute(
        "SELECT 1 FROM submissions WHERE chat_id=? AND user_id=? AND day=?",
        (chat_id, user_id, day),
    ).fetchone()

    if existing:
        await update.message.reply_text(f"⚠️ You already submitted Day {day}.")
    else:
        conn.execute(
            "INSERT INTO submissions(chat_id,user_id,day,url,submitted_at) VALUES(?,?,?,?,?)",
            (chat_id, user_id, day, url, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        await update.message.reply_text(
            f"✅ Day {day} recorded for {update.effective_user.first_name}!"
        )
    conn.close()


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
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("progress", progress))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, submission))

    app.job_queue.run_daily(
        daily_reminder,
        time=time(hour=REMINDER_HOUR, minute=REMINDER_MINUTE, tzinfo=TIMEZONE),
    )

    if not RENDER_EXTERNAL_URL:
        raise RuntimeError("RENDER_EXTERNAL_URL must be set for webhook mode")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"{RENDER_EXTERNAL_URL.rstrip('/')}/{TOKEN}",
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
