import unittest

from lean_reuse.parser import parse_file


class ModuleImportTests(unittest.TestCase):
    def test_module_import_modifiers_preserve_import_graph(self):
        source = """module
import Mathlib.Data.Nat.Basic
public import TorchLean.Tensor.Shape
meta import Lean.Elab.Tactic
public meta import Lean.Meta.Closure
public import all TorchLean.NN.Model

namespace TorchLean
def exampleValue : Nat := 1
end TorchLean
"""
        parsed = parse_file("Example.lean", "Example.lean", source)
        self.assertEqual(parsed.imports, [
            "Mathlib.Data.Nat.Basic", "TorchLean.Tensor.Shape", "Lean.Elab.Tactic",
            "Lean.Meta.Closure", "TorchLean.NN.Model",
        ])
        self.assertEqual([d.name for d in parsed.decls], ["TorchLean.exampleValue"])


if __name__ == "__main__":
    unittest.main()
