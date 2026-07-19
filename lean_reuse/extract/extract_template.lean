/-
Environment-graph extractor (exact tier).

This file is a TEMPLATE: the runner prepends `import <TargetRoots>` after the
`import Lean` line and drops it into the target repo, then runs
    EXTRACT_OUT=dump.tsv FULL_PREFIXES=Self,Prefixes lake env lean extract.lean

Output (TSV):
    M\t<moduleName>                                   -- module table, in order
    C\t<id>\t<userName>\t<kind>\t<module>\t<flags>\t<typeDepIds>\t<valueDepIds>
flags: i=instance, p=private, j=projection, joined without separator ('-' if none).
Dep ids are space-separated and refer to C ids. Value deps are only computed
for constants whose module matches FULL_PREFIXES (empty = all).
-/
import Lean
-- EXTRA_IMPORTS

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

def isFullMod (fulls : Array String) (m : String) : Bool :=
  fulls.isEmpty || fulls.any (fun p => m == p || m.startsWith (p ++ "."))

def depsStr (ids : Std.HashMap Name Nat) (arr : Array Name) : String := Id.run do
  let mut s := ""
  for d in arr do
    match ids.get? d with
    | some k => s := s ++ toString k ++ " "
    | none => pure ()
  return s

set_option maxHeartbeats 0 in
set_option maxRecDepth 10000 in
#eval show Lean.Elab.Command.CommandElabM Unit from do
  let env ← getEnv
  let out := (← IO.getEnv "EXTRACT_OUT").getD "extract_dump.tsv"
  let fulls : Array String :=
    ((((← IO.getEnv "FULL_PREFIXES").getD "").splitOn ",").filter (· ≠ "")).toArray
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
    h.putStr s!"M\t{m}\n"
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
    let tdeps := if full then depsStr idMap ci.type.getUsedConstants else ""
    -- direct field access: `ConstantInfo.value?` hides theorem proofs on
    -- newer toolchains unless allowOpaque, and that param doesn't exist on
    -- older ones — the constructor fields are stable everywhere.
    let vexpr? : Option Expr := match ci with
      | .defnInfo v => some v.value
      | .thmInfo v => some v.value
      | .opaqueInfo v => some v.value
      | _ => none
    let vdeps := if full then
        match vexpr? with
        | some v => depsStr idMap v.getUsedConstants
        | none => ""
      else ""
    h.putStr s!"C\t{j}\t{userName}\t{kindOf ci}\t{modStr}\t{flags}\t{tdeps}\t{vdeps}\n"
    j := j + 1
  h.flush
  IO.println s!"extracted {j} constants -> {out}"
