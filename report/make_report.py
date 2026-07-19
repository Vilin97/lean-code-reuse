"""Assemble the findings report from results JSONs + validation + bench.

Corpus: formalization projects only (no compiler/stdlib, no teaching games,
no conjecture lists). Framing: discriminate LOW from HIGH quality — not AI
from human. Quality anchors (community-vetted HIGH vs unreviewed/sorried LOW)
calibrate each metric; a composite percentile score ranks everyone.
"""

from __future__ import annotations

import argparse
import json
import math
import os

# provenance groups (colors only — the analysis axis is quality, not authorship)
GROUP_OF = {
    "mathlib4": 0, "cslib": 0, "scilean": 0, "flt": 0, "pfr": 0,
    "addcombi": 0, "pnt": 0, "carleson": 0, "analysis": 0,
    "physlib": 1, "equational_theories": 1, "lean-pool": 1,
    "tauceti": 2, "strongpnt": 2,
    "atlas": 3, "seed-prover": 3, "superhuman": 3, "erdos90": 3, "clawristotle": 3,
}
GROUPS = ["Human", "Human + AI mix", "AI, curated", "AI, less curated", "—"]
ORDER = [
    "mathlib4", "flt", "pfr", "addcombi", "carleson", "pnt", "analysis",
    "cslib", "scilean", "physlib", "equational_theories", "lean-pool",
    "tauceti", "strongpnt", "atlas", "erdos90", "clawristotle",
    "seed-prover", "superhuman",
]
# quality anchors for calibration (declared, defensible, and clearly labeled)
HIGH_ANCHOR = {"mathlib4", "flt", "pfr", "carleson", "addcombi"}
LOW_ANCHOR = {"seed-prover", "superhuman", "atlas"}
CCDF_KEYS = ["mathlib4", "physlib", "tauceti", "strongpnt", "atlas", "erdos90", "seed-prover"]
VOCAB_KEYS = ["carleson", "flt", "tauceti", "strongpnt", "erdos90"]
DISPLAY_LABEL = {}

# metrics used in the composite quality score: (label, accessor, higher_is_better)
COMPOSITE = [
    ("cross-dir reuse", lambda r: r["m3"]["crossdir"]),
    ("used outside file", lambda r: r["m3"]["outside"]),
    ("granular imports", lambda r: -r["m9"]["whole_ml"]),
    ("no sorries", lambda r: -r["m8"]["sorry"]),
    ("no duplication", lambda r: -r["m7"]["dup"]),
    ("doc coverage", lambda r: r["m10"].get("pct_defs_with_doc")),
    ("elab economy", lambda r: -r["m13"]["secs_per_kloc"] if r["m13"].get("secs_per_kloc") is not None else None),
]


def pack_repo(key, res, tier):
    meta, m = res["meta"], res["metrics"]
    d, s, c, e = m["reuse_degree"], m["statement_vs_proof"], m["cross_file"], m["external_reuse"]
    return {
        "key": key, "label": DISPLAY_LABEL.get(key, meta["label"]), "cat": meta["category"],
        "group": GROUP_OF[key], "tier": tier, "stars": meta["stars"],
        "url": meta["url"], "files": meta["files"], "loc": meta["loc"],
        "decls": d["n_reusable_decls"], "alldecls": meta["decls"], "edges": meta["edges"],
        "provenance": meta["provenance"],
        "excluded": False,
        "anchor": "high" if key in HIGH_ANCHOR else "low" if key in LOW_ANCHOR else None,
        "m1": {
            "mean": d["degree"]["mean"], "median": d["degree"]["median"],
            "p90": d["degree"]["p90"], "max": d["degree"]["max"],
            "never": d["pct_never_reused"], "ge2": d["pct_reused_ge2"],
            "ccdf": d["ccdf"], "top": d["top"][:10],
        },
        "m2": {
            "sig": s["share_signature"], "val": s["share_value"], "prf": s["share_proof"],
            "load": s["load_bearing_share"], "thmstmt": s["pct_theorems_used_in_statements"],
        },
        "m3": {
            "crossfile": c["pct_edges_cross_file"], "crossdir": c["pct_edges_cross_dir"],
            "outside": c["pct_decls_used_outside_file"],
            "five": c.get("pct_decls_used_in_5plus_external_files", 0),
        },
        "m4": {
            "ml_per_decl": e["mathlib_refs_per_decl"], "vocab": e["mathlib_vocab"],
            "vocab1k": e["mathlib_vocab_per_1k_refs"],
            "ext_int": e["external_internal_ratio"], "top": e["top_mathlib"][:10],
        },
        "m5": {
            "gini": m["concentration"].get("gini"),
            "top1": m["concentration"].get("top1pct_share"),
            "top10": m["concentration"].get("top10pct_share"),
        },
        "m6": {
            "maxd": m["dependency_depth"]["max_depth"],
            "meand": m["dependency_depth"]["mean_depth"],
            "p90d": m["dependency_depth"]["p90_depth"],
            "cyc": m["dependency_depth"]["pct_in_cycles"],
        },
        "m7": {
            "dup": m["duplication"]["body_dup_rate"], "dupn": m["duplication"]["body_dup_n"],
            "dupmax": m["duplication"]["body_max_cluster"], "sdup": m["duplication"]["stmt_dup_rate"],
        },
        "m8": {
            "sorry": m["proof_economy"]["sorry_rate"], "nsorry": m["proof_economy"]["n_sorried_theorems"],
            "pl_med": m["proof_economy"]["proof_lines"]["median"],
            "rpp": m["proof_economy"]["refs_per_proof"],
        },
        "m9": {
            "whole_ml": m["import_graph"]["pct_files_importing_all_mathlib"],
            "fanin2": m["import_graph"]["pct_files_fan_in_ge2"],
        },
        "m10": m.get("doc_coverage", {}),
        "m11": m.get("complexity", {}),
        "m12": m.get("trust_base", {}),
        "m13": m.get("elab_cost", {"secs_per_kloc": None}),
    }


def auc(hi_vals, lo_vals, higher_is_good):
    pairs = [(h, l) for h in hi_vals for l in lo_vals]
    if not pairs:
        return 0.5
    wins = sum(1 for h, l in pairs if h != l and (h > l) == higher_is_good)
    ties = sum(1 for h, l in pairs if h == l)
    return (wins + 0.5 * ties) / len(pairs)


def med(vals):
    v = sorted(vals)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True)
    ap.add_argument("--textual", required=True)
    ap.add_argument("--validation", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    env = json.load(open(args.env))
    tx = json.load(open(args.textual))
    validation = json.load(open(args.validation))

    repos = []
    for k in ORDER:
        if k in env:
            r = pack_repo(k, env[k], "exact")
        elif k in tx:
            r = pack_repo(k, tx[k], "textual")
        else:
            continue
        repos.append(r)
    byk = {r["key"]: r for r in repos}

    totals = {
        "repos": len(repos),
        "decls": sum(r["alldecls"] for r in repos),
        "edges": sum(r["edges"] for r in repos),
        "loc": sum(r["loc"] for r in repos),
        "envRepos": sum(1 for r in repos if r["tier"] == "exact"),
    }

    # CCDF series with pixel-space label de-collision
    ccdf = []
    for k in CCDF_KEYS:
        if k not in byk:
            continue
        r = byk[k]
        pts = sorted(((int(t), v) for t, v in r["m1"]["ccdf"].items()), key=lambda p: p[0])
        ccdf.append({"label": r["label"], "group": r["group"],
                     "dash": r["tier"] != "exact", "pts": pts})

    def last_y(s):
        return [p for p in s["pts"] if p[1] > 0][-1][1]

    def ypx(v):
        return 12 + (-math.log10(max(v, 1e-4))) / 4 * 328

    prev_eff = -1e9
    for i in sorted(range(len(ccdf)), key=lambda i: ypx(last_y(ccdf[i]))):
        base = ypx(last_y(ccdf[i]))
        eff = max(prev_eff + 14, base)
        ccdf[i]["dy"] = round(eff - base, 1)
        prev_eff = eff

    vocab = [
        {"label": byk[k]["label"], "vocab": byk[k]["m4"]["vocab"], "top": byk[k]["m4"]["top"]}
        for k in VOCAB_KEYS if k in byk and byk[k]["m4"]["vocab"]
    ]

    # ---- anchor-calibrated AUC table ----------------------------------------
    hi = [byk[k] for k in HIGH_ANCHOR if k in byk]
    lo = [byk[k] for k in LOW_ANCHOR if k in byk]

    def fmtv(v, pct=False):
        if v is None:
            return "—"
        return f"{v * 100:.1f}%" if pct else f"{v:.2f}" if isinstance(v, float) else str(v)

    metrics = [
        ("M3 · edges crossing directories", lambda r: r["m3"]["crossdir"], True, True),
        ("M3 · decls used outside their file", lambda r: r["m3"]["outside"], True, True),
        ("M9 · files importing all of Mathlib", lambda r: r["m9"]["whole_ml"], False, True),
        ("M10 · defs with docstrings", lambda r: r["m10"].get("pct_defs_with_doc"), True, True),
        ("M10 · comment density", lambda r: r["m10"].get("comment_density"), True, True),
        ("M13 · elaboration secs per kLOC", lambda r: r["m13"].get("secs_per_kloc"), False, False),
        ("M8 · sorried theorems", lambda r: r["m8"]["sorry"], False, True),
        ("M7 · duplicate bodies", lambda r: r["m7"]["dup"], False, True),
        ("M11 · branching tactics per proof", lambda r: r["m11"].get("branch_per_proof"), False, False),
        ("M1 · share reused >=2", lambda r: r["m1"]["ge2"], True, True),
        ("M1 · share never reused", lambda r: r["m1"]["never"], False, True),
        ("M2 · statement share of refs", lambda r: r["m2"]["sig"], True, True),
        ("M4 · Mathlib refs per decl", lambda r: r["m4"]["ml_per_decl"] or None, True, False),
        ("M5 · top-1% reuse share", lambda r: r["m5"]["top1"] or 0, False, True),
        ("M6 · max dependency depth", lambda r: r["m6"]["maxd"], True, False),
        ("M12 · axioms per 1k decls", lambda r: r["m12"].get("axioms_per_1k_decls"), False, False),
    ]
    auc_rows = []
    for label, f, good_high, pct in metrics:
        hv = [f(r) for r in hi if f(r) is not None]
        lv = [f(r) for r in lo if f(r) is not None]
        if not hv or not lv:
            continue
        a = auc(hv, lv, good_high)
        mids = [f(byk[k]) for k in ORDER
                if k in byk and k not in HIGH_ANCHOR and k not in LOW_ANCHOR
                and f(byk[k]) is not None]
        auc_rows.append({
            "label": label, "dir": "↑ good" if good_high else "↓ good",
            "medH": fmtv(med(hv), pct), "medM": fmtv(med(mids), pct) if mids else "—",
            "medL": fmtv(med(lv), pct), "auc": round(a, 3),
        })
    auc_rows.sort(key=lambda r: -abs(r["auc"] - 0.5))

    # ---- composite quality score (percentile-rank mean over discriminators) --
    comp = []
    for r in repos:
        parts = []
        for label, f in COMPOSITE:
            v = f(r)
            if v is None:
                continue
            others = [f(o) for o in repos if f(o) is not None]
            rank = sum(1 for o in others if o < v) + 0.5 * sum(1 for o in others if o == v)
            parts.append(rank / len(others))
        comp.append({"key": r["key"], "label": r["label"], "group": r["group"],
                     "tier": r["tier"], "anchor": r["anchor"],
                     "score": round(sum(parts) / len(parts), 3),
                     "n_metrics": len(parts)})
    comp.sort(key=lambda c: -c["score"])

    data = {
        "groups": GROUPS,
        "totals": totals,
        "repos": repos,
        "ccdf": ccdf,
        "vocab": vocab,
        "auc": auc_rows,
        "composite": comp,
        "validation": validation,
        "verdicts": VERDICTS,
        "prose": build_prose(byk, validation),
        "footer": FOOTER,
    }

    tpl = open(os.path.join(os.path.dirname(__file__), "template.html")).read()
    html = tpl.replace("/*__DATA__*/", json.dumps(data))
    with open(args.out, "w") as f:
        f.write(html)
    print(f"wrote {args.out} ({len(html)//1024} KB)")


VERDICTS = [
    {"good": True, "title": "Cross-directory reuse (M3)",
     "text": "The strongest structural separator against the low anchors: high-quality libraries interweave their directories; dumps and archipelagos don't. LeanPool's 93 directories with 0.1% cross-dir reuse reflect its pool-of-projects design, not its authorship."},
    {"good": True, "title": "Docstring coverage (M10)",
     "text": "A process signal: Mathlib's linter enforces docstrings on definitions and the habit propagates through reviewed projects; unreviewed corpora rarely fake it. Mirrors the SE finding that process metrics out-predict product metrics."},
    {"good": True, "title": "Elaboration cost per LOC (M13)",
     "text": "The heartbeats hypothesis: brute-force tactics make the elaborator grind. Measured by re-elaborating sampled files with import-load baselines subtracted — see §8 for which corpora pay more per line."},
    {"good": True, "title": "Hygiene profile (M7/M8/M9)",
     "text": "Sorries, duplicate bodies, wholesale imports: each catches a different failure mode; jointly with locality they separate the anchors completely. Cheap to compute, hard to fail accidentally."},
    {"good": False, "title": "Raw reuse counts (M1)",
     "text": "Median in-degree is a coin flip; never-reused inverts on bespoke proof towers (superhuman reuses 97% of its lemmas — exactly once each). Volume of reuse cannot tell a cathedral from scaffolding."},
    {"good": False, "title": "Depth, leverage, statement share",
     "text": "Depth is inheritable via vendored code; Mathlib leverage measures participation, which every serious pipeline has; statement share inverts on hypothesis-heavy restated problem statements."},
]

FOOTER = (
    "Generated 2026-07-18 by the <span class=\"mono\">lean_reuse</span> toolkit — "
    "textual tier: scoping parser; exact tier: Lean metaprogram over elaborated "
    "environments (getUsedConstants on types and values, generated auxiliaries "
    "contracted). Elaboration cost: timed re-elaboration of sampled files per built "
    "repo, import baseline subtracted. Corpus: formalization projects only, pinned "
    "2026-07-18. Code: lean-code-reuse repo, one module per metric."
)


def build_prose(byk, validation):
    ml = byk["mathlib4"]
    sp = byk.get("seed-prover")
    sh = byk.get("superhuman")
    tc = byk.get("tauceti")
    lp = byk.get("lean-pool")
    at = byk.get("atlas")
    e9 = byk.get("erdos90")
    cw = byk.get("clawristotle")
    spnt = byk.get("strongpnt")
    mv = validation.get("mathlib4", {})

    def pct(v):
        return f"{v*100:.1f}%" if v is not None else "—"

    return {
        "reuseProse": f"""
<p>Mathlib's curve is the reference: a heavy tail riding on a thick middle —
{pct(ml['m1']['ge2'])} of its {ml['decls']:,} reusable declarations are used by at least two
others. But raw counts mislead in both directions: <b>superhuman</b> (58 bespoke proof
towers) has one of the lowest never-reused rates in the corpus ({pct(sh['m1']['never'])})
because every lemma feeds the next step exactly once, and StrongPNT's curve tracks the human
research projects closely. Counting reuse is not enough; the sections below ask
<em>where</em> it lives and <em>what it costs</em>.</p>""",
        "whereProse": f"""
<p>File-system locality separates the anchors cleanly: {pct(ml['m3']['outside'])} of Mathlib
declarations are used outside their defining file, research formalizations cluster at
20–40%, while Seed-Prover sits at {pct(sp['m3']['outside'])} and superhuman at
{pct(sh['m3']['outside'])}. Clawristotle ({pct(cw['m3']['outside'])}) shows the caveat: a
disciplined single-theorem project — of any authorship — is structured like a small research
formalization, and locality metrics respect that. Structure metrics measure the artifact,
not the author; that is exactly why the calibration below anchors on quality rather than
provenance.</p>""",
        "mlProse": f"""
<p>Every serious corpus leans on Mathlib — leverage measures <em>participation</em>, not
quality. TauCeti cites {tc['m4']['ml_per_decl']:.0f} references per declaration over a
{tc['m4']['vocab']:,}-lemma vocabulary; StrongPNT {spnt['m4']['ml_per_decl']:.0f} over
{spnt['m4']['vocab']:,}; Erdős-90's vocabulary is {e9['m4']['vocab']:,}. LeanPool's
{lp['m4']['vocab']:,} — the largest — partly reflects the human projects it absorbs (a large
portion of LeanPool is not AI-written, consistent with it scoring in the human band
throughout this study). The discriminating signal in this chart is the vertical axis:
internal dead weight at comparable leverage.</p>
<p class="note">Hygiene aside: LeanPool redeclares Mathlib names (<code>LieHom.snd</code>),
so it cannot be imported alongside full Mathlib — found when the extractor tried.</p>""",
        "hygieneProse": f"""
<p>Seed-Prover's {pct(sp['m7']['dup'])} duplicate-body rate and Meta ATLAS's
{at['m8']['nsorry']:,} sorried theorems ({pct(at['m8']['sorry'])}) are the extreme cases;
Erdős-90 still duplicates {pct(e9['m7']['dup'])} of bodies in its submission tree. Two
readings need context before judging: Tao's <i>Analysis</i> shows
{pct(byk['analysis']['m8']['sorry'])} sorries because exercises are deliberately left to
the reader, and SciLean's {pct(byk['scilean']['m8']['sorry'])} reflects its explicit
<code>sorry_proof</code> convention for numerical facts. The curated AI projects are clean
on both counts (TauCeti: {pct(tc['m7']['dup'])} duplicates, zero sorries; StrongPNT:
{pct(spnt['m7']['dup'])} duplicates, {pct(spnt['m8']['sorry'])} sorries).</p>""",
        "discussProse": """
<p>Calibrated against the declared anchors, the discriminating metrics form a coherent
family: <b>organization</b> (cross-directory reuse, outside-file reuse), <b>process
discipline</b> (docstring coverage, granular imports, sorry hygiene), and <b>economy</b>
(duplication, elaboration cost per line). The metrics that fail — raw reuse counts, depth,
Mathlib leverage, statement share — are <em>volume</em> metrics that a large or
machine-generated corpus satisfies incidentally. This mirrors three decades of software
measurement: volume-derived indices (Halstead, McCabe aggregates, the Maintainability
Index) predict quality poorly and average away power-law tails, while process signals and
simple hygiene risk-profiles are the robust predictors. The five-check profile here is a
SIG-style risk profile adapted to Lean.</p>
<p>The composite percentile score below makes the quality ordering explicit — and it is
visibly <em>not</em> a provenance ordering: LeanPool (mixed authorship) and the curated AI
projects sit inside the human band, while the lowest positions are held by unreviewed
corpora regardless of who — or what — wrote them.</p>""",
        "validityProse": f"""
<p><b>Tier agreement.</b> Where both tiers exist they correlate at Spearman ρ
{mv.get('spearman_indeg','—')} across Mathlib's {mv.get('n_joined',0):,} joined
declarations (0.76–0.79 on every repo checked); the textual tier under-counts dot-notation
and instance uses but preserves ranking, justifying its use for the unbuildable corpora
(Seed-Prover, superhuman, Erdős-90, Clawristotle).</p>
<p><b>Anchors, not ground truth.</b> "High" anchors are maintainer-reviewed,
Mathlib-integration-bound projects (Mathlib, FLT, PFR, AddCombi, Carleson); "low" anchors
are unreviewed dumps or corpora shipping thousands of sorries (Seed-Prover, superhuman,
ATLAS). The choice is declared but it is a choice; mid-corpus repos are never used for
calibration, only scored. Sample sizes are small — read AUCs as effect directions, not
significance tests.</p>
<p><b>Elaboration cost caveats.</b> Wall-clock re-elaboration approximates heartbeats;
import-loading is subtracted via per-import-set stub baselines, but toolchain differences
(v4.21–v4.33), caching and machine noise remain; samples are 12 files per repo.</p>
<p><b>Other limitations.</b> Single snapshot (2026-07-18); size confounds (depth,
vocabulary grow with scope); Erdős-90 measured on its <code>src/submission</code> tree;
Equational Theories machine-generates proofs by design; the process metrics the SE
literature ranks highest (churn, review activity) need git/PR history and are the natural
next step.</p>""",
    }


if __name__ == "__main__":
    main()
