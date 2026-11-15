"""Exercise the extractor against a tiny stand-in for the Lake process."""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from lean_reuse import extract_runner


class ExtractRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "target repo"
        self.repo.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        lake = self.bin / "lake"
        lake.write_text(
            f"#!{sys.executable}\n"
            "import json, os, pathlib, sys\n"
            "status = int(os.environ.get('EXTRACT_TEST_STATUS', '0'))\n"
            "if not status:\n"
            "    script = pathlib.Path(sys.argv[-1]).read_text()\n"
            "    pathlib.Path(os.environ['EXTRACT_OUT']).write_text(json.dumps({\n"
            "        'args': sys.argv[1:], 'script': script,\n"
            "        'imports': os.environ.get('EXTRACT_IMPORTS'),\n"
            "        'prefixes': os.environ['FULL_PREFIXES']}))\n"
            "sys.exit(status)\n"
        )
        lake.chmod(0o755)
        self.bin_patch = patch.object(extract_runner, "ELAN_BIN", str(self.bin))
        self.bin_patch.start()
        self.addCleanup(self.bin_patch.stop)

    def test_relative_paths_are_resolved_before_entering_target_repo(self):
        # Scratch and output may live in different, initially absent directories.
        out = os.path.relpath(self.root / "output" / "graph.tsv")
        scratch = os.path.relpath(self.root / "scratch")
        result = extract_runner.run_extract(
            str(self.repo), ["TorchLean.NN.Model"], ["TorchLean"], out, scratch
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(Path(out).read_text())
        self.assertIn("import TorchLean.NN.Model", payload["script"])
        self.assertTrue(Path(payload["args"][-1]).is_absolute())

    def run_cli(self, *extra):
        args = [
            "extract_runner", "--repo-dir", str(self.repo),
            "--imports", "TorchLean.Tensor.Shape,TorchLean.NN.Model",
            "--full-prefixes", "TorchLean",
            "--out", str(self.root / "graph.tsv"),
            "--scratch", str(self.root / "scratch"), *extra,
        ]
        with patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()):
            return extract_runner.main()

    def test_cli_dynamic_imports_do_not_expose_target_notation(self):
        self.assertEqual(self.run_cli("--dyn"), 0)
        payload = json.loads((self.root / "graph.tsv").read_text())
        self.assertIn("--run", payload["args"])
        self.assertEqual(payload["imports"], "TorchLean.Tensor.Shape,TorchLean.NN.Model")
        self.assertEqual(payload["prefixes"], "TorchLean")
        self.assertNotIn("import TorchLean.", payload["script"])
        self.assertIn("(level := .private)", payload["script"])

    def test_cli_propagates_lean_failure(self):
        with patch.dict(os.environ, {"EXTRACT_TEST_STATUS": "7"}):
            self.assertEqual(self.run_cli(), 7)
        self.assertFalse((self.root / "graph.tsv").exists())


if __name__ == "__main__":
    unittest.main()
