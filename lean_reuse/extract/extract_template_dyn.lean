/-
Dynamic-import variant of the environment-graph extractor.

The static template `import`s the target, which exposes this script's own
syntax to the target's notation (AI libraries in particular define DSLs that
break `s!`/`[i]!`/`++` parsing). Here the script imports only `Lean`; target
modules are loaded at runtime via `importModules`, so their notation cannot
affect parsing. Module list comes from EXTRACT_IMPORTS (comma-separated).

`-- LEVEL_ARG` is replaced by `(level := .private)` on toolchains that have
the olean-level parameter (module-system builds), or nothing on older ones.
-/
import Lean

open Lean

def kindOf : ConstantInfo → String
  | .axiomInfo _  => "axiom"
  | .defnInfo _   => "def"
  | .thmInfo _    => "theorem"
  | .opaqueInfo _ => "opaque"
  | .quotInfo _   => "quot"
  | .inductInfo _ => "inductive"
  | .ctorInfo _   => "ctor"
  | .recInfo _    => "rec"

def isFullMod (fulls : Array String) (m0 : String) : Bool :=
  -- `toString` guillemet-quotes non-identifier name components; strip them so
  -- an unquoted prefix like `LEAN-IMO-Bench` still matches `«LEAN-IMO-Bench».…`.
  let m := (m0.replace "«" "").replace "»" ""
  fulls.isEmpty || fulls.any (fun p => m == p || m.startsWith (p ++ "."))

def depsStr (ids : Std.HashMap Name Nat) (arr : Array Name) : String := Id.run do
  let mut s := ""
  for d in arr do
    match ids.get? d with
    | some k => s := s ++ toString k ++ " "
    | none => pure ()
  return s

unsafe def main : IO Unit := do
  initSearchPath (← findSysroot)
  let out := (← IO.getEnv "EXTRACT_OUT").getD "extract_dump.tsv"
  let fulls : Array String :=
    ((((← IO.getEnv "FULL_PREFIXES").getD "").splitOn ",").filter (· ≠ "")).toArray
  -- Build names via mkStr fold: String.toName validates identifiers on newer
  -- toolchains and maps segments like `Putnam-2025` to .anonymous.
  let importNames : List Name :=
    (((← IO.getEnv "EXTRACT_IMPORTS").getD "").splitOn ",").filter (· ≠ "")
      |>.map (fun s => (s.splitOn ".").foldl .mkStr .anonymous)
  let imports : Array Import := importNames.toArray.map (fun n => { module := n })
  let env ← importModules imports {} (trustLevel := 1024) -- LEVEL_ARG
  let mods := env.header.moduleNames
  let consts := env.constants.toList
  let mut idMap : Std.HashMap Name Nat := ∅
  let mut i := 0
  for (n, _) in consts do
    if !n.hasMacroScopes then
      idMap := idMap.insert n i
      i := i + 1
  let instNames := Meta.instanceExtension.getState env |>.instanceNames
  let h ← IO.FS.Handle.mk out IO.FS.Mode.write
  for m in mods do
    h.putStr ("M\t" ++ toString m ++ "\n")
  let mut j := 0
  for (n, ci) in consts do
    if n.hasMacroScopes then
      continue
    let modStr := match env.getModuleIdxFor? n with
      | some idx => toString (mods.getD idx Name.anonymous)
      | none => "<cur>"
    let full := isFullMod fulls modStr
    let userName := (privateToUserName? n).getD n
    let mut flags := ""
    if instNames.contains n then flags := flags ++ "i"
    if isPrivateName n then flags := flags ++ "p"
    if (env.getProjectionFnInfo? n).isSome then flags := flags ++ "j"
    if flags == "" then flags := "-"
    let vexpr? : Option Expr := match ci with
      | .defnInfo v => some v.value
      | .thmInfo v => some v.value
      | .opaqueInfo v => some v.value
      | _ => none
    let tdeps := if full then depsStr idMap ci.type.getUsedConstants else ""
    let vdeps := if full then
        match vexpr? with
        | some v => depsStr idMap v.getUsedConstants
        | none => ""
      else ""
    h.putStr ("C\t" ++ toString j ++ "\t" ++ toString userName ++ "\t" ++ kindOf ci
      ++ "\t" ++ modStr ++ "\t" ++ flags ++ "\t" ++ tdeps ++ "\t" ++ vdeps ++ "\n")
    j := j + 1
  h.flush
  IO.println ("extracted " ++ toString j ++ " constants -> " ++ out)
