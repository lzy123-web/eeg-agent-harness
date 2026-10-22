"""Issue #9 intent-alignment evaluation; offline gold never enters runtime prompts."""

from .evaluation import load_suite, run_controlled_injections, run_real_evaluation

__all__ = ("load_suite", "run_controlled_injections", "run_real_evaluation")
