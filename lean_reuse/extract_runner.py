"""Run the environment-graph extractor inside a built Lean repo.

Generates a script from extract_template.lean (injecting `import` lines for
the target's root modules), then runs `lake env lean <script>` in the repo so
it picks up the repo's toolchain and LEAN_PATH. The repo must be built.
"""

from __future__ import annotations

import os
import re
import subprocess

TEMPLATE = os.path.join(os.path.dirname(__file__), "extract", "extract_template.lean")
TEMPLATE_DYN = os.path.join(
    os.path.dirname(__file__), "extract", "extract_template_dyn.lean"
)
ELAN_BIN = os.path.expanduser("~/.elan/bin")


def run_extract(
    repo_dir: str,
    imports: list[str],
    full_prefixes: list[str],
    out_path: str,
    scratch_dir: str,
    timeout: int = 4 * 3600,
    dyn: bool = False,
    private_level: bool = True,
) -> subprocess.CompletedProcess:
    def quote_mod(m: str) -> str:
        if "«" in m:  # caller already quoted problem segments
            return m
        comps = m.split(".")
        return ".".join(
            c if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_']*", c) or c.startswith("«") else f"«{c}»"
            for c in comps
        )

    tag = imports[0].replace(".", "_") if imports else "none"
    env = dict(os.environ)
    env["EXTRACT_OUT"] = out_path
    env["FULL_PREFIXES"] = ",".join(full_prefixes)
    env["PATH"] = ELAN_BIN + ":" + env.get("PATH", "")
    if dyn:
        with open(TEMPLATE_DYN) as f:
            tpl = f.read()
        script = tpl.replace(
            "-- LEVEL_ARG", "(level := .private)" if private_level else ""
        )
        script_path = os.path.join(scratch_dir, f"extract_dyn_{tag}.lean")
        env["EXTRACT_IMPORTS"] = ",".join(m.replace("«", "").replace("»", "") for m in imports)
        cmd = ["lake", "env", "lean", "--run", script_path]
    else:
        with open(TEMPLATE) as f:
            tpl = f.read()
        script = tpl.replace(
            "-- EXTRA_IMPORTS", "\n".join(f"import {quote_mod(m)}" for m in imports)
        )
        script_path = os.path.join(scratch_dir, f"extract_{tag}.lean")
        cmd = ["lake", "env", "lean", script_path]
    with open(script_path, "w") as f:
        f.write(script)
    return subprocess.run(
        cmd,
        cwd=repo_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-dir", required=True)
    ap.add_argument("--imports", required=True, help="comma-separated root modules")
    ap.add_argument("--full-prefixes", default="", help="comma-separated module prefixes")
    ap.add_argument("--out", required=True)
    ap.add_argument("--scratch", required=True)
    args = ap.parse_args()
    cp = run_extract(
        args.repo_dir,
        [m for m in args.imports.split(",") if m],
        [p for p in args.full_prefixes.split(",") if p],
        args.out,
        args.scratch,
    )
    print("returncode:", cp.returncode)
    print(cp.stdout[-4000:])
    print(cp.stderr[-4000:])
