"""移植自 qwen3_4b/tools/calculator.py，純功能無狀態，原樣搬入。

用 AST 白名單解析數學表達式，不執行任何程式碼，安全性邏輯不變。
"""
import ast
import math
import operator

from ..base import Tool, ToolResult

_OPERATORS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}

_FUNCTIONS = {
    "abs": abs, "round": round, "int": int, "float": float,
    "sqrt": math.sqrt, "log": math.log, "log2": math.log2, "log10": math.log10,
    "exp": math.exp, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "ceil": math.ceil, "floor": math.floor, "factorial": math.factorial,
}

_CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf}


def _eval_node(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, complex)):
            return node.value
        raise ValueError(f"不支援的常數類型：{type(node.value)}")

    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise ValueError(f"未知變數：{node.id}")

    if isinstance(node, ast.BinOp):
        op = _OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError(f"不支援的運算子：{type(node.op).__name__}")
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            raise ZeroDivisionError("除以零")
        return op(left, right)

    if isinstance(node, ast.UnaryOp):
        op = _OPERATORS.get(type(node.op))
        if op is None:
            raise ValueError(f"不支援的一元運算子：{type(node.op).__name__}")
        return op(_eval_node(node.operand))

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("不支援的函式呼叫形式")
        fn = _FUNCTIONS.get(node.func.id)
        if fn is None:
            raise ValueError(f"不支援的函式：{node.func.id}")
        return fn(*[_eval_node(a) for a in node.args])

    raise ValueError(f"不允許的語法節點：{type(node).__name__}")


def _calculate(expression: str) -> str:
    expr = expression.strip()
    if not expr:
        return "請提供要計算的數學表達式"
    try:
        result = _eval_node(ast.parse(expr, mode="eval").body)
        if isinstance(result, float) and result.is_integer():
            return f"{expr} = {int(result)}"
        if isinstance(result, float):
            return f"{expr} = {result:.10g}"
        return f"{expr} = {result}"
    except ZeroDivisionError:
        return "計算錯誤：除以零"
    except ValueError as e:
        return f"不支援的語法：{e}"
    except SyntaxError:
        return f"表達式語法錯誤：{expr}"
    except OverflowError:
        return "計算結果超出數值範圍"
    except Exception as e:
        return f"計算失敗：{e}"


class CalculatorTool(Tool):
    # 安全計算數學表達式，不執行任何程式碼（AST 白名單解析，防止 eval 注入風險）
    name = "calculate"
    description = (
        "安全計算數學表達式。支援加減乘除（+ - * / // %）、次方（**）、"
        "sqrt / log / log10 / sin / cos / tan / ceil / floor / factorial / abs / round，"
        "以及常數 pi、e。"
    )
    parameters = {
        "type": "object",
        "properties": {"expression": {"type": "string", "description": "數學表達式，例如：sqrt(2)、2**10"}},
        "required": ["expression"],
    }

    def run(self, expression: str, **kwargs) -> ToolResult:
        return ToolResult(output=_calculate(expression))
