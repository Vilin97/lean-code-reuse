"""The seven corpora of the compression study, scoped as in RemyDegenne/lean-quality-indicators
(libraries.toml + the OpenAI Math and CFSG run locks), plus AxiomMath/Stacks.

Each corpus is a list of sources (checkout dir, include prefixes, fnmatch excludes where '*'
crosses '/'). Files are listed in path order; a multi-repo corpus (Formal Frontier) prefixes
paths with the repository name, exactly like the upstream compression.py.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path

DEFAULT_EXCLUDE = ["*/Certificates/*"]   # machine-generated numerical certificates

FORMAL_FRONTIER = [
    "adic-modules:AdicModules", "algebraic-direct-limits:AlgebraicDirectLimits",
    "algebraic-groups:AlgebraicGroups", "coherent-modules:CoherentModules",
    "complex-analysis:ComplexAnalysis", "continuous-group-cohomology:ContinuousGroupCohomology",
    "dedekind-ideal-arithmetic:DedekindIdealArithmetic", "finite-etale-algebras:FiniteEtaleAlgebras",
    "finite-group-tate-cohomology:FiniteGroupTateCohomology", "formal-power-series:FormalPowerSeries",
    "fundamental-groupoids:FundamentalGroupoids", "general-linear-groups:GeneralLinearGroups",
    "graded-rings:GradedRings", "group-rings:GroupRings", "group-theory:GroupTheory",
    "homological-algebra:HomologicalAlgebra", "ideal-completion:IdealCompletion",
    "integral-closure:IntegralClosure", "iwasawa-modules:IwasawaModules",
    "minimal-primes:MinimalPrimes", "morphism-properties:MorphismProperties",
    "multivariate-polynomials:MultivariatePolynomials", "norm-forms:NormForms",
    "polynomial-root-stability:PolynomialRootStability", "profinite-groups:ProfiniteGroups",
    "projective-modules:ProjectiveModules", "projective-space:ProjectiveSpace",
    "quadratic-algebras:QuadraticAlgebras", "restricted-product-duality:RestrictedProductDuality",
    "ringed-spaces:RingedSpaces", "scheme-properties:SchemeProperties",
    "sequence-growth:SequenceGrowth", "sheaf-cohomology:SheafCohomology",
    "simplicial-objects:SimplicialObjects", "simplicial-rings:SimplicialRings",
    "smooth-regularity:SmoothRegularity", "spectral-stone-duality:SpectralStoneDuality",
    "sphere-topology:SphereTopology", "stable-range:StableRange",
    "supernatural-numbers:SupernaturalNumbers", "toric-ideals:ToricIdeals",
    "valuation-integers:ValuationIntegers", "vector-bundles:VectorBundles",
]

CORPORA = {
    "mathlib": dict(name="Mathlib", sources=[dict(
        dir="mathlib", include=["Mathlib/"],
        exclude=["Mathlib/Tactic/*", "Mathlib/Util/*", "Mathlib/Lean/*", "Mathlib/Testing/*",
                 "Mathlib/Deprecated/*"])]),
    "tauceti": dict(name="Tau Ceti", sources=[dict(dir="tauceti", include=["TauCeti/"])]),
    "lean-pool": dict(name="Lean Pool", sources=[dict(dir="lean-pool", include=["LeanPool/"])]),
    "formal-frontier": dict(name="Formal Frontier", sources=[
        dict(dir=f"formal-frontier/{s.split(':')[0]}", include=[s.split(':')[1] + "/"])
        for s in FORMAL_FRONTIER]),
    "openai-math": dict(name="OpenAI Math", sources=[dict(dir="openai-math", include=["lean/OAI/"])]),
    "cfsg": dict(name="CFSG (AxiomMath)", sources=[dict(dir="cfsg", include=["CFSG/"])]),
    # AxiomMath/Stacks ships two tiers: StacksCore (human-reviewed, brought to Mathlib
    # standards) and StacksFrontier (written by AI agents); measured as separate rows.
    "stacks-core": dict(name="Stacks Core (reviewed)",
                        sources=[dict(dir="stacks", include=["StacksCore/"])]),
    "stacks-frontier": dict(name="Stacks Frontier (AI)",
                            sources=[dict(dir="stacks", include=["StacksFrontier/"])]),
}
ORDER = list(CORPORA)


def list_files(root: Path, include: list[str], exclude: list[str]) -> list[str]:
    out = []
    for inc in include:
        for p in (root / inc).rglob("*.lean"):
            rel = p.relative_to(root).as_posix()
            if not any(fnmatch.fnmatch(rel, g) for g in exclude):
                out.append(rel)
    return sorted(set(out))


def files_of(corpus_id: str, base: Path) -> list[tuple[str, Path]]:
    srcs = CORPORA[corpus_id]["sources"]
    out = []
    for s in srcs:
        root = base / s["dir"]
        prefix = s["dir"].rsplit("/", 1)[-1] + "/" if len(srcs) > 1 else ""
        out += [(prefix + rel, root / rel)
                for rel in list_files(root, s["include"], DEFAULT_EXCLUDE + s.get("exclude", []))]
    return sorted(out)
