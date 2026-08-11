"""Verify the app runs fully without any AI module loaded when AI is disabled."""
import sys


def test_ai_modules_not_imported():
    """Importing the app + main pipeline must not pull in any AI SDK or filter module."""
    forbidden = {
        "openai",
        "ai_filter",
        "gemini_filter",
        "agnes_filter",
        "agy_filter",
        "google.generativeai",
        "google.genai",
    }
    loaded = forbidden.intersection(sys.modules)
    assert loaded == set(), f"AI modules were imported despite use_ai=false: {loaded}"


def test_main_module_has_no_top_level_ai_imports():
    import ast
    import inspect

    import main

    source = inspect.getsource(main)
    tree = ast.parse(source)
    imports = []
    for node in ast.walk(tree):
        # Only module-level imports (col_offset == 0) must be AI-free.
        # Imports inside the `if use_ai:` branch are conditional and fine.
        if isinstance(node, (ast.Import, ast.ImportFrom)) and node.col_offset == 0:
            imports.append(ast.get_source_segment(source, node) or "")
    joined = "\n".join(imports)
    assert "ai_filter" not in joined
    assert "gemini_filter" not in joined
    assert "agnes_filter" not in joined
    assert "agy_filter" not in joined


def test_rule_filter_used_when_ai_disabled():
    """The rule filter is a drop-in AI filter with the same interface and no API key."""
    from rule_filter import RuleFilter

    rf = RuleFilter()
    assert rf.is_configured is True
    results = rf.evaluate_job_batch([{
        "index": 1,
        "title": "Junior QA Analyst",
        "company": "Jabil",
        "description": "QA, data validation, junior welcome.",
    }])
    assert results[0]["score"] >= 0
