import base64
import hashlib
import html
import json
import os
import random
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Europe/Budapest")
START_DATE = datetime.fromisoformat("2026-10-06").date()
AI_FILE = "ai/daily_content.json"

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

def main():
    day = current_day()
    name, url = challenge(day)
    backup = load_backup()
    users = backup.get("users", [])
    submissions = backup.get("submissions", [])
    submitted = {
        (row["chat_id"], row["user_id"])
        for row in submissions
        if row["day"] == day
    }

    with open(AI_FILE, encoding="utf-8") as f:
        ai = json.load(f)

    selected_mode = mode()
    chats = sorted({row["chat_id"] for row in users})

    for chat_id in chats:
        if selected_mode == "morning":
            morning_concept = ai.get("morning_concept", "")
            morning_explanation = ai.get("morning_concept_explanation", "")
            if ai.get("next_day") == day:
                morning_concept = ai.get("next_morning_concept", morning_concept)
                morning_explanation = ai.get("next_morning_concept_explanation", morning_explanation)

            incomplete = [
                row for row in users
                if row["chat_id"] == chat_id
                and (chat_id, row["user_id"]) not in submitted
            ]
            if not incomplete:
                continue

            mentions = " ".join(
                mention(row["user_id"], row.get("first_name"), row.get("username"))
                for row in incomplete
            )
            text = (
                f"🌅 <b>Day {day}/30</b>\n\n"
                f"🧠 <b>{html.escape(name)}</b>\n{url}\n\n"
                f"💡 <b>Interview concept: {html.escape(morning_concept)}</b>\n"
                f"{html.escape(morning_explanation)}\n\n"
                f"👋 {mentions}"
            )
        else:
            if not any(row["chat_id"] == chat_id and row["day"] == day for row in submissions):
                continue
            feedback = ai.get("evening_feedback", "").strip()
            if not feedback:
                continue
            text = (
                f"🌙 <b>Day {day} — Evening takeaway</b>\n\n"
                f"{html.escape(feedback)}"
            )

        send_telegram(chat_id, text)

if __name__ == "__main__":
    main()
