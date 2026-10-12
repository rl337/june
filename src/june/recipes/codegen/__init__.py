"""Incubating ``june.codegen`` recipes: oneshot, refine, and package variants."""

from june.recipes.codegen.completers import (
    CodegenCompleter,
    FixedPackageCompleter,
    FixedScriptCompleter,
    JunesparkCodegenCompleter,
    ScriptedSequenceCompleter,
)
from june.recipes.codegen.graph import (
    ONESHOT_NODE_ORDER,
    PACKAGE_NODE_ORDER,
    REFINE_NODE_ORDER,
    bound_run_for_codegen,
    build_codegen_graph,
    build_package_graph,
    build_refine_graph,
)
from june.recipes.codegen.problem import (
    BAD_RPN_SOLUTION,
    REFERENCE_RPN_SOLUTION,
    REFERENCE_SOLUTION,
    REFERENCE_WORDSTATS_FILES,
    RPN_EVAL,
    SUM_MULTIPLES_OF_3_OR_5,
    WORD_STATS_PKG,
    CodingProblem,
)
from june.recipes.codegen.run import (
    EXPECTED_NODE_ORDER,
    EXPECTED_OFFLINE_BUDGET_SPENT,
    EXPECTED_PACKAGE_BUDGET_SPENT,
    EXPECTED_REFINE_BUDGET_SPENT,
    CodegenRecipeResult,
    expected_node_order,
    run_codegen_recipe,
)
from june.recipes.codegen.runners import make_codegen_runners

__all__ = [
    "BAD_RPN_SOLUTION",
    "CodegenCompleter",
    "CodegenRecipeResult",
    "CodingProblem",
    "EXPECTED_NODE_ORDER",
    "EXPECTED_OFFLINE_BUDGET_SPENT",
    "EXPECTED_PACKAGE_BUDGET_SPENT",
    "EXPECTED_REFINE_BUDGET_SPENT",
    "FixedPackageCompleter",
    "FixedScriptCompleter",
    "JunesparkCodegenCompleter",
    "ONESHOT_NODE_ORDER",
    "PACKAGE_NODE_ORDER",
    "REFERENCE_RPN_SOLUTION",
    "REFERENCE_SOLUTION",
    "REFERENCE_WORDSTATS_FILES",
    "REFINE_NODE_ORDER",
    "RPN_EVAL",
    "SUM_MULTIPLES_OF_3_OR_5",
    "ScriptedSequenceCompleter",
    "WORD_STATS_PKG",
    "bound_run_for_codegen",
    "build_codegen_graph",
    "build_package_graph",
    "build_refine_graph",
    "expected_node_order",
    "make_codegen_runners",
    "run_codegen_recipe",
]
