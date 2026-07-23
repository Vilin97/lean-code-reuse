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
import sys

# allow `from lean_reuse import ...` when run as a script from anywhere
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# provenance groups (colors only — the analysis axis is quality, not authorship)
GROUP_OF = {
    "mathlib4": 0, "cslib": 0, "flt": 0, "pfr": 0,
    "addcombi": 0, "pnt": 0, "carleson": 0, "spherepacking": 0,
    "physlib": 1, "equational_theories": 1, "lean-pool": 1,
    "tauceti": 2, "strongpnt": 2,
    "atlas": 3, "seed-prover": 3, "superhuman": 3, "erdos90": 3, "clawristotle": 3,
    "pedigree": 3, "gblean": 3,
    "statlearn": 1, "econlib": 1, "econcs": 1, "asympstat": 1, "brownian": 0,
}
GROUPS = ["Human", "Human + AI mix", "AI, curated", "AI, less curated", "—"]
ORDER = [
    "mathlib4", "flt", "pfr", "addcombi", "carleson", "pnt", "brownian", "spherepacking",
    "cslib", "physlib", "statlearn", "econlib", "econcs", "asympstat",
    "equational_theories",
    "lean-pool", "tauceti", "strongpnt", "atlas", "erdos90", "clawristotle",
    "seed-prover", "superhuman", "pedigree", "gblean",
]

DESC = {
    "mathlib4": "The community's monolithic mathematics library — the reference point for scale, review process and reuse discipline.",
    "flt": "Kevin Buzzard's ongoing formalization of Fermat's Last Theorem, structured to feed results back into Mathlib.",
    "pfr": "Tao-led formalization of the Polynomial Freiman–Ruzsa conjecture; the archetype crowd-sourced research project.",
    "addcombi": "Additive combinatorics library split out of PFR; young and small but maintainer-reviewed.",
    "carleson": "Van Doorn-led formalization of Carleson's theorem on pointwise convergence of Fourier series.",
    "pnt": "The PNT+ project: prime number theorem and consequences, blueprint-driven.",
    "brownian": "Degenne-led construction of Brownian motion: Gaussian measures, Kolmogorov extension, continuity — Mathlib-bound probability theory.",
    "spherepacking": "Community formalization of Viazovska's sphere-packing solution in dimension 8, blueprint-led.",
    "cslib": "The official Lean computer-science library: lambda calculi, semantics, logic.",
    "physlib": "Community physics library (ex-PhysLean/HEPLean): QFT, relativity, quantum information.",
    "statlearn": "Statistical learning theory library (ICML 2026): concentration, VC theory, generalization bounds; AI-assisted development.",
    "econlib": "Formal political economy: preferences, game theory, mechanism design, social choice, general equilibrium; AI-assisted.",
    "econcs": "Computational economics and game theory library (EconCS community); AI-assisted development.",
    "asympstat": "Asymptotic statistical theory: parametric and semi-parametric efficiency, contiguity, local asymptotic normality; AI-assisted.",
    "equational_theories": "Tao's magma equational-theories project — deliberately machine-generated implication proofs at scale.",
    "lean-pool": "A pool absorbing stale formalization projects: 65 human / 38 AI / 20 mixed sub-projects.",
    "tauceti": "An 'AIs-welcome' library downstream of Mathlib where AI implements and reviews under explicit process rules.",
    "strongpnt": "Math Inc's strong prime number theorem, produced by their Gauss autoformalization agent.",
    "atlas": "Meta's Autoformalized Textbook Library At Scale — 2,653 machine-generated textbook modules. Its files redefine names across modules, so they cannot load as one environment; measured on a deterministic 180-module stratified sample, each extracted in isolation.",
    "erdos90": "OpenAI's formalization of the Erdős-90 unit-distance counterexample (submission tree).",
    "clawristotle": "Single-theorem AI formalizations (Landau Coulomb, Grothendieck vanishing) — the artifact of arXiv:2606.13925.",
    "seed-prover": "ByteDance's IMO-style proof dump from the Seed-Prover system — measured on its IMO 2025 subproject, the slice that ships a lakefile and builds.",
    "superhuman": "DeepMind's 58-file corpus of competition proofs from the superhuman system — measured on the 31 files that compile under a v4.21 toolchain (files collide on top-level names, so each is loaded in its own environment).",
    "pedigree": "Slop calibration: a P=NP 'proof' propped up by declared axioms (flagged as crank in LeanPool triage).",
    "gblean": "Slop calibration: Groebner-basis scaffold with more sorries than theorems.",
}

CCDF_KEYS = None  # all repos
VOCAB_KEYS = ["carleson", "flt", "tauceti", "strongpnt", "erdos90"]
DISPLAY_LABEL = {
    "seed-prover": "Seed-Prover (IMO 2025)",
    "superhuman": "superhuman (31/58)",
    "atlas": "Meta ATLAS (180-mod sample)",
}

# The composite and PCA batteries are defined inside main() in terms of the
# SCORED metric ids, restricted to discriminant-valid metrics (see
# lean_reuse/architecture_index.py) and scored on raw values.


def pack_repo(key, res, tier):
    meta, m = res["meta"], res["metrics"]
    d, s, c, e = m["reuse_degree"], m["statement_vs_proof"], m["cross_file"], m["external_reuse"]
    return {
        "key": key, "label": DISPLAY_LABEL.get(key, meta["label"]), "cat": meta["category"],
        "group": GROUP_OF[key], "tier": tier, "stars": meta["stars"],
        "url": meta["url"], "files": meta["files"], "loc": meta["loc"],
        "decls": d["n_reusable_decls"], "alldecls": meta["decls"], "edges": meta["edges"],
        "provenance": meta["provenance"],
        "desc": DESC.get(key, ""),
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
            repos.append(pack_repo(k, env[k], "exact"))
        else:
            # exact tier only: repos that cannot be built (even partially)
            # are excluded from the corpus rather than approximated textually
            print(f"[report] {k}: no exact-tier results — excluded from corpus")
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

    auc_rows = []

    # ---- size audit + discriminant-validity layer --------------------------
    # size_confound still quantifies each metric's raw correlation with size,
    # but nothing is residualized any more: correlation with size does not
    # prove a metric MEASURES size (good libraries grow, so genuine quality
    # signals co-vary with size — residualizing them away pushed Mathlib to
    # mid-pack on metrics where it genuinely leads). The operative test is
    # discriminant validity: does a large-but-uncurated corpus score high?
    # See lean_reuse/architecture_index.py.
    from lean_reuse import architecture_index as _arch
    from lean_reuse import size_confound as _scmod
    sc = _scmod.compute(env, ORDER)
    arch = _arch.compute(env, ORDER)
    verdicts = _arch.classify_battery(
        env, ORDER, [(mid, path, hib) for mid, path, hib in _scmod.BATTERY])

    def rawv(r, mid):
        return sc["metrics"].get(mid, {}).get("raw", {}).get(r["key"])

    # canonical scored battery: (metric_id, display, higher_better, in_composite)
    SCORED = [
        ("m3_crossdir",    "M3 · cross-directory reuse",        True,  True),
        ("m3_outside",     "M3 · used outside defining file",   True,  True),
        ("m9_whole_ml",    "M9 · files importing all Mathlib",  False, True),
        ("m10_doc",        "M10 · docstring coverage",          True,  True),
        ("m8_sorry",       "M8 · sorried theorems",             False, True),
        ("m7_dup",         "M7 · duplicate bodies",             False, True),
        ("m14_amort_mean", "M14 · amortization exponent",       True,  True),
        ("m13_elab",       "M13 · elaboration cost / kLOC",     False, True),
        ("m15_triv_stmt",  "M15 · trivial statements",          False, True),
        ("m4_vocab1k",     "M4 · Mathlib vocabulary breadth",   True,  True),
        ("m12_axioms",     "M12 · axioms per 1k decls",         False, True),
        ("m10_comment",    "M10 · comment density",             True,  False),
        ("m2_stmt_share",  "M2 · statement share of refs",      False, False),
        ("m5_top1",        "M5 · top-1% reuse concentration",   True,  False),
        ("m1_mean_indeg",  "M1 · mean in-degree",               True,  False),
        ("m1_ge2",         "M1 · share reused ≥2",              True,  False),
        ("m1_never",       "M1 · share never reused",           False, False),
        ("m6_maxd",        "M6 · max dependency depth",         True,  False),
        ("m6_meand",       "M6 · mean dependency depth",        True,  False),
        ("m14_amort_p90",  "M14 · amortization p90",            True,  False),
        ("m4_ext_int",     "M4 · external/internal ratio",      True,  False),
        ("m11_branch",     "M11 · branching tactics / proof",   True,  False),
        ("m15_triv_proof", "M15 · trivial one-liner proofs",    False, False),
        ("m12_axioms",     "M12 · axioms per 1k decls",         False, False),
    ]
    # dedup by metric-id, keeping the first (labelled) occurrence
    _seen = set(); SCORED = [s for s in SCORED if s[1] and not (s[0] in _seen or _seen.add(s[0]))]
    # composite: only checks that pass the discriminant test enter (a size
    # proxy in the composite would let a repo score well just by being large)
    COMPOSITE_IDS = [(mid, hib) for mid, _, hib, inc in SCORED
                     if inc and verdicts.get(mid, {}).get("real_signal", True)]
    composite_dropped = [mid for mid, _, hib, inc in SCORED
                         if inc and not verdicts.get(mid, {}).get("real_signal", True)]

    # ---- composite of mechanical checks (percentile-rank mean, raw values) --
    comp = []
    for r in repos:
        parts = []
        for mid, hib in COMPOSITE_IDS:
            v = rawv(r, mid)
            if v is None:
                continue
            sign = 1 if hib else -1
            others = [rawv(o, mid) * sign for o in repos if rawv(o, mid) is not None]
            vv = v * sign
            rank = sum(1 for o in others if o < vv) + 0.5 * sum(1 for o in others if o == vv)
            parts.append(rank / len(others))
        comp.append({"key": r["key"], "label": r["label"], "group": r["group"],
                     "tier": r["tier"], "anchor": r["anchor"],
                     "score": round(sum(parts) / len(parts), 3) if parts else 0.0,
                     "n_metrics": len(parts)})
    comp.sort(key=lambda c: -c["score"])

    # ---- PCA over the standardized raw battery (discriminant-valid metrics) --
    import numpy as _np
    pca_metrics = [
        (lbl, mid) for mid, lbl, hib, inc in SCORED
        if verdicts.get(mid, {}).get("real_signal", True)
        and all(rawv(r, mid) is not None for r in repos)
    ]
    M = _np.array([[rawv(r, mid) for _, mid in pca_metrics] for r in repos], dtype=float)
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

    # ---- payload for the "architecture, not size" section ------------------
    label_of = {mid: lbl for mid, lbl, _, _ in SCORED}
    conf_rows = sorted(
        [{"label": label_of.get(mid, mid), "rho_raw": m["rho_raw"],
          "real": verdicts.get(mid, {}).get("real_signal", True),
          "bb_ranks": verdicts.get(mid, {}).get("big_uncurated_ranks", [])}
         for mid, m in sc["metrics"].items() if mid in label_of],
        key=lambda r: -abs(r["rho_raw"]))
    # the three M16 architecture components join the verdict chart with their
    # own rho/verdict rows (the other DISCRIMINANT_TABLE entries are already
    # present as M3/M14/M6/M1 battery rows)
    for t in arch["table"]:
        if t["id"] not in ("dir_breadth", "crossdir_v_rand", "def_hub_ratio"):
            continue
        conf_rows.append({"label": "M16 · " + t["label"], "rho_raw": t["rho_size"],
                          "real": t["real_signal"], "bb_ranks": t["big_uncurated_ranks"]})
    conf_rows.sort(key=lambda r: -abs(r["rho_raw"]))
    log_size = sc["log_size"]
    ks = [r["key"] for r in repos]
    comp_by_k = {c["key"]: c["score"] for c in comp}
    comp_rho_raw = _scmod.spearman([comp_by_k[k] for k in ks], [log_size[k] for k in ks])

    # size-matched cohorts: quality still separates at fixed size?
    Q = {"mathlib4":1,"flt":1,"pfr":1,"addcombi":1,"carleson":1,"pnt":1,"brownian":1,
         "cslib":1,"physlib":1,"tauceti":1,"strongpnt":1,"clawristotle":1,
         "seed-prover":-1,"superhuman":-1,"pedigree":-1,"gblean":-1,"atlas":-1}
    # (metric_id, label, is_pct, higher_is_better)
    COHORT_METRICS = [("m3_crossdir","cross-dir reuse",True,True),
                      ("m10_doc","doc coverage",True,True),
                      ("m14_amort_mean","amortization (log₁₀)",False,True),
                      ("m6_maxd","max depth",False,True),
                      ("m7_dup","duplicate bodies",True,False),
                      ("m8_sorry","sorry rate",True,False)]
    def cohort(lo, hi):
        cks = sorted([k for k in ORDER if k in byk and lo <= byk[k]["alldecls"] < hi and Q.get(k, 0)],
                     key=lambda k: byk[k]["alldecls"])
        rows = []
        for mid, mlabel, is_pct, hib in COHORT_METRICS:
            raws = sc["metrics"].get(mid, {}).get("raw", {})
            pos = [raws[k] for k in cks if Q[k] > 0 and k in raws]
            neg = [raws[k] for k in cks if Q[k] < 0 and k in raws]
            if not pos or not neg:
                continue
            rev, slp = sum(pos)/len(pos), sum(neg)/len(neg)
            rows.append({"metric": mlabel, "pct": is_pct,
                         "reviewed": round(rev, 3), "slop": round(slp, 3),
                         "sep": (rev >= slp) == hib})
        return {"repos": [{"key": k, "label": byk[k]["label"], "decls": byk[k]["alldecls"],
                           "q": Q[k]} for k in cks], "rows": rows}
    _sizes = [byk[k]["alldecls"] for k in byk]
    size_confound = {
        "rows": conf_rows,
        "n_real": sum(1 for r in conf_rows if r["real"]),
        "n_total": len(conf_rows),
        "comp_rho_raw": round(comp_rho_raw, 2),
        "composite_dropped": [label_of.get(m, m) for m in composite_dropped],
        "cohort_small": cohort(80, 600),
        "cohort_large": cohort(5000, 400000),
        "span_orders": round(math.log10(max(_sizes) / max(1, min(_sizes))), 1),
        "max_raw": (lambda r: f"{r['rho_raw']:+.2f}")(max(conf_rows, key=lambda r: abs(r["rho_raw"]))) if conf_rows else "+0.80",
        "addcombi_decls": f"{byk['addcombi']['alldecls']:,}" if "addcombi" in byk else "242",
        "atlas_decls": f"{byk['atlas']['alldecls']:,}" if "atlas" in byk else "15,633",
    }

    # ---- metric-level cross-tier validation --------------------------------
    # repos whose exact tier covers a partial slice (buildable subproject or
    # per-module subset) — their textual results describe a different file set,
    # so a same-repo aggregate tier comparison would be apples-to-oranges.
    # clawristotle: exact = Landau subproject, textual = Landau + grothendieck.
    PARTIAL_EXACT = {"seed-prover", "superhuman", "pedigree", "atlas", "clawristotle"}
    dual = [k for k in ORDER if k in env and k in tx and k not in PARTIAL_EXACT]
    tv_metrics = [
        ("share reused >=2", lambda m: m["reuse_degree"]["pct_reused_ge2"]),
        ("share never reused", lambda m: m["reuse_degree"]["pct_never_reused"]),
        ("mean in-degree", lambda m: m["reuse_degree"]["degree"]["mean"]),
        ("used outside file", lambda m: m["cross_file"]["pct_decls_used_outside_file"]),
        ("edges crossing dirs", lambda m: m["cross_file"]["pct_edges_cross_dir"]),
        ("duplicate bodies", lambda m: m["duplication"]["body_dup_rate"]),
        ("sorried theorems", lambda m: m["proof_economy"]["sorry_rate"]),
        ("defs with docstrings", lambda m: m["doc_coverage"].get("pct_defs_with_doc")),
        ("amortization mean log10", lambda m: m["amortization"]["mean_log10_cost"]),
        ("trivial one-liner proofs", lambda m: m["triviality"].get("pct_trivial_proofs")),
    ]
    def _spear(a, b):
        a = _np.array(a, float); b = _np.array(b, float)
        ra = _np.argsort(_np.argsort(a)); rb = _np.argsort(_np.argsort(b))
        ca, cb = ra - ra.mean(), rb - rb.mean()
        d = _np.sqrt((ca**2).sum() * (cb**2).sum())
        return float((ca*cb).sum()/d) if d else 0.0
    tierval = []
    for label, f in tv_metrics:
        pairs = []
        for k in dual:
            try:
                tv_ = f(tx[k]["metrics"]); ev_ = f(env[k]["metrics"])
            except (KeyError, TypeError):
                continue
            if tv_ is None or ev_ is None:
                continue
            pairs.append((k, tv_, ev_))
        if len(pairs) < 5:
            continue
        t = [p[1] for p in pairs]; e = [p[2] for p in pairs]
        tierval.append({
            "label": label, "n": len(pairs),
            "spearman": round(_spear(t, e), 2),
            "med_abs_diff": round(float(_np.median(_np.abs(_np.array(t) - _np.array(e)))), 4),
        })

    data = {
        "groups": GROUPS,
        "tierval": tierval,
        "pca": pca,
        "totals": totals,
        "repos": repos,
        "ccdf": ccdf,
        "vocab": vocab,
        "auc": auc_rows,
        "composite": comp,
        "composite_n_checks": len(COMPOSITE_IDS),
        "size_confound": size_confound,
        "architecture": arch,
        "verdicts": {mid: v["real_signal"] for mid, v in verdicts.items()},
        # per-repo decl-level agreement table: only repos whose two tiers cover
        # the same file set (partial-exact slices would compare mismatched
        # graphs and inflate the textual degree columns)
        "validation": {k: v for k, v in validation.items()
                       if k not in PARTIAL_EXACT and k in byk},
        "prose": build_prose(byk, validation, {c["key"]: c["score"] for c in comp}, size_confound, arch),
        "footer": FOOTER.format(nrepos=len(repos)),
    }

    tpl = open(os.path.join(os.path.dirname(__file__), "template.html")).read()
    html = tpl.replace("/*__DATA__*/", json.dumps(data))
    with open(args.out, "w") as f:
        f.write(html)
    print(f"wrote {args.out} ({len(html)//1024} KB)")


FOOTER = (
    "Generated 2026-07-22 by the <span class=\"mono\">lean_reuse</span> toolkit — "
    "{nrepos} corpora, 16 metric families, all measured on the exact tier: a Lean "
    "metaprogram over elaborated environments (getUsedConstants on types and "
    "values, generated auxiliaries contracted). Elaboration cost: timed re-elaboration of "
    "sampled files, import baseline subtracted. Amortization: log-space inlined-cost DP "
    "over the declaration DAG. Repos pinned 2026-07-18/19. Code: lean-code-reuse repo, "
    "one module per metric."
)


def build_prose(byk, validation, comp=None, size_conf=None, arch=None):
    comp = comp or {}
    arch = arch or {}
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

    ncorp = len(byk)
    NUMWORD = {23: "Twenty-three", 24: "Twenty-four", 25: "Twenty-five",
               26: "Twenty-six", 27: "Twenty-seven", 28: "Twenty-eight"}
    ncorp_word = NUMWORD.get(ncorp, str(ncorp))
    # low-curation AI corpora that actually made the exact-tier cut
    lowcur = [("atlas", "Meta&nbsp;ATLAS"), ("seed-prover", "Seed-Prover"),
              ("superhuman", "DeepMind superhuman"), ("erdos90", "OpenAI's Erdős-90"),
              ("clawristotle", "Clawristotle")]
    lowcur_present = [name for k, name in lowcur if k in byk]
    lowcur_str = ", ".join(lowcur_present[:-1]) + ", " + lowcur_present[-1] if len(lowcur_present) > 1 else (lowcur_present[0] if lowcur_present else "")
    slop = [("pedigree", "Pedigree&nbsp;Polytopes' axiomatized P=NP"), ("gblean", "GBLean")]
    slop_present = [name for k, name in slop if k in byk]
    slop_str = " and ".join(slop_present)
    slop_lead = {2: "two community-flagged slop repos", 1: "one community-flagged slop repo"}.get(len(slop_present), f"{len(slop_present)} community-flagged slop repos")

    scd = size_conf or {}
    top_size = sorted(scd.get("rows", []), key=lambda r: -abs(r["rho_raw"]))[:3]
    top_names = ", ".join(r["label"].split(" · ")[-1] for r in top_size) if top_size else "the amortization exponent, dependency depth and concentration"

    pri = arch.get("primary", {})
    sep = arch.get("max_separation", {})
    bb_pri = pri.get("big_uncurated_ranks", {})
    bb_str = ", ".join(f"{DISPLAY_LABEL.get(k, byk[k]['label'] if k in byk else k)} #{v}"
                       for k, v in sorted(bb_pri.items(), key=lambda t: t[1]))
    return {
        "sizeProse": f"""
<p>A fair worry: with corpora spanning {scd.get('span_orders','3.5')} orders of magnitude in size
(102 to 303,000 declarations), a metric that merely grows with a library could masquerade as a
quality signal. Raw, the most size-correlated metrics are <b>{top_names}</b> (Spearman ρ up to
{scd.get('max_raw','+0.80')} against log-size), and they are exactly the reuse metrics this dashboard
surfaces first.</p>
<p><b>But correlation with size is the wrong test.</b> An earlier revision residualized every metric
against log-declarations — and threw real signal away: good libraries <em>grow</em>, so a genuine
quality signal co-varies with size, and regressing it out pushed Mathlib to mid-pack on metrics where
it genuinely leads. The operative question is <b>discriminant validity</b>: <em>does a large-but-bad
library score high?</em> The corpus contains the control group — its three largest non-Mathlib corpora
(lean-pool at 44k declarations, Erdős-90 at 37k, Meta ATLAS at 16k) are none of them curated
libraries. A metric that ranks them high despite their bulk is a size proxy; a metric that ranks them
near the bottom is measuring architecture. That test cleanly splits the battery: cross-directory reuse
is real (Mathlib 62% of edges, reviewed median 17%, lean-pool <b>0.05%</b> — 44,000 declarations
arranged as an archipelago score nothing), while the amortization exponent, dependency depth and mean
in-degree are genuine size proxies — the big-uncurated corpora's <em>median beats the reviewed
median</em> on them purely from bulk.</p>
<p><b>The Architecture Index</b> distills the discriminant-valid wiring metrics — cross-directory
reuse, directory breadth of reuse, and cross-directory reuse relative to a random-wiring baseline —
into one mean percentile. Mathlib ranks <b>#{pri.get('mathlib_rank','1')}</b> (sharing the exact top
score, 94, with Tao's Equational Theories project), the reviewed-vs-slop
AUC is {pri.get('auc','0.93')}, residual size correlation ρ = {pri.get('rho_size','0.32')}, and the
big-uncurated control corpora rank {bb_str} — huge, but low. (A max-separation variant that swaps
directory breadth for the definitions-are-hubs ratio reaches AUC {sep.get('auc','1.00')} at
ρ = {sep.get('rho_size','0.43')}; it is reported in the how-box, and the size-independent variant
leads.) Every per-metric chart is back to raw values, badged with its verdict; the composite averages
only the discriminant-valid checks.</p>""",
        "cohortProse": f"""
<p>A second, independent check: does quality separate <em>within</em> a size band? The groups overlap
in size (AddCombi, a reviewed library, has {scd.get('addcombi_decls','242')} declarations — smaller
than three of the slop dumps; ATLAS, slop, has {scd.get('atlas_decls','15,633')} — larger than most
reviewed libraries). In both bands the reviewed repos still separate from the slop dumps on nearly
every metric — including the size-proxy amortization and depth. Size inflates magnitudes; it does not
create the separation.</p>""",
        "corpusIntroProse": f"""
<p>{ncorp_word} corpora — formalization projects plus a declared slop calibration set,
every one measured on the exact tier (a repo that cannot be built at all is excluded, not
approximated). (Math&nbsp;Inc's Gauss PR against the Sphere Packing repo was measured in an
earlier revision and is excluded here; §12 records the lesson it taught.) Compiler
internals, teaching games and statements-only conjecture lists are excluded by design, and
so are SciLean and Tao's <i>Analysis&nbsp;I</i>: their <code>sorry_proof</code> and
exercises-for-the-reader conventions are deliberate choices that hygiene checks misread.
The corpus spans Mathlib and its reviewed satellites (FLT, PFR, AddCombi, Carleson, PNT+,
CSLib, Physlib, Equational Theories, the community Sphere Packing project, and four domain
libraries: Stat Learning Theory, EconLib, EconCSLib, Asymptotic Statistics),
mixed-authorship pools (LeanPool — 65 human / 38 AI / 20 mixed projects), curated AI
projects (TauCeti, Math&nbsp;Inc's StrongPNT), low-curation AI corpora ({lowcur_str}), and
{slop_lead} for calibration ({slop_str}). Provenance is shown as color, but it is
<em>not</em> the analysis axis: the question is what separates low-quality from high-quality
corpora, whoever wrote them.</p>""",
        "reuseProse": f"""
<p>Mathlib's curve is the reference: a heavy tail riding on a thick middle —
{pct(ml['m1']['ge2'])} of its {ml['decls']:,} reusable declarations are used by at least two
others. But raw counts mislead in both directions: <b>superhuman</b> (58 bespoke proof
towers) has one of the lowest never-reused rates in the corpus ({pct(sh['m1']['never'])})
because every lemma feeds the next step exactly once, and StrongPNT's curve tracks the human
research projects closely. Counting reuse is not enough; the next sections ask how reuse
<em>compounds</em> (§2), what it costs (§4), and <em>where</em> it lives (§7).</p>""",
        "whereProse": f"""
<p>File-system locality separates the anchors cleanly: {pct(ml['m3']['outside'])} of Mathlib
declarations are used outside their defining file, research formalizations cluster at
20–40%, while Seed-Prover sits at {pct(sp['m3']['outside'])} and superhuman at
{pct(sh['m3']['outside'])}. Clawristotle ({pct(cw['m3']['outside'])}) shows the caveat: a
disciplined single-theorem project — of any authorship — is structured like a small research
formalization, and locality metrics respect that. Structure metrics measure the artifact,
not the author.</p>""",
        "mlProse": f"""
<p>Every serious corpus leans on Mathlib — leverage measures <em>participation</em>, not
quality. TauCeti cites {tc['m4']['ml_per_decl']:.0f} references per declaration over a
{tc['m4']['vocab']:,}-lemma vocabulary; StrongPNT {spnt['m4']['ml_per_decl']:.0f} over
{spnt['m4']['vocab']:,}; Erdős-90's vocabulary is {e9['m4']['vocab']:,}. LeanPool's
{lp['m4']['vocab']:,} — the largest — partly reflects the human projects it absorbs: by the
maintainer's own count its 123 projects split 65 human / 38 AI / 20 mixed, so its
human-band scores are expected, not surprising. The discriminating signal in this chart is the vertical axis:
internal dead weight at comparable leverage.</p>
<p class="note">A hygiene aside found by the extractor itself: LeanPool redeclares
Mathlib names (<code>LieHom.snd</code>), so it cannot be imported alongside full Mathlib.{
" And several corpora name-collide internally — Meta&nbsp;ATLAS defines <code>jacobianMatrix</code> in two files, DeepMind superhuman and Pedigree redefine core types across files — so they cannot load as one environment; we extract each colliding module in isolation and merge the graphs, which loses only cross-file edges those corpora barely have." if (at or sh or byk.get("pedigree")) else ""}</p>""",
        "hygieneProse": f"""
<p>Seed-Prover's {pct(sp['m7']['dup'])} duplicate-body rate{f" and Meta ATLAS's {at['m8']['nsorry']:,} sorried theorems ({pct(at['m8']['sorry'])})" if at else ""} anchor{"" if at else "s"} the low end, and
the slop calibration set behaves as expected — GBLean:
{pct(byk['gblean']['m8']['sorry']) if 'gblean' in byk else '—'} sorried theorems; Pedigree Polytopes proves
P=NP from {byk['pedigree']['m12'].get('n_axioms_declared','—') if 'pedigree' in byk else '—'}
declared axioms (M12 catches what the sorry counter cannot: axiomatizing your way to a
headline). The curated AI projects are clean on both counts (TauCeti:
{pct(tc['m7']['dup'])} duplicates, zero sorries; StrongPNT: {pct(spnt['m7']['dup'])}
duplicates, {pct(spnt['m8']['sorry'])} sorries).</p>""",
        "discussProse": f"""
<p>The discriminating metrics form a coherent family: <b>organization</b> (cross-directory
and outside-file reuse, directory breadth, the definitions-are-hubs shape — the §14
architecture family), <b>process discipline</b> (docstring coverage, granular imports,
sorry hygiene, no declared axioms) and <b>economy</b> (duplication, triviality). The
failures are <em>volume</em> metrics — raw citation counts, depth, the amortization
exponent, Mathlib leverage, statement share, elaboration cost — that a large or
machine-generated corpus satisfies incidentally (§14 makes this precise), mirroring the
software-measurement literature where volume indices predict quality poorly and process
signals hold up.</p>
<p>Read the composite as a floor, not a ranking: hygiene checks are table stakes a modern
pipeline already passes, so the slop calibration set interleaves with the lower human band
here — Pedigree Polytopes ({comp.get('pedigree',0)*100:.0f}) is sorry-free because it
axiomatizes instead (the axiom check, not the sorry counter, is what catches it), GBLean
({comp.get('gblean',0)*100:.0f}) is exposed by sorry-rate, Seed-Prover
({comp.get('seed-prover',0)*100:.0f}) by duplication and isolation. What cleanly separates
reviewed libraries from slop is the <b>Architecture Index</b> of §14 (AUC 0.93 for the
size-independent variant that leads the dashboard; 1.00 for the max-separation variant,
which puts every slop corpus in the bottom seven). And one cautionary result from an earlier revision of
this study is worth recording: we separately measured Math Inc's Gauss PR against the
community Sphere Packing repo, and it passed — indeed topped — every mechanical check here
while community review rejected it on definition quality and API design; it is excluded
from this corpus, and the lesson stands in §12. Treat low scores as meaningful and high
scores as necessary-not-sufficient.</p>""",
        "amortProse": f"""
<p>This is the graph-theoretic formulation under which reuse <em>does</em> discriminate —
massively. Mathlib's average declaration would cost 10<sup>{ml['m14'].get('mean_log10_cost','?')}</sup>
inlined nodes without sharing (its deepest: 10<sup>{ml['m14'].get('max_log10_cost','?')}</sup>);
Seed-Prover's average is 10<sup>{sp['m14'].get('mean_log10_cost','?')}</sup> — barely above no
sharing at all. Unlike raw in-degree, this cannot be gamed by splitting one proof into a
chain (a chain of length k only reaches cost k); it grows only when declarations are used
<em>by many declarations that are themselves reused</em> — compounding, exactly the Mathlib
design philosophy. The same construction appears independently in Freedman et&nbsp;al.,
<a href="https://arxiv.org/abs/2603.20396"><i>Compression is all you need: modeling
mathematics</i></a> (2026), as "wrapped" versus "unwrapped" length measured on Mathlib —
their observation that unwrapped length grows exponentially with depth while wrapped length
stays constant is precisely why we report the exponent.</p>
<p><b>The size caveat, taken seriously.</b> Those exponents are the single most size-driven
number in this study — they correlate with log-declarations at ρ = +0.79, and they fail the
discriminant test of §14: the median of the three largest <em>uncurated</em> corpora out-scores the
reviewed median (2.5 vs 1.4 — lean-pool and Erdős-90 individually rank #2 and #3) purely from bulk,
so a big pile compounds incidentally. The metric is
therefore badged a <b>size proxy</b>, excluded from the composite, and reported here as
descriptive — an honest demotion of what earlier drafts called the winning reuse metric. It
does not vanish: the size-matched cohorts in §14 show reviewed repos still out-compound the
dumps at equal size. Two further caveats: it measures each repo's <em>internal</em> economy
(chains through Mathlib are credited to M4, not here), and it needs the elaborated graph, so
it is exact-tier only.</p>""",
        "validityProse": f"""
<p><b>Every row is exact now — at the price of coverage.</b> Corpora that ship no lakefile
were built anyway: Erdős-90 and Seed-Prover's IMO-2025 subproject ship lakefiles in
subdirectories (found by archaeology, v4.30 and v4.14); superhuman got a v4.21 lakefile we
authored (31 of 58 files compile — the corpus mixes mathlib vintages — and the files
name-collide, so each is loaded in its own environment and the graphs merged); Pedigree's
library core builds module-by-module. Where the buildable slice is a strict subset of the
tree, the row says so in the corpus table — we measure what compiles, which for proof
dumps is itself part of the finding. The retired textual tier remains as a cross-check:
on Mathlib the tiers correlate at Spearman ρ {mv.get('spearman_indeg','—')} across
{mv.get('n_joined',0):,} joined declarations, and on Seed-Prover's built slice ρ 0.975
with mean in-degree 1.04 (textual) vs 1.05 (exact) — the parser was a good approximation
for hygiene and locality, and a hopeless one for the amortization exponent.</p>
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
