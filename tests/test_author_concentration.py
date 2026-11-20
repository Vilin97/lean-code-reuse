import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class AuthorConcentrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Test Committer")
        self.git("config", "user.email", "committer@example.org")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args, **kwargs):
        return subprocess.check_output(["git", "-C", str(self.repo), *args],
                                       text=True, stderr=subprocess.STDOUT, **kwargs).strip()

    def write(self, path, text):
        p = self.repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def commit(self, name="Alice", email="alice@example.org"):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture change", env={
            **os.environ, "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
        })
        return self.git("rev-parse", "HEAD")

    def measure(self, roots=None, **kwargs):
        self.assertIsNotNone(importlib.util.find_spec("lean_reuse.author_concentration"),
                             "The Git attribution collector must exist")
        from lean_reuse.author_concentration import measure_repo
        return measure_repo(str(self.repo), roots or ["Lib"], **kwargs)

    def test_surviving_code_lines_ignore_comments_deleted_code_and_whitespace_edits(self):
        self.write("Lib/A.lean", '/- outer /- nested -/ comment -/\nnamespace Demo\ndef first : Nat := 1\ndef second : Nat := 2\n\ndef text : String := "-- literal"\nend Demo\n')
        self.write("Tests/Excluded.lean", "def unrelated := 0\n")
        self.commit()
        self.write("Lib/A.lean", '/- outer /- nested -/ comment -/\nnamespace Demo\ndef second : Nat := 3\ndef third : Nat := 4\n\ndef text : String := "-- literal"\nend Demo\n')
        self.commit("Bob", "bob@example.org")
        p = self.repo / "Lib/A.lean"
        p.write_text("\n".join("  " + line for line in p.read_text().splitlines()) + "\n")
        self.commit("Formatter", "format@example.org")
        result = self.measure()
        self.assertEqual(result["total_sloc"], 5)
        self.assertEqual({r["name"]: r["sloc"] for r in result["authors"]}, {"Alice": 3, "Bob": 2})
        self.assertEqual(result["top_author_sloc"], 3)
        self.assertEqual(result["top_author_share"], .6)
        self.assertEqual(result["files"], ["Lib/A.lean"])
        self.assertEqual(result["files_measured"], 1)

    def test_mailmap_aliases_merge_but_same_display_name_does_not(self):
        self.write("Lib/A.lean", "def alpha : Nat := 123456\n")
        self.commit("Old Alice", "old@example.org")
        self.write("Lib/B.lean", "def beta : Nat := 654321\n")
        self.commit("Alice", "alice@example.org")
        self.write("Lib/C.lean", "def gamma : Nat := 987654\n")
        self.commit("Alice", "different@example.org")
        self.write(".mailmap", "Alice <alice@example.org> Old Alice <old@example.org>\n")
        self.commit()
        result = self.measure()
        self.assertEqual(sorted(r["sloc"] for r in result["authors"]), [1, 2])
        self.assertEqual(result["top_author_sloc"], 2)
        self.assertAlmostEqual(result["top_author_share"], 2/3)
        self.assertEqual(len({r["id"] for r in result["authors"]}), 2)
        self.assertNotIn("@example.org", str(result))

    def test_pinned_revision_and_cache_ignore_worktree_edits(self):
        self.write("Lib/A.lean", "def original : Nat := 12345\n")
        old = self.commit()
        cache = str(Path(self.tmp.name) / "cache")
        first = self.measure(revision=old, cache_dir=cache)
        self.write("Lib/A.lean", "def original : Nat := 12345\ndef additional : Nat := 67890\n")
        new = self.commit("Bob", "bob@example.org")
        self.write("Lib/A.lean", "not the committed source\n" * 20)
        self.assertEqual(self.measure(revision=old, cache_dir=cache)["total_sloc"], first["total_sloc"])
        changed = self.measure(revision=new, cache_dir=cache)
        self.assertEqual(changed["total_sloc"], 2)
        self.assertEqual(changed["revision"], new)

    def test_root_files_and_exclusions_do_not_double_count(self):
        for f in ("Lib/A.lean", "Lib/docs/Hidden.lean", "Lib/.lake/Dep.lean", "root.lean"):
            self.write(f, "def value : Nat := 12345\n")
        self.commit()
        result = self.measure(["Lib", "Lib/A.lean", "root.lean"])
        self.assertEqual(result["files"], ["Lib/A.lean", "root.lean"])
        self.assertEqual(result["total_sloc"], 2)

    def test_empty_code_has_no_fabricated_owner_and_missing_scope_fails(self):
        self.write("Lib/A.lean", "/- comment only -/\n\n")
        self.commit()
        result = self.measure()
        self.assertEqual(result["total_sloc"], 0)
        self.assertIsNone(result["top_author_share"])
        self.assertIsNone(result["top_author"])
        with self.assertRaises(ValueError):
            self.measure(["DoesNotExist"])

    def test_one_valid_root_does_not_hide_another_missing_root(self):
        self.write("Lib/A.lean", "def value : Nat := 12345\n")
        self.commit()
        with self.assertRaisesRegex(ValueError, "Missing.*MissingRoot"):
            self.measure(["Lib", "MissingRoot"])

    def test_shallow_history_is_refused(self):
        self.write("Lib/A.lean", "def first : Nat := 12345\n")
        self.commit()
        self.write("Lib/B.lean", "def second : Nat := 67890\n")
        self.commit("Bob", "bob@example.org")
        clone = Path(self.tmp.name) / "shallow"
        subprocess.run(["git", "clone", "-q", "--depth", "1", self.repo.as_uri(), str(clone)], check=True)
        self.repo = clone
        with self.assertRaisesRegex(ValueError, "[Ss]hallow"):
            self.measure()

    def test_missing_email_retains_lines_with_explicit_name_fallback(self):
        self.write("Lib/A.lean", 'def hello : String := "world"\n')
        self.commit("Lean 4 VS Code Extension", "")
        result = self.measure()
        self.assertEqual(result["total_sloc"], 1)
        self.assertEqual(result["top_author"], "Lean 4 VS Code Extension")
        self.assertEqual(result["name_only_sloc"], 1)
        self.assertEqual(result["authors"][0]["identity_basis"], "name_only")

    def test_cli_records_missing_repo_without_losing_valid_measurements(self):
        import json
        import sys
        self.write("Lib/A.lean", "def value : Nat := 12345\n")
        self.commit()
        manifest = Path(self.tmp.name) / "manifest.json"
        manifest.write_text(json.dumps({
            "missing": {"repo_dir": str(self.repo / "missing"), "roots": ["Lib"]},
            "valid": {"repo_dir": str(self.repo), "roots": ["Lib"]},
        }))
        out = Path(self.tmp.name) / "out.json"
        cp = subprocess.run([sys.executable, "-m", "lean_reuse.author_concentration",
                             "--manifest", str(manifest), "--out", str(out),
                             "--cache-dir", str(Path(self.tmp.name) / "cache")],
                            capture_output=True, text=True)
        self.assertEqual(cp.returncode, 1)
        self.assertTrue(out.exists(), cp.stderr)
        rows = json.loads(out.read_text())
        self.assertEqual(rows["missing"]["status"], "error")
        self.assertEqual(rows["valid"]["total_sloc"], 1)


if __name__ == "__main__":
    unittest.main()
