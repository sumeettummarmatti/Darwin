"""A small, safe expression language for policy packs.

Policy packs carry expressions such as::

    employment_type == 'permanent' and grade in ['L4', 'L5']
    round(basic_monthly * 15 / 26 * gratuity_years)
    notice_days >= lookup('statutory_floor_days', state)

We parse them with Python's ``ast`` module and walk an explicit whitelist of
node types. There is no ``eval``: anything not listed below (attribute access,
imports, lambdas, comprehensions, subscripts on arbitrary objects…) is rejected
when the pack loads, not when it runs.
"""

from __future__ import annotations

import ast
import math
from datetime import date, datetime, timedelta
from typing import Any, Callable, Mapping


class ExpressionError(ValueError):
    """Raised when an expression is malformed or refers to something unknown."""


# ── functions a policy author may call ────────────────────────────────────────


def _to_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ExpressionError(f"not a date: {value!r}")


def _days_between(start: Any, end: Any) -> int:
    return (_to_date(end) - _to_date(start)).days


def _add_days(start: Any, days: Any) -> str:
    return (_to_date(start) + timedelta(days=int(days))).isoformat()


def _completed_months(start: Any, end: Any) -> int:
    a, b = _to_date(start), _to_date(end)
    months = (b.year - a.year) * 12 + (b.month - a.month)
    if b.day < a.day:
        months -= 1
    return max(months, 0)


def _completed_years(start: Any, end: Any) -> int:
    return _completed_months(start, end) // 12


SAFE_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "int": int,
    "len": len,
    "date": lambda v: _to_date(v).isoformat(),
    "days_between": _days_between,
    "add_days": _add_days,
    "completed_months": _completed_months,
    "completed_years": _completed_years,
    "contains": lambda haystack, needle: needle in (haystack or []),
    "lower": lambda text: str(text or "").lower(),
    "get": lambda mapping, key, default=None: (mapping or {}).get(key, default),
    "endswith": lambda text, suffix: str(text or "").endswith(suffix),
    "startswith": lambda text, prefix: str(text or "").startswith(prefix),
    # True if any phrase occurs in the text as whole words (case-insensitive).
    "contains_any": lambda text, phrases: any(
        f" {p.lower()} " in f" {''.join(c if c.isalnum() else ' ' for c in str(text or '').lower())} " for p in phrases
    ),
}

_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
}

_CMP_OPS = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


class Expression:
    """A parsed, validated expression. Parse once at load, evaluate many times."""

    def __init__(self, source: str | int | float | bool):
        self.source = source
        if isinstance(source, (int, float, bool)):
            self._tree: ast.AST = ast.Constant(value=source)
            return
        try:
            self._tree = ast.parse(str(source), mode="eval").body
        except SyntaxError as exc:
            raise ExpressionError(f"cannot parse {source!r}: {exc.msg}") from exc
        self._check(self._tree)

    # Validation happens at load time so a broken pack never reaches runtime.
    def _check(self, node: ast.AST) -> None:
        allowed = (
            ast.Constant, ast.Name, ast.Attribute, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
            ast.IfExp, ast.Call, ast.List, ast.Tuple, ast.Load, ast.And, ast.Or,
            ast.Not, ast.USub, ast.UAdd, ast.keyword,
            *_BIN_OPS.keys(), *_CMP_OPS.keys(),
        )
        for child in ast.walk(node):
            if not isinstance(child, allowed):
                raise ExpressionError(
                    f"{type(child).__name__} is not allowed in policy expressions: {self.source!r}"
                )
            if isinstance(child, ast.Attribute) and child.attr.startswith("_"):
                raise ExpressionError(f"private attribute '{child.attr}' not allowed: {self.source!r}")
            if isinstance(child, ast.Call):
                if not isinstance(child.func, ast.Name):
                    raise ExpressionError(f"only plain function calls allowed: {self.source!r}")

    def names(self) -> set[str]:
        """Every name and dotted path this expression reads, e.g. {'steps', 'steps.notice', 'steps.notice.days'}.

        Used by pack validation (prohibited criteria) and the workflow linter.
        """
        called = {n.func.id for n in ast.walk(self._tree) if isinstance(n, ast.Call)}
        found: set[str] = set()
        for node in ast.walk(self._tree):
            if isinstance(node, ast.Name) and node.id not in called:
                found.add(node.id)
            elif isinstance(node, ast.Attribute):
                parts, cur = [], node
                while isinstance(cur, ast.Attribute):
                    parts.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    parts.append(cur.id)
                    parts.reverse()
                    for i in range(1, len(parts) + 1):
                        found.add(".".join(parts[:i]))
                    found.update(parts)
        return found

    def evaluate(self, facts: Mapping[str, Any], functions: Mapping[str, Callable] | None = None) -> Any:
        funcs = {**SAFE_FUNCTIONS, **(functions or {})}
        try:
            return _Evaluator(facts, funcs).visit(self._tree)
        except ExpressionError:
            raise
        except (TypeError, ValueError, ZeroDivisionError, KeyError, OverflowError) as exc:
            # Bad data fails closed as a policy error, never as a crash.
            raise ExpressionError(f"{self.source!r}: {type(exc).__name__}: {exc}") from exc

    def __repr__(self) -> str:
        return f"Expression({self.source!r})"


class _Evaluator:
    def __init__(self, facts: Mapping[str, Any], functions: Mapping[str, Callable]):
        self.facts = facts
        self.functions = functions

    def visit(self, node: ast.AST) -> Any:
        method = getattr(self, f"visit_{type(node).__name__}", None)
        if method is None:  # pragma: no cover - _check already rejects these
            raise ExpressionError(f"unsupported node {type(node).__name__}")
        return method(node)

    def visit_Constant(self, node: ast.Constant) -> Any:
        return node.value

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in ("true", "True"):
            return True
        if node.id in ("false", "False"):
            return False
        if node.id in ("null", "None"):
            return None
        if node.id not in self.facts:
            raise ExpressionError(f"unknown fact '{node.id}'")
        return self.facts[node.id]

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        # Dotted access is dictionary lookup only — never Python attribute access.
        value = self.visit(node.value)
        if not isinstance(value, Mapping):
            raise ExpressionError(f"cannot read '.{node.attr}' from a non-mapping")
        if node.attr not in value:
            raise ExpressionError(f"unknown field '{node.attr}'")
        return value[node.attr]

    def visit_List(self, node: ast.List) -> list:
        return [self.visit(e) for e in node.elts]

    visit_Tuple = visit_List

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        return _BIN_OPS[type(node.op)](self.visit(node.left), self.visit(node.right))

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        value = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return not value
        if isinstance(node.op, ast.USub):
            return -value
        return +value

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        if isinstance(node.op, ast.And):
            result: Any = True
            for value in node.values:
                result = self.visit(value)
                if not result:
                    return result
            return result
        result = False
        for value in node.values:
            result = self.visit(value)
            if result:
                return result
        return result

    def visit_Compare(self, node: ast.Compare) -> bool:
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            if not _CMP_OPS[type(op)](left, right):
                return False
            left = right
        return True

    def visit_IfExp(self, node: ast.IfExp) -> Any:
        return self.visit(node.body) if self.visit(node.test) else self.visit(node.orelse)

    def visit_Call(self, node: ast.Call) -> Any:
        name = node.func.id  # type: ignore[attr-defined]
        if name not in self.functions:
            raise ExpressionError(f"unknown function '{name}'")
        args = [self.visit(a) for a in node.args]
        kwargs = {k.arg: self.visit(k.value) for k in node.keywords if k.arg}
        return self.functions[name](*args, **kwargs)
