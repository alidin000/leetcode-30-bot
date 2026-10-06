import asyncio
import html
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
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

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

POINTS_BY_DIFFICULTY = {
    "EASY": 1,
    "MEDIUM": 2,
    "HARD": 4,
}
LEETCODE_GRAPHQL_API = "https://leetcode.com/graphql"
QUESTION_METADATA_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    title
    difficulty
  }
}
"""

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

LEETCODE_URL = re.compile(
    r"https?://(?:www\.)?leetcode\.com/(?:"
    r"problems/[^/\s]+/submissions(?:/detail)?/[^\s)]+"
    r"|submissions(?:/detail)?/[^\s)]+"
    r")",
    re.I,
)


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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS competition_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            day INTEGER NOT NULL,
            problem_slug TEXT NOT NULL,
            problem_title TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            points INTEGER NOT NULL,
            url TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            UNIQUE(chat_id, user_id, problem_slug)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS problem_metadata (
            problem_slug TEXT PRIMARY KEY,
            problem_title TEXT NOT NULL,
            difficulty TEXT NOT NULL,
            points INTEGER NOT NULL
        )
    """)
    conn.commit()
    return conn


def github_request(method, path, payload=None, query=None):
    if not GITHUB_TOKEN:
        return None

    url = f"https://api.github.com/repos/{GITHUB_BACKUP_REPO}/contents/{quote(path, safe='/')}"
    if query:
        url += "?" + query
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
    current_users = [
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
    current_submissions = [
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
    current_competition_submissions = [
        {
            "chat_id": row[0],
            "user_id": row[1],
            "day": row[2],
            "problem_slug": row[3],
            "problem_title": row[4],
            "difficulty": row[5],
            "points": row[6],
            "url": row[7],
            "submitted_at": row[8],
        }
        for row in conn.execute(
            "SELECT chat_id, user_id, day, problem_slug, problem_title, difficulty, points, url, submitted_at "
            "FROM competition_submissions"
        ).fetchall()
    ]
    conn.close()

    existing = github_request(
        "GET",
        GITHUB_BACKUP_PATH,
        query=f"ref={quote(GITHUB_BACKUP_BRANCH, safe='')}",
    )
    if not existing or not existing.get("sha") or not existing.get("content"):
        # Never replace a potentially healthy remote backup with a possibly
        # empty/incomplete local SQLite database.
        logging.error("Remote GitHub backup could not be read; refusing to overwrite it.")
        return False

    try:
        remote_backup = json.loads(
            base64.b64decode(existing["content"]).decode("utf-8")
        )
    except (ValueError, UnicodeDecodeError, KeyError):
        logging.exception("Remote GitHub backup is invalid; refusing to overwrite it.")
        return False

    def merge_records(existing_rows, current_rows, key_fields):
        merged = {}
        for row in existing_rows or []:
            key = tuple(row.get(field) for field in key_fields)
            merged[key] = row
        for row in current_rows:
            key = tuple(row.get(field) for field in key_fields)
            merged[key] = row
        return list(merged.values())

    backup = {
        "version": max(2, int(remote_backup.get("version", 1) or 1)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "users": merge_records(
            remote_backup.get("users", []),
            current_users,
            ("chat_id", "user_id"),
        ),
        "submissions": merge_records(
            remote_backup.get("submissions", []),
            current_submissions,
            ("chat_id", "user_id", "day"),
        ),
        "competition_submissions": merge_records(
            remote_backup.get("competition_submissions", []),
            current_competition_submissions,
            ("chat_id", "user_id", "problem_slug"),
        ),
    }

    content = base64.b64encode(
        (json.dumps(backup, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    ).decode("ascii")

    payload = {
        "message": "Update challenge data backup",
        "content": content,
        "branch": GITHUB_BACKUP_BRANCH,
        "sha": existing["sha"],
    }

    result = github_request("PUT", GITHUB_BACKUP_PATH, payload)
    if result:
        logging.info(
            "Challenge data backed up to GitHub: %s users, %s legacy submissions, "
            "%s competition submissions.",
            len(backup["users"]),
            len(backup["submissions"]),
            len(backup["competition_submissions"]),
        )
        return True

    logging.error("Challenge data backup failed.")
    return False
def restore_from_github():
    if not GITHUB_TOKEN:
        logging.warning("GITHUB_TOKEN is not configured; restore skipped.")
        return False

    result = github_request(
        "GET",
        GITHUB_BACKUP_PATH,
        query=f"ref={quote(GITHUB_BACKUP_BRANCH, safe='')}",
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
    conn.executemany(
        """
        INSERT OR IGNORE INTO competition_submissions(
            chat_id,user_id,day,problem_slug,problem_title,difficulty,points,url,submitted_at
        ) VALUES(?,?,?,?,?,?,?,?,?)
        """,
        [
            (
                row["chat_id"],
                row["user_id"],
                row["day"],
                row["problem_slug"],
                row["problem_title"],
                row["difficulty"],
                row["points"],
                row["url"],
                row["submitted_at"],
            )
            for row in backup.get("competition_submissions", [])
            if row.get("problem_slug") and row.get("difficulty") and row.get("points") is not None
        ],
    )
    conn.commit()
    conn.close()
    logging.info(
        "Restored %s users, %s legacy submissions and %s competition submissions from GitHub.",
        len(backup.get("users", [])),
        len(backup.get("submissions", [])),
        len(backup.get("competition_submissions", [])),
    )
    return True


def restore_with_retries(attempts=3):
    for attempt in range(1, attempts + 1):
        if restore_from_github():
            logging.info("GitHub restore succeeded on attempt %s/%s.", attempt, attempts)
            return True
        logging.warning("GitHub restore attempt %s/%s failed.", attempt, attempts)
    logging.error("GitHub restore failed after %s attempts.", attempts)
    return False


async def ensure_restored():
    await asyncio.to_thread(restore_with_retries)


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
    return (
        f"🧠 Day {day}/30\n\n{name}\n{url}\n\n"
        "⚔️ Competition mode: every unique LeetCode problem you submit counts.\n"
        "Easy = 1 point · Medium = 2 points · Hard = 4 points.\n"
        "Duplicate problems do not score again."
    )


def extract_problem_slug(url):
    try:
        path_parts = [part for part in urlparse(url).path.split("/") if part]
    except ValueError:
        return None

    if "problems" not in path_parts:
        return None

    index = path_parts.index("problems")
    if index + 1 >= len(path_parts):
        return None

    slug = path_parts[index + 1].strip().lower()
    if not slug or "submissions" not in path_parts[index + 2:]:
        return None
    return slug


def lookup_problem_metadata(problem_slug):
    conn = db()
    cached = conn.execute(
        "SELECT problem_title, difficulty, points FROM problem_metadata WHERE problem_slug=?",
        (problem_slug,),
    ).fetchone()
    conn.close()

    if cached:
        return {
            "title": cached[0],
            "difficulty": cached[1],
            "points": cached[2],
        }

    payload = json.dumps({
        "query": QUESTION_METADATA_QUERY,
        "variables": {"titleSlug": problem_slug},
    }).encode("utf-8")
    request = Request(
        LEETCODE_GRAPHQL_API,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "leetcode-30-bot/2.0",
            "Referer": f"https://leetcode.com/problems/{problem_slug}/",
        },
    )

    try:
        with urlopen(request, timeout=15) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        logging.exception("Failed to fetch LeetCode metadata for %s", problem_slug)
        return None

    question = (body.get("data") or {}).get("question")
    if not question or question.get("difficulty") not in POINTS_BY_DIFFICULTY:
        logging.warning("No usable LeetCode metadata for %s: %s", problem_slug, body)
        return None

    difficulty = question["difficulty"]
    points = POINTS_BY_DIFFICULTY[difficulty]
    title = question["title"]

    conn = db()
    conn.execute(
        """
        INSERT OR REPLACE INTO problem_metadata(problem_slug,problem_title,difficulty,points)
        VALUES(?,?,?,?)
        """,
        (problem_slug, title, difficulty, points),
    )
    conn.commit()
    conn.close()

    return {"title": title, "difficulty": difficulty, "points": points}


def backfill_competition_submissions():
    conn = db()
    legacy_rows = conn.execute(
        "SELECT chat_id,user_id,day,url,submitted_at FROM submissions"
    ).fetchall()
    conn.close()

    created = 0
    skipped = 0
    for chat_id, user_id, day, url, submitted_at in legacy_rows:
        problem_slug = extract_problem_slug(url)
        if not problem_slug:
            skipped += 1
            continue

        metadata = lookup_problem_metadata(problem_slug)
        if not metadata:
            skipped += 1
            continue

        conn = db()
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO competition_submissions(
                chat_id,user_id,day,problem_slug,problem_title,difficulty,points,url,submitted_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                chat_id,
                user_id,
                day,
                problem_slug,
                metadata["title"],
                metadata["difficulty"],
                metadata["points"],
                url,
                submitted_at,
            ),
        )
        conn.commit()
        conn.close()
        if cur.rowcount:
            created += 1

    if skipped:
        logging.warning(
            "Competition backfill skipped %s legacy submissions without verifiable problem metadata.",
            skipped,
        )
    if created:
        logging.info("Backfilled %s legacy submissions into competition scoring.", created)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    await update.effective_message.reply_text(
        "🏆 Welcome to LeetCode 30!\n\n"
        "Use /today for today's problem.\n"
        "Send your LeetCode submission link after solving.\n"
        "Use /progress or /leaderboard to see the challenge."
    )


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    await update.effective_message.reply_text(challenge_message(current_day()))


async def random_problem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    daily_name, _ = challenge(current_day())
    choices = [problem for problem in CHALLENGES if problem[0] != daily_name]
    name, url = random.choice(choices)
    await update.effective_message.reply_text(
        f"🎲 Random LeetCode problem\n\n{name}\n{url}"
    )

async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_restored()
    register_user(update)
    chat_id = update.effective_chat.id
    day = current_day()
    conn = db()
    rows = conn.execute(
        "SELECT user_id, first_name, username FROM users WHERE chat_id=? ORDER BY first_name",
        (chat_id,),
    ).fetchall()
    message = [f"🏆 Day {day}/30", ""]
    for user_id, first_name, username in rows:
        today_count, today_points = conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(points), 0)
            FROM competition_submissions
            WHERE chat_id=? AND user_id=? AND day=?
            """,
            (chat_id, user_id, day),
        ).fetchone()
        total_count, total_points = conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(points), 0)
            FROM competition_submissions
            WHERE chat_id=? AND user_id=?
            """,
            (chat_id, user_id),
        ).fetchone()
        display = f"@{username}" if username else first_name
        message.append(
            f"{display}: today {today_count} questions / {today_points} pts · "
            f"total {total_count} / {total_points} pts"
        )
    conn.close()
    await update.effective_message.reply_text("\n".join(message))


def leaderboard_rows(chat_id, day=None):
    conn = db()
    if day is None:
        rows = conn.execute("""
            SELECT u.first_name, u.username,
                   COUNT(s.id) AS solved,
                   COALESCE(SUM(s.points), 0) AS points
            FROM users u
            LEFT JOIN competition_submissions s
              ON s.chat_id=u.chat_id AND s.user_id=u.user_id
            WHERE u.chat_id=?
            GROUP BY u.user_id
            ORDER BY points DESC, solved DESC, u.first_name ASC
        """, (chat_id,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT u.first_name, u.username,
                   COUNT(s.id) AS solved,
                   COALESCE(SUM(s.points), 0) AS points
            FROM users u
            LEFT JOIN competition_submissions s
              ON s.chat_id=u.chat_id AND s.user_id=u.user_id AND s.day=?
            WHERE u.chat_id=?
            GROUP BY u.user_id
            ORDER BY points DESC, solved DESC, u.first_name ASC
        """, (day, chat_id)).fetchall()
    conn.close()
    return rows


def leaderboard_section(title, rows):
    lines = [title]
    for index, (first_name, username, solved, points) in enumerate(rows, 1):
        display = f"@{username}" if username else first_name
        lines.append(
            f"{index}. {display} — {solved} question{'s' if solved != 1 else ''} · {points} pts"
        )
    if not rows:
        lines.append("No participants yet.")
    return lines


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_restored()
    register_user(update)
    chat_id = update.effective_chat.id
    day = current_day()

    daily_rows = leaderboard_rows(chat_id, day)
    overall_rows = leaderboard_rows(chat_id)

    message = [
        f"🏆 Leaderboard — Day {day}/30",
        "",
        *leaderboard_section("📅 TODAY", daily_rows),
        "",
        *leaderboard_section("🏆 OVERALL", overall_rows),
    ]

    if daily_rows:
        max_points = daily_rows[0][3]
        max_solved = daily_rows[0][2]
        winners = [
            (first_name, username)
            for first_name, username, solved, points in daily_rows
            if points == max_points and solved == max_solved
        ]
        if max_solved == 0:
            message.extend(["", "🤝 No winner today — nobody submitted a counted problem."])
        elif len(winners) == 1:
            first_name, username = winners[0]
            display = f"@{username}" if username else first_name
            message.extend(["", f"🥇 Today’s winner: {display} — {max_points} pts"])
        else:
            displays = [
                f"@{username}" if username else first_name
                for first_name, username in winners
            ]
            message.extend(["", f"🥇 Today’s joint winners: {', '.join(displays)} — {max_points} pts"])

    if overall_rows and overall_rows[0][2] > 0:
        first_name, username, solved, points = overall_rows[0]
        display = f"@{username}" if username else first_name
        message.extend(["", f"👑 Overall leader: {display} — {points} pts / {solved} unique questions"])

    await update.effective_message.reply_text("\n".join(message))


def save_competition_submission(
    chat_id,
    user_id,
    day,
    problem_slug,
    problem_title,
    difficulty,
    points,
    url,
    submitted_at,
):
    conn = db()
    existing = conn.execute(
        """
        SELECT day, problem_title, difficulty, points
        FROM competition_submissions
        WHERE chat_id=? AND user_id=? AND problem_slug=?
        """,
        (chat_id, user_id, problem_slug),
    ).fetchone()

    if existing:
        conn.close()
        return {"counted": False, "existing": existing}

    conn.execute(
        """
        INSERT INTO competition_submissions(
            chat_id,user_id,day,problem_slug,problem_title,difficulty,points,url,submitted_at
        ) VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (
            chat_id,
            user_id,
            day,
            problem_slug,
            problem_title,
            difficulty,
            points,
            url,
            submitted_at,
        ),
    )
    # Preserve the original table as a compatibility marker for "participated today".
    conn.execute(
        "INSERT OR IGNORE INTO submissions(chat_id,user_id,day,url,submitted_at) VALUES(?,?,?,?,?)",
        (chat_id, user_id, day, url, submitted_at),
    )
    conn.commit()
    conn.close()
    return {"counted": True, "existing": None}


async def finish_submission(update, problem_title, difficulty, points, pending):
    chat_id = pending["chat_id"]
    user_id = pending["user_id"]
    day = pending["day"]
    problem_slug = pending["problem_slug"]
    url = pending["url"]
    submitted_at = pending["submitted_at"]

    result = save_competition_submission(
        chat_id=chat_id,
        user_id=user_id,
        day=day,
        problem_slug=problem_slug,
        problem_title=problem_title,
        difficulty=difficulty,
        points=points,
        url=url,
        submitted_at=submitted_at,
    )

    if not result["counted"]:
        existing = result["existing"]
        text = (
            f"⚠️ Duplicate: {problem_title} was already counted on Day {existing[0]}. "
            f"It is worth {existing[3]} point(s), so this submission adds 0 points."
        )
    else:
        backup_ok = await asyncio.to_thread(backup_to_github)
        suffix = (
            "💾 Backup saved."
            if backup_ok
            else "⚠️ GitHub backup failed — the score is only local until backup succeeds."
        )
        text = (
            f"✅ {problem_title} counted!\n"
            f"🎚 {difficulty.title()} · +{points} point(s)\n"
            f"🏆 Every unique problem counts once during the challenge.\n"
            f"{suffix}"
        )

    message = update.effective_message
    if message:
        await message.reply_text(text)
    else:
        await update.callback_query.edit_message_text(text)


async def record_submission(update: Update, url: str, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    day = current_day()
    problem_slug = extract_problem_slug(url)

    if not problem_slug:
        await update.effective_message.reply_text(
            "❌ I need a problem-specific submission link so I can identify the problem.\n\n"
            "Use a link like:\n"
            "https://leetcode.com/problems/two-sum/submissions/123456789/\n\n"
            "Generic /submissions/detail/... links do not contain enough public information for "
            "duplicate detection and competition scoring."
        )
        return

    metadata = await asyncio.to_thread(lookup_problem_metadata, problem_slug)
    if not metadata:
        pending_map = context.user_data.setdefault("pending_difficulty_submissions", {})
        token = f"{datetime.now(timezone.utc).timestamp():.6f}".replace(".", "")[-12:]
        pending_map[token] = {
            "chat_id": chat_id,
            "user_id": user_id,
            "day": day,
            "problem_slug": problem_slug,
            "problem_title": problem_slug.replace("-", " ").title(),
            "url": url,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🟢 Easy · 1 pt", callback_data=f"diff:{token}:EASY"),
                InlineKeyboardButton("🟠 Medium · 2 pts", callback_data=f"diff:{token}:MEDIUM"),
            ],
            [
                InlineKeyboardButton("🔴 Hard · 4 pts", callback_data=f"diff:{token}:HARD"),
            ],
        ])
        await update.effective_message.reply_text(
            "⚠️ I couldn't retrieve this problem's difficulty automatically.\n\n"
            f"<b>{html.escape(pending_map[token]['problem_title'])}</b>\n"
            "Choose the LeetCode difficulty below. Your choice will be used for scoring.",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    submitted_at = datetime.now(timezone.utc).isoformat()
    result = save_competition_submission(
        chat_id=chat_id,
        user_id=user_id,
        day=day,
        problem_slug=problem_slug,
        problem_title=metadata["title"],
        difficulty=metadata["difficulty"],
        points=metadata["points"],
        url=url,
        submitted_at=submitted_at,
    )

    if not result["counted"]:
        existing = result["existing"]
        await update.effective_message.reply_text(
            f"⚠️ Duplicate: {metadata['title']} was already counted on Day {existing[0]}. "
            f"It is worth {existing[3]} point(s), so this submission adds 0 points."
        )
        return

    backup_ok = await asyncio.to_thread(backup_to_github)
    score = metadata["points"]
    suffix = (
        "💾 Backup saved."
        if backup_ok
        else "⚠️ GitHub backup failed — the score is only local until backup succeeds."
    )

    await update.effective_message.reply_text(
        f"✅ {metadata['title']} counted!\n"
        f"🎚 {metadata['difficulty'].title()} · +{score} point(s)\n"
        f"🏆 Every unique problem counts once during the challenge.\n"
        f"{suffix}"
    )


async def difficulty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = (query.data or "").split(":")
    if len(parts) != 3 or parts[0] != "diff" or parts[2] not in POINTS_BY_DIFFICULTY:
        await query.edit_message_text("❌ This difficulty selection is no longer valid.")
        return

    token = parts[1]
    difficulty = parts[2]
    pending_map = context.user_data.get("pending_difficulty_submissions", {})
    pending = pending_map.pop(token, None)

    if not pending:
        await query.edit_message_text(
            "⚠️ This submission request has expired. Please send the submission link again."
        )
        return

    if query.message and query.message.chat_id != pending["chat_id"]:
        await query.edit_message_text("❌ This submission belongs to another chat.")
        return

    if query.from_user.id != pending["user_id"]:
        await query.edit_message_text("❌ Only the participant who submitted the link can choose its difficulty.")
        return

    title = pending["problem_title"]
    points = POINTS_BY_DIFFICULTY[difficulty]
    result = save_competition_submission(
        chat_id=pending["chat_id"],
        user_id=pending["user_id"],
        day=pending["day"],
        problem_slug=pending["problem_slug"],
        problem_title=title,
        difficulty=difficulty,
        points=points,
        url=pending["url"],
        submitted_at=pending["submitted_at"],
    )

    if not result["counted"]:
        existing = result["existing"]
        await query.edit_message_text(
            f"⚠️ Duplicate: {title} was already counted on Day {existing[0]}. "
            f"It is worth {existing[3]} point(s), so this submission adds 0 points."
        )
        return

    backup_ok = await asyncio.to_thread(backup_to_github)
    suffix = (
        "💾 Backup saved."
        if backup_ok
        else "⚠️ GitHub backup failed — the score is only local until backup succeeds."
    )

    await query.edit_message_text(
        f"✅ {title} counted!\n"
        f"🎚 {difficulty.title()} · +{points} point(s)\n"
        f"🏆 Every unique problem counts once during the challenge.\n"
        f"{suffix}"
    )


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    ok = await asyncio.to_thread(backup_to_github)
    if ok:
        await update.effective_message.reply_text("💾 Backup completed successfully.")
    else:
        await update.effective_message.reply_text("❌ Backup failed. Check the Render logs and GitHub token permissions.")

async def submit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    if not context.args:
        await update.effective_message.reply_text(
            "Send your LeetCode submission link like:\n"
            "/submit https://leetcode.com/problems/two-sum/submissions/123456789/"
        )
        return
    match = LEETCODE_URL.search(context.args[0])
    if not match:
        await update.effective_message.reply_text("❌ That doesn't look like a LeetCode submission link.")
        return
    await record_submission(update, match.group(0), context)


async def submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_message.text:
        return
    match = LEETCODE_URL.search(update.effective_message.text)
    if not match:
        return
    register_user(update)
    await record_submission(update, match.group(0), context)


def incomplete_users(chat_id, day):
    conn = db()
    rows = conn.execute(
        """
        SELECT u.user_id, u.first_name, u.username
        FROM users u
        WHERE u.chat_id=?
          AND NOT EXISTS (
              SELECT 1
              FROM competition_submissions s
              WHERE s.chat_id=u.chat_id
                AND s.user_id=u.user_id
                AND s.day=?
          )
        ORDER BY u.first_name
        """,
        (chat_id, day),
    ).fetchall()
    conn.close()
    return rows


def mention_user(user_id, first_name, username):
    display = f"@{username}" if username else (first_name or "participant")
    return f'<a href="tg://user?id={user_id}">{html.escape(display)}</a>'


async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    chats = [row[0] for row in conn.execute("SELECT DISTINCT chat_id FROM users")]
    conn.close()
    day = current_day()

    for chat_id in chats:
        try:
            incomplete = incomplete_users(chat_id, day)
            if not incomplete:
                continue

            mentions = " ".join(
                mention_user(user_id, first_name, username)
                for user_id, first_name, username in incomplete
            )
            message = (
                "⏰ <b>Daily LeetCode challenge</b>\n\n"
                + challenge_message(day)
                + "\n\n👋 Still to submit: "
                + mentions
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="HTML",
            )
        except Exception:
            logging.exception("Failed to send reminder to %s", chat_id)

    # Keep GitHub as the durable copy of the live SQLite state.
    await asyncio.to_thread(backup_to_github)


async def test_tag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update)
    chat_id = update.effective_chat.id
    day = current_day()
    incomplete = incomplete_users(chat_id, day)

    if not incomplete:
        await update.effective_message.reply_text(
            f"🧪 Tag test passed: everyone registered in this chat has submitted Day {day}."
        )
        return

    mentions = " ".join(
        mention_user(user_id, first_name, username)
        for user_id, first_name, username in incomplete
    )
    await update.effective_message.reply_text(
        f"🧪 <b>Tag test</b> — Day {day}\n\n"
        f"These participants would be tagged by the reminder:\n{mentions}",
        parse_mode="HTML",
    )


def main():
    logging.basicConfig(level=logging.INFO)
    db()

    restored = restore_with_retries()
    if restored:
        backfill_competition_submissions()
        # Only back up after a successful restore. This prevents an empty or
        # incomplete local database from replacing the durable GitHub backup.
        backup_to_github()
    else:
        logging.error(
            "Startup restore failed; preserving GitHub backup and starting with local state only."
        )

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("random", random_problem))
    app.add_handler(CommandHandler("submit", submit_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CallbackQueryHandler(difficulty_callback, pattern=r"^diff:"))
    app.add_handler(CommandHandler("testtag", test_tag))
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
        url_path="telegram",
        webhook_url=f"https://{RENDER_EXTERNAL_URL.rstrip('/').removeprefix('https://').removeprefix('http://')}/telegram",
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
