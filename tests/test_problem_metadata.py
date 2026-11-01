import unittest

from problem_metadata import parse_neetcode_html


def page(slug, title, class_difficulty, text_difficulty):
    return f"""
    <!doctype html>
    <html>
      <head>
        <link rel="canonical" href="https://neetcode.io/problems/{slug}/question">
      </head>
      <body>
        <h1 class="problem-title">{title}</h1>
        <span class="difficulty-pill {class_difficulty}">{text_difficulty}</span>
      </body>
    </html>
    """


class NeetCodeMetadataTests(unittest.TestCase):
    def test_easy_problem(self):
        result = parse_neetcode_html(
            page("binary-tree-diameter", "Diameter of Binary Tree", "easy", "Easy"),
            "binary-tree-diameter",
        )
        self.assertEqual(
            result,
            {
                "title": "Diameter of Binary Tree",
                "difficulty": "EASY",
                "points": 1,
            },
        )

    def test_medium_problem(self):
        result = parse_neetcode_html(
            page("minimum-stack", "Min Stack", "medium", "Medium"),
            "minimum-stack",
        )
        self.assertEqual(result["difficulty"], "MEDIUM")
        self.assertEqual(result["points"], 2)

    def test_hard_problem(self):
        result = parse_neetcode_html(
            page("word-ladder", "Word Ladder", "hard", "Hard"),
            "word-ladder",
        )
        self.assertEqual(result["difficulty"], "HARD")
        self.assertEqual(result["points"], 4)

    def test_rejects_mismatched_class_and_text(self):
        result = parse_neetcode_html(
            page("binary-tree-diameter", "Diameter of Binary Tree", "medium", "Easy"),
            "binary-tree-diameter",
        )
        self.assertIsNone(result)

    def test_rejects_wrong_canonical_slug(self):
        result = parse_neetcode_html(
            page("some-other-problem", "Some Other Problem", "easy", "Easy"),
            "binary-tree-diameter",
        )
        self.assertIsNone(result)

    def test_rejects_ambiguous_multiple_pills(self):
        html = page("binary-tree-diameter", "Diameter of Binary Tree", "easy", "Easy")
        html = html.replace(
            "</body>",
            '<span class="difficulty-pill medium">Medium</span></body>',
        )
        self.assertIsNone(parse_neetcode_html(html, "binary-tree-diameter"))

    def test_rejects_missing_problem_metadata(self):
        self.assertIsNone(
            parse_neetcode_html(
                "<html><body>Unable to load this problem.</body></html>",
                "binary-tree-diameter",
            )
        )


if __name__ == "__main__":
    unittest.main()
