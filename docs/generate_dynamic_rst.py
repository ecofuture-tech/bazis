import ast
import importlib.util
import inspect
from pathlib import Path

from sphinx.ext.autodoc import FunctionDocumenter


def generate_dynamic_fields_rst(srcdir: str):
    dynamic_tests_root = Path(srcdir).parent / "tests" / "test_routes_view" / "dynamic"
    dynamic_fields_rst = Path(srcdir) / "dynamic_fields.rst"

    content = [
        "Dynamic fields",
        "==============",
        "",
        """
``FieldDynamic`` is a declarative builder for computed fields, used through the ``@calc_property`` decorator.

When calling ``FieldDynamic()``, it automatically transforms into one of the ``Field*`` classes:

- ``FieldIsExists`` (boolean indicator for a specified combination of conditions) — if ``alias`` starts with ``has_``.
- ``FieldSubAggr`` (aggregation result) — if ``func`` is specified.
- ``FieldJson`` (list of values for one-to-many and many-to-many relationships) — if ``fields`` are defined.
- ``FieldRelated`` (values for one-to-one and many-to-one relationships) — in all other cases.

``DependsCalc`` is a helper mechanism for passing dependencies.
It creates a Pydantic model from fields specified in ``FieldDynamic``, taking nesting into account.
Used in ``@calc_property`` to pass dependency values to methods.
        """,
        ""
    ]

    for py_file in sorted(dynamic_tests_root.rglob("test_*.py")):
        rel_path = py_file.relative_to(Path(srcdir).parent).with_suffix("")
        module = ".".join(rel_path.parts)

        spec = importlib.util.spec_from_file_location(module, str(py_file))
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            doc = inspect.getdoc(mod)
            if not doc:
                continue
            module_title = doc.strip().splitlines()[0]
        except Exception:
            continue

        content.append("")
        content.append(module_title)
        content.append("-" * len(module_title))
        content.append('\n'.join(doc.strip().splitlines()[2:]))
        content.append("")
        content.append(f".. automodule:: {module}")
        content.append("   :members:")
        content.append("   :member-order: bysource")
        content.append("")

    dynamic_fields_rst.write_text("\n".join(content), encoding="utf-8")


def suppress_function_headers():
    FunctionDocumenter.add_directive_header = lambda self, sig: None

def trim_module_docstring(app, what, name, obj, options, lines):
    if what != "module":
        return

    if not name.startswith("tests.test_routes_view.dynamic"):
        return

    if lines:
        lines[:] = []

def append_info_to_docstring(app, what, name, obj, options, lines):
    if what != "function":
        return

    # process only modules starting with tests.test_routes_view.dynamic
    if not getattr(obj, "__module__", "").startswith("tests.test_routes_view.dynamic"):
        return

    doc = inspect.getdoc(obj)
    lines.clear()

    if doc:
        doc_lines = doc.strip().splitlines()
        if doc_lines:
            title = doc_lines[0].strip()
            lines.append(title)
            lines.append("=" * len(title))
            lines.append("")

            rest_doc = doc_lines[1:]
            if rest_doc:
                lines += rest_doc
                lines.append("")

    for key, value in extract_all_variables_in_order(obj):
        lines.append("")
        if key == "url":
            lines.append("**Endpoint:**")
            lines.append("")
            lines.append(".. code-block:: bash")
            lines.append("")
            lines.append(f"   GET {value}")
        elif key in {"sql_query", "expected_sql_template"}:
            lines.append("**SQL query:**")
            lines.append("")
            lines.append(".. code-block:: sql")
            lines.append("")
            for line in value.splitlines():
                lines.append(f"   {line}")


def extract_all_variables_in_order(func):
    try:
        source = inspect.getsource(func)
        tree = ast.parse(source)
        results = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                for sub in node.body:
                    if isinstance(sub, ast.Assign):
                        for target in sub.targets:
                            if isinstance(target, ast.Name) and target.id in {"url", "sql_query", "expected_sql_template"}:
                                value = sub.value
                                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                                    results.append((target.id, value.value.strip()))
                                elif isinstance(value, ast.JoinedStr):
                                    parts = []
                                    for part in value.values:
                                        if isinstance(part, ast.Constant):
                                            parts.append(part.value)
                                        elif isinstance(part, ast.FormattedValue):
                                            parts.append("{...}")
                                    results.append((target.id, "".join(parts).strip()))
        return results
    except Exception as e:
        print(f"[sphinx][extract_all_variables_in_order] error: {e}")
        return []