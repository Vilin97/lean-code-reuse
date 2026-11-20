import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AuthorReportTests(unittest.TestCase):
    def test_attribution_is_visible_safe_and_does_not_change_quality_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            input_file = tmp / "authors.json"
            name = '</script><img src=x onerror="alert(1)">'
            input_file.write_text(json.dumps({
                "torchlean": {
                    "status": "ok", "top_author": name, "top_author_sloc": 90,
                    "top_author_share": .9, "total_sloc": 100, "n_authors": 2,
                    "files_measured": 3, "revision": "a" * 40,
                    "revision_date": "2026-11-15T00:00:00+00:00", "measured_at": "2026-11-16T00:00:00+00:00",
                    "roots": ["TorchLean"], "top_author_ties": ["author1"],
                },
                "mathlib4": {"status": "error", "error": "history unavailable"},
            }))

            def generate(out, extra):
                cp = subprocess.run([
                    sys.executable, str(ROOT / "report/make_report.py"),
                    "--env", str(ROOT / "results/results_env.json"),
                    "--textual", str(ROOT / "results/results_textual.json"),
                    "--validation", str(ROOT / "results/validation.json"),
                    "--out", str(out), *extra,
                ], capture_output=True, text=True)
                self.assertEqual(cp.returncode, 0, cp.stderr)
                html = out.read_text()
                return html, json.loads(re.search(r"const DATA = (.*);", html)[1])

            _, baseline = generate(tmp / "baseline.html", [])
            html, measured = generate(tmp / "measured.html", ["--authorship", str(input_file)])
            self.assertEqual(measured["pca"], baseline["pca"])
            self.assertEqual(measured["composite"], baseline["composite"])
            self.assertEqual(measured["architecture"], baseline["architecture"])
            self.assertEqual(measured["repos"], baseline["repos"])
            rows = measured["author_concentration"]
            self.assertEqual(rows["torchlean"]["top_author"], name)
            self.assertEqual(rows["torchlean"]["top_author_share"], .9)
            self.assertEqual(rows["mathlib4"]["status"], "error")
            self.assertEqual(rows["pfr"]["status"], "unavailable")
            self.assertNotIn(name, html)
            self.assertIn("label", rows["atlas"], "Source attribution needs a label independent of graph sampling")
            self.assertEqual(rows["atlas"]["label"], "Meta ATLAS")


if __name__ == "__main__":
    unittest.main()
