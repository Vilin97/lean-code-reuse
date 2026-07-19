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
    "mathlib4": 0, "cslib": 0, "flt": 0, "pfr": 0,
    "addcombi": 0, "pnt": 0, "carleson": 0, "spherepacking": 0,
    "physlib": 1, "equational_theories": 1, "lean-pool": 1,
    "tauceti": 2, "strongpnt": 2,
    "atlas": 3, "seed-prover": 3, "superhuman": 3, "erdos90": 3, "clawristotle": 3,
    "sphere-gauss": 3, "pedigree": 3, "rubik": 3, "gblean": 3,
}
GROUPS = ["Human", "Human + AI mix", "AI, curated", "AI, less curated", "—"]
ORDER = [
    "mathlib4", "flt", "pfr", "addcombi", "carleson", "pnt", "spherepacking",
    "cslib", "physlib", "equational_theories", "lean-pool",
    "tauceti", "strongpnt", "sphere-gauss", "atlas", "erdos90", "clawristotle",
    "seed-prover", "superhuman", "pedigree", "rubik", "gblean",
]

CCDF_KEYS = None  # all repos
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
    ("amortization", lambda r: r["m14"].get("mean_log10_cost")),
    ("elab economy", lambda r: -r["m13"]["secs_per_kloc"] if r["m13"].get("secs_per_kloc") is not None else None),
    ("no trivial statements", lambda r: -r["m15"]["pct_trivial_statements"] if r["m15"].get("pct_trivial_statements") is not None else None),
    ("Mathlib vocabulary breadth", lambda r: r["m4"].get("vocab1k")),
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
        "anchor": None,
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
            "pl_p90": m["proof_economy"]["proof_lines"]["p90"],
            "stmt_med": m["proof_economy"].get("stmt_chars_median"),
            "stmt_lines": m["proof_economy"].get("stmt_lines"),
            "pl_stats": m["proof_economy"]["proof_lines"],
            "rpp": m["proof_economy"]["refs_per_proof"],
        },
        "m9": {
            "whole_ml": m["import_graph"]["pct_files_importing_all_mathlib"],
            "fanin2": m["import_graph"]["pct_files_fan_in_ge2"],
            "file_med": m["import_graph"].get("median_file_loc"),
            "file_stats": m["import_graph"].get("file_loc_stats"),
        },
        "m10": m.get("doc_coverage", {}),
        "m11": m.get("complexity", {}),
        "m12": m.get("trust_base", {}),
        "m13": m.get("elab_cost", {"secs_per_kloc": None}),
        "m14": m.get("amortization", {}),
        "m15": m.get("triviality", {}),
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
    for k in (CCDF_KEYS or [r["key"] for r in repos]):
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

    # ---- metric battery (definitions reused by PCA and composite) ----------
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
        ("M5 · top-1% reuse share", lambda r: r["m5"]["top1"] or 0, False, True),
        ("M6 · max dependency depth", lambda r: r["m6"]["maxd"], True, False),
        ("M12 · axioms per 1k decls", lambda r: r["m12"].get("axioms_per_1k_decls"), False, False),
        ("M14 · amortization: mean log10 inlined cost", lambda r: r["m14"].get("mean_log10_cost"), True, False),
        ("M14 · amortization: p90 log10 inlined cost", lambda r: r["m14"].get("p90_log10_cost"), True, False),
        ("M8 · median proof length (lines)", lambda r: r["m8"]["pl_med"], False, False),
        ("M8 · p90 proof length (lines)", lambda r: r["m8"]["pl_p90"], False, False),
        ("M8 · median statement length (chars)", lambda r: r["m8"].get("stmt_med"), False, False),
        ("M9 · median file length (LOC)", lambda r: r["m9"].get("file_med"), False, False),
        ("M15 · trivial statements", lambda r: r["m15"].get("pct_trivial_statements"), False, True),
        ("M15 · trivial one-liner proofs", lambda r: r["m15"].get("pct_trivial_proofs"), False, True),
    ]
    auc_rows = []

    # ---- composite of mechanical checks (percentile-rank mean) -------------
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

    # ---- PCA over the standardized metric battery --------------------------
    import numpy as _np
    all_metrics = [(lbl, f) for lbl, f, _, _ in metrics]
    # no imputation: keep only metrics computed for EVERY corpus repo
    pca_metrics = [
        (lbl, f) for lbl, f in all_metrics
        if all(f(r) is not None for r in repos)
    ]
    M = _np.array([[f(r) for _, f in pca_metrics] for r in repos], dtype=float)
    for j in range(M.shape[1]):
        col = M[:, j]
        sd = col.std()
        M[:, j] = (col - col.mean()) / (sd if sd > 1e-9 else 1.0)
    U, S, Vt = _np.linalg.svd(M, full_matrices=False)
    pcs = U[:, :3] * S[:3]
    expl = (S**2 / (S**2).sum())[:3]
    # orient PC1 so Mathlib is positive; PC2 so high anchors avg positive
    mi = next(i for i, r in enumerate(repos) if r["key"] == "mathlib4")
    if pcs[mi, 0] < 0:
        pcs[:, 0] *= -1
        Vt[0] *= -1
    si = next(i for i, r in enumerate(repos) if r["key"] == "seed-prover")
    if pcs[si, 1] > 0:
        pcs[:, 1] *= -1
        Vt[1] *= -1
    load1 = sorted(zip([l for l, _ in pca_metrics], Vt[0]), key=lambda t: -abs(t[1]))[:5]
    load2 = sorted(zip([l for l, _ in pca_metrics], Vt[1]), key=lambda t: -abs(t[1]))[:5]
    load3 = sorted(zip([l for l, _ in pca_metrics], Vt[2]), key=lambda t: -abs(t[1]))[:5]
    pca = {
        "points": [
            {"label": r["label"], "group": r["group"], "anchor": r["anchor"],
             "tier": r["tier"], "x": round(float(pcs[i, 0]), 3), "y": round(float(pcs[i, 1]), 3),
             "z": round(float(pcs[i, 2]), 3)}
            for i, r in enumerate(repos)
        ],
        "expl": [round(float(e), 3) for e in expl],
        "load1": [{"m": l, "w": round(float(w), 2)} for l, w in load1],
        "load2": [{"m": l, "w": round(float(w), 2)} for l, w in load2],
        "load3": [{"m": l, "w": round(float(w), 2)} for l, w in load3],
        "included": [l for l, _ in pca_metrics],
    }

    data = {
        "groups": GROUPS,
        "pca": pca,
        "totals": totals,
        "repos": repos,
        "ccdf": ccdf,
        "vocab": vocab,
        "auc": auc_rows,
        "composite": comp,
        "validation": validation,
        "verdicts": VERDICTS,
        "prose": build_prose(byk, validation, {c["key"]: c["score"] for c in comp}),
        "footer": FOOTER,
    }

    tpl = open(os.path.join(os.path.dirname(__file__), "template.html")).read()
    html = tpl.replace("/*__DATA__*/", json.dumps(data))
    with open(args.out, "w") as f:
        f.write(html)
    print(f"wrote {args.out} ({len(html)//1024} KB)")


VERDICTS = [
    {"good": True, "title": "Amortization exponent (M14)",
     "text": "Reuse measured as compression: log₁₀ of the fully-inlined dependency tree. Mathlib averages 10^7.5 (deepest 10^41); unreviewed dumps sit near 10^0.5–0.8, and chain-splitting cannot inflate it, since a chain of length k only reaches cost k."},
    {"good": True, "title": "Cross-directory reuse (M3)",
     "text": "The strongest structural separator: Mathlib routes 62% of reuse edges across top-level directories; every AI-heavy corpus — curated included — sits below 2%. LeanPool's 93 directories with 0.1% cross-dir reuse reflect its pool-of-projects design, not its authorship."},
    {"good": True, "title": "Docstring coverage (M10)",
     "text": "A process signal: Mathlib's linter enforces docstrings on definitions (99.4% coverage) and the habit propagates through reviewed projects; both Gauss-completed corpora sit near 20%. Mirrors the SE finding that process metrics out-predict product metrics."},
    {"good": True, "title": "Hygiene profile (M7/M8/M9)",
     "text": "Sorries, duplicate bodies, wholesale imports, trivial statements: each catches a different failure mode — ATLAS's 2,900 sorries, Seed-Prover's 60% duplication, superhuman's blanket `import Mathlib`, Pedigree's 59 axioms. Jointly with locality they flag every unreviewed corpus in this study."},
    {"good": False, "title": "Raw reuse counts (M1)",
     "text": "Median in-degree separates nothing. Never-reused even inverts — superhuman's bespoke proof towers reuse 97% of their lemmas, exactly once each. Citation volume cannot tell a cathedral from scaffolding; that is what M14 fixes."},
    {"good": False, "title": "Elaboration cost per LOC (M13) — refuted",
     "text": "The heartbeats hypothesis inverts: sorried or shallow content elaborates cheaply (ATLAS: 12 s/kLOC) while TauCeti's 73 s/kLOC reflects genuinely hard mathematics. Cost per line measures effort, not quality — expensive-per-line *and* nothing-reused is the actual smell."},
    {"good": False, "title": "Depth, leverage, statement share",
     "text": "Depth is inheritable via vendored code (LeanPool's 163-deep chain runs through a vendored logic library); Mathlib leverage measures participation, which every serious pipeline has; statement share inverts on hypothesis-heavy restated problem statements."},
]

FOOTER = (
    "Generated 2026-07-19 by the <span class=\"mono\">lean_reuse</span> toolkit — "
    "20 formalization projects, 14 metric families. Textual tier: scoping parser; exact "
    "tier: Lean metaprogram over elaborated environments (getUsedConstants on types and "
    "values, generated auxiliaries contracted). Elaboration cost: timed re-elaboration of "
    "sampled files, import baseline subtracted. Amortization: log-space inlined-cost DP "
    "over the declaration DAG. Repos pinned 2026-07-18/19. Code: lean-code-reuse repo, "
    "one module per metric."
)


def build_prose(byk, validation, comp=None):
    comp = comp or {}
    ml = byk["mathlib4"]
    sp = byk.get("seed-prover")
    sh = byk.get("superhuman")
    tc = byk.get("tauceti")
    lp = byk.get("lean-pool")
    at = byk.get("atlas")
    e9 = byk.get("erdos90")
    cw = byk.get("clawristotle")
    spnt = byk.get("strongpnt")
    sg = byk.get("sphere-gauss") or {}
    spc = byk.get("spherepacking") or {}
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
research projects closely. Counting reuse is not enough; the next sections ask how reuse
<em>compounds</em> (§2), what it costs (§3), and <em>where</em> it lives (§7).</p>""",
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
{lp['m4']['vocab']:,} — the largest — partly reflects the human projects it absorbs: by the
maintainer's own count its 123 projects split 65 human / 38 AI / 20 mixed, so its
human-band scores are expected, not surprising. The discriminating signal in this chart is the vertical axis:
internal dead weight at comparable leverage.</p>
<p class="note">Two hygiene asides found by the extractor itself: LeanPool redeclares
Mathlib names (<code>LieHom.snd</code>), so it cannot be imported alongside full Mathlib;
and Meta ATLAS's own modules collide with each other (<code>jacobianMatrix</code> is defined
in two files), so its 2,653 modules cannot be loaded as one environment at all — it is a
collection of files that compile, not a library. That is why ATLAS carries textual-tier
numbers.</p>""",
        "hygieneProse": f"""
<p>Seed-Prover's {pct(sp['m7']['dup'])} duplicate-body rate and Meta ATLAS's
{at['m8']['nsorry']:,} sorried theorems ({pct(at['m8']['sorry'])}) anchor the low end, and
the slop calibration set behaves as expected — Rubik Cube Group:
{pct(byk['rubik']['m8']['sorry']) if 'rubik' in byk else '—'} sorried theorems; GBLean:
{pct(byk['gblean']['m8']['sorry']) if 'gblean' in byk else '—'}; Pedigree Polytopes proves
P=NP from {byk['pedigree']['m12'].get('n_axioms_declared','—') if 'pedigree' in byk else '—'}
declared axioms (M12 catches what the sorry counter cannot: axiomatizing your way to a
headline). The curated AI projects are clean on both counts (TauCeti:
{pct(tc['m7']['dup'])} duplicates, zero sorries; StrongPNT: {pct(spnt['m7']['dup'])}
duplicates, {pct(spnt['m8']['sorry'])} sorries). The two Sphere Packing rows are compared
directly in §4 and §12.</p>""",
        "discussProse": f"""
<p>The discriminating metrics form a coherent family: <b>compounding reuse</b> (the
amortization exponent), <b>organization</b> (cross-directory and outside-file reuse),
<b>process discipline</b> (docstring coverage, granular imports, sorry hygiene) and
<b>economy</b> (duplication, triviality). The failures are <em>volume</em> metrics — raw
citation counts, depth, Mathlib leverage, statement share, elaboration cost — that a large
or machine-generated corpus satisfies incidentally, mirroring the software-measurement
literature where volume indices predict quality poorly and process signals hold up.</p>
<p><b>The Sphere Packing A/B, and why the composite must be read with suspicion.</b> The
corpus contains the community formalization and Math Inc's Gauss PR against it: same
theorem, different process. The PR tops the composite
({comp.get('sphere-gauss', 0)*100:.0f} vs {comp.get('spherepacking', 0)*100:.0f}) — yet the
community's review of it was scathing, reporting padding such as declarations of type
<code>True</code> and lemmas of the form <code>1 + 1 = 2</code>. We built a triviality
detector (M15) for exactly these; on the branch head we measure (pinned 2026-07-19), it
finds none — either they were cleaned after review or predate this snapshot — and the PR
passes every other mechanical check too. The honest conclusion is not that the PR is
high-quality; it is that <b>a modern AI pipeline can saturate every mechanically checkable
signal while failing expert review</b> on definition quality, statement generality and API
design (§12). The residual quantitative tells are vocabulary poverty per citation
({(sg.get('m4') or {}).get('vocab1k','—')} distinct Mathlib lemmas per 1k refs vs the
community's {(spc.get('m4') or {}).get('vocab1k','—')}) and a heavier proof-length tail.
Treat the composite as a floor-detector: scoring low is meaningful, scoring high is not a
certificate.</p>
<p>The slop calibration set behaves as floors should: Pedigree Polytopes
({comp.get('pedigree',0)*100:.0f}) is exposed by axioms (59 declared) rather than sorries,
GBLean ({comp.get('gblean',0)*100:.0f}) and Rubik ({comp.get('rubik',0)*100:.0f}) by
sorry-rates, Seed-Prover ({comp.get('seed-prover',0)*100:.0f}) by duplication and
isolation. TauCeti and LeanPool (65 human / 38 AI / 20 mixed projects) sit inside the human
band. SciLean and Tao's <i>Analysis</i> remain excluded: their sorry conventions are
deliberate design choices the checks misread.</p>""",
        "amortProse": f"""
<p>This is the graph-theoretic formulation under which reuse <em>does</em> discriminate —
massively. Mathlib's average declaration would cost 10<sup>{ml['m14'].get('mean_log10_cost','?')}</sup>
inlined nodes without sharing (its deepest: 10<sup>{ml['m14'].get('max_log10_cost','?')}</sup>);
Seed-Prover's average is 10<sup>{sp['m14'].get('mean_log10_cost','?')}</sup> — barely above no
sharing at all. Unlike raw in-degree, this cannot be gamed by splitting one proof into a
chain (a chain of length k only reaches cost k); it grows only when declarations are used
<em>by many declarations that are themselves reused</em> — compounding, exactly the Mathlib
design philosophy. Two caveats: the exponent grows with library size (part of the point,
but compare like-sized repos), and it measures each repo's <em>internal</em> economy —
chains through Mathlib are credited to M4, not here.</p>""",
        "validityProse": f"""
<p><b>Tier agreement.</b> Where both tiers exist they correlate at Spearman ρ
{mv.get('spearman_indeg','—')} across Mathlib's {mv.get('n_joined',0):,} joined
declarations (0.76–0.79 on every repo checked); the textual tier under-counts dot-notation
and instance uses but preserves ranking, justifying its use for the unbuildable corpora
(Seed-Prover, superhuman, Erdős-90, Clawristotle).</p>
<p><b>No fitted labels.</b> Nothing here is trained or calibrated against a quality
labeling: the PCA uses only complete-coverage metrics with no imputation, and the composite
is an unweighted mean of percentile ranks. Where we assert a metric "discriminates," the
claim rests on the visible separation in its panel and on the slop set behaving as
expected — judge from the charts.</p>
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
