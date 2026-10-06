import html
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Europe/Budapest")
START_DATE = datetime.fromisoformat("2026-10-06").date()
AI_FILE = "ai/daily_content.json"

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

def current_day():
    today = datetime.now(TIMEZONE).date()
    return min(30, max(1, (today - START_DATE).days + 1))

def challenge(day):
    import random
    shuffled = random.Random(START_DATE.toordinal()).sample(CHALLENGES, len(CHALLENGES))
    return shuffled[(day - 1) % len(shuffled)]

def load_backup():
    raw = subprocess.check_output(
        ["git", "show", "data-backup:data/backup.json"],
        text=True,
    )
    return json.loads(raw)

def mention(user_id, first_name, username):
    display = f"@{username}" if username else (first_name or "participant")
    return f'<a href="tg://user?id={user_id}">{html.escape(display)}"'

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
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode())
        if not result.get("ok"):
            raise RuntimeError(result)

def mode():
    manual = os.environ.get("MANUAL_MODE")
    if manual:
        return manual
    schedule = os.environ.get("SCHEDULE", "")
    return "morning" if schedule.startswith("0 9") else "evening"

_metadata_cache = {}

def extract_problem_slug(url):
    match = re.search(r"https?://(?:www\.)?leetcode\.com/problems/([^/?\s]+)/submissions(?:/|$)", url, re.I)
    return match.group(1).lower() if match else None

def fetch_problem_metadata(problem_slug):
    if problem_slug in _metadata_cache:
        return _metadata_cache[problem_slug]

    payload = json.dumps({
        "query": QUESTION_METADATA_QUERY,
        "variables": {"titleSlug": problem_slug},
    }).encode("utf-8")
    request = urllib.request.Request(
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
        with urllib.request.urlopen(request, timeout=15) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None

    question = (body.get("data") or {}).get("question")
    difficulty = question.get("difficulty") if question else None
    title = question.get("title") if question else None
    if not title or difficulty not in POINTS_BY_DIFFICULTY:
        return None

    metadata = {
        "title": title,
        "difficulty": difficulty,
        "points": POINTS_BY_DIFFICULTY[difficulty],
    }
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

        if difficulty not in POINTS_BY_DIFFICULTY or points is None or not title:
            metadata = fetch_problem_metadata(problem_slug)
            if not metadata:
                continue
            difficulty = metadata["difficulty"]
            points = metadata["points"]
            title = metadata["title"]

        seen.add(key)
        entries.append({
            "chat_id": chat_id,
            "user_id": user_id,
            "day": int(row.get("day", 0)),
            "problem_slug": problem_slug,
            "problem_title": title,
            "difficulty": difficulty,
            "points": int(points),
            "url": row.get("url", ""),
            "submitted_at": row.get("submitted_at", ""),
        })

    return entries

def leaderboard_for_chat(entries, users, chat_id, day):
    by_user = {}
    for entry in entries:
        if str(entry["chat_id"]) != str(chat_id) or entry["day"] != day:
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

    results.sort(key=lambda row: (-row["points"], -row["questions"], (row["first_name"] or "").lower()))
    return results

def morning_text(day):
    name, url = challenge(day)
    return (
        f"🌅 <b>Day {day}/30 — LeetCode Competition</b>\n\n"
        f"🧠 <b>Official challenge: {html.escape(name)}</b>\n"
        f"{url}\n\n"
        "⚔️ <b>Competition rules</b>\n"
        "Submit any LeetCode problem you solve today — every unique problem counts.\n"
        "🟢 Easy = 1 point\n"
        "🟠 Medium = 2 points\n"
        "🔴 Hard = 4 points\n\n"
        "🚫 The same problem can only score once per participant during the 30-day challenge.\n"
        "🏆 At the end of the day, the highest score wins."
    )

def evening_text(day, entries, users, chat_id):
    name, url = challenge(day)
    rows = leaderboard_for_chat(entries, users, chat_id, day)

    lines = [
        f"🏆 <b>Day {day}/30 — Competition Results</b>",
        "",
        f"🧠 Official challenge: <b>{html.escape(name)}</b>",
        f"<a href="{url}">Open problem</a>",
        "",
        "📊 <b>Daily leaderboard</b>",
    ]

    for index, row in enumerate(rows, 1):
        display = f"@{row['username']}" if row["username"] else (row["first_name"] or "participant")
        lines.append(
            f"{index}. {html.escape(display)} — "
            f"{row['questions']} question{'s' if row['questions'] != 1 else ''} · "
            f"{row['points']} pts"
        )

    if not rows:
        lines.extend(["", "No participants are registered for this chat."])
        return "\n".join(lines)

    top = rows[0]
    tied = [
        row for row in rows
        if row["points"] == top["points"] and row["questions"] == top["questions"]
    ]

    if top["questions"] == 0:
        lines.extend(["", "🤝 <b>No winner today</b> — nobody submitted a counted problem."])
    elif len(tied) == 1:
        display = f"@{top['username']}" if top["username"] else (top["first_name"] or "participant")
        lines.extend([
            "",
            f"🥇 <b>Winner: {html.escape(display)}</b>",
            f"{top['points']} pts from {top['questions']} unique question{'s' if top['questions'] != 1 else ''}.",
        ])
    else:
        displays = [
            f"@{row['username']}" if row["username"] else (row["first_name"] or "participant")
            for row in tied
        ]
        lines.extend([
            "",
            f"🥇 <b>Joint winners: {html.escape(', '.join(displays))}</b>",
            f"{top['points']} pts from {top['questions']} unique questions each.",
        ])

    lines.extend([
        "",
        "⚔️ Scoring: Easy 1 · Medium 2 · Hard 4",
        "🚫 Duplicate problems are ignored for scoring.",
    ])
    return "\n".join(lines)

def main():
    day = current_day()
    backup = load_backup()
    users = backup.get("users", [])
    entries = build_competition_entries(backup)
    selected_mode = mode()
    chats = sorted({row["chat_id"] for row in users})

    if selected_mode == "morning":
        message = morning_text(day)
        for chat_id in chats:
            # Keep the morning announcement useful even when everybody has already submitted.
            send_telegram(chat_id, message)
        return

    for chat_id in chats:
        message = evening_text(day, entries, users, chat_id)
        send_telegram(chat_id, message)

if __name__ == "__main__":
    main()
