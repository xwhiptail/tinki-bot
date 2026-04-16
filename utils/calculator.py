import ast
import operator
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

CALCULATION_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def _evaluate_decimal_expression(node):
    if isinstance(node, ast.Expression):
        return _evaluate_decimal_expression(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Decimal(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _evaluate_decimal_expression(node.operand)
        return operand if isinstance(node.op, ast.UAdd) else -operand
    if isinstance(node, ast.BinOp) and type(node.op) in CALCULATION_OPERATORS:
        left = _evaluate_decimal_expression(node.left)
        right = _evaluate_decimal_expression(node.right)
        return CALCULATION_OPERATORS[type(node.op)](left, right)
    raise ValueError("Unsupported expression")


def _format_decimal_result(value: Decimal) -> str:
    normalized = format(value.normalize(), 'f')
    if '.' in normalized:
        integer_part, fractional_part = normalized.split('.', 1)
        fractional_part = fractional_part.rstrip('0')
        if fractional_part:
            return f"{int(integer_part):,}.{fractional_part}"
    return f"{int(Decimal(normalized)):,}"


def maybe_calculate_reply(text: str) -> Optional[str]:
    candidate = text.strip().lower()
    candidate = re.sub(r'^(what(?:\'s| is)|calculate|compute|solve)\s+', '', candidate)
    candidate = candidate.rstrip(' ?!.')
    candidate = re.sub(r'(?<=\d)\s*[x×]\s*(?=\d)', '*', candidate)
    candidate = re.sub(r'(?<=\d)\s*[÷]\s*(?=\d)', '/', candidate)
    if not candidate or not re.fullmatch(r'[\d\s\.\+\-\*\/\(\)]+', candidate):
        return None
    try:
        parsed = ast.parse(candidate, mode='eval')
        result = _evaluate_decimal_expression(parsed)
        return _format_decimal_result(result)
    except (SyntaxError, ValueError, InvalidOperation, ZeroDivisionError):
        return None
