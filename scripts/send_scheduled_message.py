import html
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from problem_metadata import lookup_problem_metadata as lookup_platform_problem_metadata
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError

TIMEZONE = timezone.utc
START_DATE = datetime.fromisoformat("2026-11-01").date()
AI_FILE = "ai/daily_content.json"
AUTO_SEND_PAUSED_UNTIL = datetime.fromisoformat("2026-11-13T14:40:00+00:00")

POINTS_BY_DIFFICULTY = {
    "EASY": 1,
    "MEDIUM": 2,
    "HARD": 4,
}
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

def current_day():
    return datetime.now(timezone.utc).date().toordinal()


def challenge_day_number(day):
    return (datetime.fromordinal(int(day)).date() - START_DATE).days + 1


def scheduled_day(selected_mode):
    """
    Return the challenge day represented by the scheduled message.
    Evening results belong to the challenge day whose 19:15 run was scheduled,
    even if GitHub Actions starts the delayed job after midnight.
    """
    now = datetime.now(TIMEZONE)
    reference_date = now.date()

    if selected_mode in {"evening", "penalty"}:
        # These reports refer to the UTC challenge day that just ended.
        if selected_mode == "penalty" or now.hour < 12:
            reference_date = reference_date.fromordinal(reference_date.toordinal() - 1)

    return reference_date.toordinal()

def challenge(day):
    import random
    shuffled = random.Random(START_DATE.toordinal()).sample(CHALLENGES, len(CHALLENGES))
    day_number = challenge_day_number(day)
    return shuffled[(day_number - 1) % len(shuffled)]

def load_backup():
    raw = subprocess.check_output(
        ["git", "show", "data-backup:data/backup.json"],
        text=True,
    )
    return json.loads(raw)

def mention(user_id, first_name, username):
    display = f"@{username}" if username else (first_name or "participant")
    return f'<a href="tg://user?id={user_id}">{html.escape(display)}</a>'

def send_telegram(chat_id, text):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    request = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Telegram sendMessage failed with HTTP {exc.code}: {detail}"
        ) from exc
    if not result.get("ok"):
        raise RuntimeError(f"Telegram sendMessage failed: {result}")

def mode():
    manual = os.environ.get("MANUAL_MODE")
    if manual:
        return manual
    schedule = os.environ.get("SCHEDULE", "")
    if schedule.startswith("0 9"):
        return "morning"
    if schedule.startswith("10 0"):
        return "penalty"
    return "evening"

_metadata_cache = {}

def extract_problem_slug(url):
    match = re.search(r"https?://(?:www\.)?leetcode\.com/problems/([^/?\s]+)/submissions(?:/|$)", url, re.I)
    if match:
        return "leetcode:" + match.group(1).lower()
    match = re.search(r"https?://(?:www\.)?neetcode\.io/problems/([^/?#\s)]+)", url, re.I)
    if match:
        return "neetcode:" + match.group(1).lower()
    return None

def fetch_problem_metadata(problem_slug):
    if problem_slug in _metadata_cache:
        return _metadata_cache[problem_slug]

    metadata = lookup_platform_problem_metadata(problem_slug)
    if metadata:
        _metadata_cache[problem_slug] = metadata
    return metadata


def build_competition_entries(backup):
    """
    Prefer the enriched competition_submissions written by the new bot.
    Also understand legacy submissions where a problem slug is visible in the URL.
    """
    source = backup.get("competition_submissions") or []
    if not source:
        source = backup.get("submissions", [])

    entries = []
    seen = set()

    for row in source:
        chat_id = row.get("chat_id")
        user_id = row.get("user_id")
        problem_slug = (row.get("problem_slug") or extract_problem_slug(row.get("url", "")))
        if chat_id is None or user_id is None or not problem_slug:
            continue

        key = (str(chat_id), str(user_id), problem_slug)
        if key in seen:
            continue

        difficulty = row.get("difficulty")
        points = row.get("points")
        title = row.get("problem_title")

        try:
            stored_points = int(points)
        except (TypeError, ValueError):
            stored_points = None

        needs_refresh = (
            problem_slug.startswith("neetcode:")
            or difficulty not in POINTS_BY_DIFFICULTY
            or stored_points != POINTS_BY_DIFFICULTY.get(difficulty)
            or not title
        )
        if needs_refresh:
            metadata = fetch_problem_metadata(problem_slug)
            if metadata:
                difficulty = metadata["difficulty"]
                points = metadata["points"]
                title = metadata["title"]
            elif (
                difficulty not in POINTS_BY_DIFFICULTY
                or stored_points != POINTS_BY_DIFFICULTY.get(difficulty)
                or not title
            ):
                continue
            else:
                points = stored_points
        else:
            points = stored_points

        seen.add(key)
        entries.append({
            "chat_id": chat_id,
            "user_id": user_id,
            "day": (
                datetime.fromisoformat(row["submitted_at"].replace("Z", "+00:00"))
                .astimezone(timezone.utc).date().toordinal()
                if row.get("submitted_at")
                else int(row.get("day", 0))
            ),
            "problem_slug": problem_slug,
            "problem_title": title,
            "difficulty": difficulty,
            "points": int(points),
            "url": row.get("url", ""),
            "submitted_at": row.get("submitted_at", ""),
        })

    return entries

def leaderboard_for_chat(entries, users, chat_id, day=None, month=None):
    by_user = {}
    for entry in entries:
        if str(entry["chat_id"]) != str(chat_id):
            continue
        if day is not None and entry["day"] != day:
            continue
        if month is not None and datetime.fromordinal(entry["day"]).strftime("%Y-%m") != month:
            continue
        key = entry["user_id"]
        bucket = by_user.setdefault(key, {"questions": 0, "points": 0})
        bucket["questions"] += 1
        bucket["points"] += entry["points"]

    results = []
    for user in users:
        if str(user.get("chat_id")) != str(chat_id):
            continue
        key = user["user_id"]
        bucket = by_user.get(key, {"questions": 0, "points": 0})
        results.append({
            "user_id": key,
            "first_name": user.get("first_name"),
            "username": user.get("username"),
            "questions": bucket["questions"],
            "points": bucket["points"],
        })

    results.sort(
        key=lambda row: (
            -row["points"],
            -row["questions"],
            (row["first_name"] or "").lower(),
        )
    )
    return results


def morning_text(day):
    name, url = challenge(day)
    return (
        f"🌅 <b>Day {challenge_day_number(day)} — LeetCode Competition</b>\n\n"
        f"🧠 <b>Official challenge: {html.escape(name)}</b>\n"
        f"{url}\n\n"
        "⚔️ <b>Competition rules</b>\n"
        "Submit any LeetCode problem you solve today — every unique problem counts.\n"
        "🟢 Easy = 1 point\n"
        "🟠 Medium = 2 points\n"
        "🔴 Hard = 4 points\n\n"
        "🚫 The same problem can only score once per participant.\n"
        "🏆 At the end of the day, the highest score wins."
    )


def render_leaderboard(title, rows, total=False):
    lines = [title]
    for index, row in enumerate(rows, 1):
        display = f"@{row['username']}" if row["username"] else (row["first_name"] or "participant")
        question_label = "total question" if total else "question"
        if row["questions"] != 1:
            question_label += "s"
        points_label = "total pts" if total else "pts"
        lines.append(
            f"{index}. {html.escape(display)} — "
            f"{row['questions']} {question_label} · {row['points']} {points_label}"
        )
    if not rows:
        lines.append("No participants are registered for this chat.")
    return lines


def winner_lines(rows):
    if not rows:
        return ["🤝 <b>No winner today</b> — no participants are registered."]
    top = rows[0]
    if top["questions"] == 0:
        return ["🤝 <b>No winner today</b> — nobody submitted a counted problem."]
    tied = [
        row for row in rows
        if row["points"] == top["points"] and row["questions"] == top["questions"]
    ]
    if len(tied) == 1:
        display = f"@{top['username']}" if top["username"] else (top["first_name"] or "participant")
        return [
            f"🥇 <b>Winner today: {html.escape(display)}</b>",
            f"{top['points']} pts from {top['questions']} unique "
            f"question{'s' if top['questions'] != 1 else ''}.",
        ]

    displays = [
        f"@{row['username']}" if row["username"] else (row["first_name"] or "participant")
        for row in tied
    ]
    return [
        f"🥇 <b>Joint winners today: {html.escape(', '.join(displays))}</b>",
        f"{top['points']} pts from {top['questions']} unique questions each.",
    ]


def evening_text(day, entries, users, chat_id):
    name, url = challenge(day)
    daily_rows = leaderboard_for_chat(entries, users, chat_id, day)
    month = datetime.fromordinal(day).strftime("%Y-%m")
    monthly_rows = leaderboard_for_chat(entries, users, chat_id, month=month)
    overall_rows = leaderboard_for_chat(entries, users, chat_id)

    lines = [
        f"🏆 <b>Day {challenge_day_number(day)} — Competition Results</b>",
        "",
        f"🧠 Official challenge: <b>{html.escape(name)}</b>",
        f'<a href="{html.escape(url, quote=True)}">Open problem</a>',
        "",
        *render_leaderboard("📅 <b>Today’s leaderboard</b>", daily_rows),
        "",
        *winner_lines(daily_rows),
        "",
        *render_leaderboard("🗓 <b>This month</b>", monthly_rows, total=True),
        "",
        *render_leaderboard("🏆 <b>Overall leaderboard</b>", overall_rows, total=True),
        "",
        "⚔️ Scoring: Easy 1 · Medium 2 · Hard 4",
        "🚫 Duplicate problems are ignored for scoring.",
    ]
    return "\n".join(lines)
def penalty_text(day, users, backup, chat_id):
    participation = {
        (str(row.get("chat_id")), str(row.get("user_id")), int(row.get("day", 0)))
        for row in backup.get("submissions", []) + backup.get("competition_submissions", [])
        if row.get("chat_id") is not None and row.get("user_id") is not None
    }
    participants = [row for row in users if str(row.get("chat_id")) == str(chat_id)]
    registered = [row for row in participants if row.get("revolut_username")]
    missing_registration = [row for row in participants if not row.get("revolut_username")]
    missed = [
        row for row in registered
        if (str(chat_id), str(row.get("user_id")), day) not in participation
    ]
    lines = [
        f"💶 <b>Day {challenge_day_number(day)} — Penalty report</b>",
        "",
        "Rule: missing the day means sending €1 to every other registered participant.",
        "",
    ]
    if missing_registration:
        names = [
            f"@{row['username']}" if row.get("username") else (row.get("first_name") or "participant")
            for row in missing_registration
        ]
        lines.extend([
            "⚠️ <b>Revolut registration missing</b>",
            html.escape(", ".join(names)),
            "These participants are excluded from transfers until they register with /revolut username.",
            "",
        ])
    if not registered:
        lines.append("No participants have registered Revolut usernames yet. Ask everyone to use /revolut username.")
        return "\n".join(lines)
    if not missed:
        lines.append("✅ No registered participant missed this day. No penalties.")
        return "\n".join(lines)

    lines.append("❌ <b>Missed the challenge</b>")
    for payer in missed:
        payer_name = f"@{payer['username']}" if payer.get("username") else (payer.get("first_name") or "participant")
        payer_revolut = payer["revolut_username"]
        recipients = [row for row in registered if row.get("user_id") != payer.get("user_id")]
        total = len(recipients)
        lines.append("")
        lines.append(f"• <b>{html.escape(payer_name)}</b> (@{html.escape(payer_revolut)}) missed Day {challenge_day_number(day)}.")
        if not recipients:
            lines.append("No other registered recipients.")
            continue
        lines.append(f"Must send €1 to each of {total} participant{'s' if total != 1 else ''}:")
        for recipient in recipients:
            lines.append(f"  • @{html.escape(recipient['revolut_username'])}")
        lines.append(f"<b>Total owed: €{total}</b>")
    return "\n".join(lines)


def main():
    if datetime.now(timezone.utc) < AUTO_SEND_PAUSED_UNTIL:
        print(f"Scheduled Telegram messages are paused until {AUTO_SEND_PAUSED_UNTIL.isoformat()}.")
        return

    backup = load_backup()
    users = backup.get("users", [])
    entries = build_competition_entries(backup)
    selected_mode = mode()
    day = scheduled_day(selected_mode)
    chats = sorted({row["chat_id"] for row in users})

    if selected_mode == "morning":
        message = morning_text(day)
        for chat_id in chats:
            send_telegram(chat_id, message)
        return

    for chat_id in chats:
        if selected_mode == "penalty":
            message = penalty_text(day, users, backup, chat_id)
        else:
            message = evening_text(day, entries, users, chat_id)
        send_telegram(chat_id, message)

if __name__ == "__main__":
    main()
