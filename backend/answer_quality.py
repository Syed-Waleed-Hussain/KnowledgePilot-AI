"""Small deterministic cleanup helpers for generated study answers."""

import json
import ast
import math
import operator
import re
from typing import Any


def normalize_citations(answer: str, source_count: int) -> str:
    """Keep only numeric citation markers that map to the current source list."""
    text = re.sub(r"【\s*(\d+)\s*】|〔\s*(\d+)\s*〕", lambda m: f"[{m.group(1) or m.group(2)}]", answer)
    text = re.sub(
        r"\[(?:source|ref(?:erence)?)\s*(\d+)\]",
        lambda m: f"[{m.group(1)}]",
        text,
        flags=re.IGNORECASE,
    )

    def keep_valid(match: re.Match[str]) -> str:
        index = int(match.group(1))
        return match.group(0) if 1 <= index <= source_count else ""

    return re.sub(r"\[(\d+)\]", keep_valid, text)


def _is_mcq_request(question: str) -> bool:
    return bool(re.search(r"\b(mcq|mcqs|multiple[- ]choice|quiz|quizzes)\b", question, re.I))


def _inline_options_to_lines(text: str) -> str:
    # Split compressed answers such as "A) one B) two C) three D) four".
    return re.sub(
        r"\s+(?=([A-D])\s*[).:]\s+)",
        "\n",
        text,
        flags=re.IGNORECASE,
    )


def _safe_arithmetic(expression: str) -> float | None:
    """Evaluate a short arithmetic expression without Python eval()."""
    operators: dict[type[ast.operator], Any] = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }

    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 8:
                raise ValueError("exponent outside safe limit")
            result = float(operators[type(node.op)](left, right))
            if not math.isfinite(result) or abs(result) > 1e12:
                raise ValueError("result outside safe limit")
            return result
        raise ValueError("unsupported arithmetic")

    try:
        parsed = ast.parse(expression.replace("×", "*").replace("÷", "/"), mode="eval")
        return visit(parsed)
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None


def _check_arithmetic(question_text: str, options: dict[str, str]) -> tuple[str | None, str | None]:
    expressions = re.findall(
        r"(?<!\w)([+-]?\d+(?:\.\d+)?(?:\s*[+\-*/×÷]\s*[+-]?\d+(?:\.\d+)?)+)(?!\w)",
        question_text,
    )
    if len(expressions) != 1:
        return None, None
    expression = expressions[0]
    value = _safe_arithmetic(expression)
    if value is None:
        return None, None
    matches: list[str] = []
    for letter, option in options.items():
        number = re.match(r"^\s*([+-]?\d+(?:\.\d+)?)\s*(?:[A-Za-z%]+)?\s*$", option)
        if number and math.isclose(float(number.group(1)), value, rel_tol=1e-9, abs_tol=1e-9):
            matches.append(letter)
    shown_value = str(int(value)) if value.is_integer() else str(value)
    if len(matches) == 1:
        return matches[0], f"Calculation check: {expression.strip()} = {shown_value}, so option {matches[0]} is correct."
    if not matches:
        return "", f"Calculation check: {expression.strip()} = {shown_value}, but none of the listed options matches."
    return "", f"Calculation check: {expression.strip()} = {shown_value}, but options {', '.join(matches)} duplicate the result."


def format_mcq_answer(question: str, answer: str) -> str:
    """Normalize model-written MCQs into readable Markdown without inventing content."""
    if not _is_mcq_request(question):
        return answer
    text = (answer.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", " ")
            .replace('\\"', '"').replace("\\u3010", "【").replace("\\u3011", "】")
            .replace("\\u3014", "〔").replace("\\u3015", "〕"))
    text = re.sub(r"\*\*(Correct Answer|Answer|Explanation|Source):\*\*", r"\n\1:", text, flags=re.I)
    text = re.sub(r"\*\*([A-D])\.\*\*", r"\1.", text)
    text = text.replace("**", "")
    text = _inline_options_to_lines(text.replace("\r\n", "\n").replace("\r", "\n"))
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    question_pattern = re.compile(r"^(?:#{1,6}\s*)?(?:\*\*)?(?:question|q)\s*(\d+)\s*[:.)-]?\s*(.*?)\*{0,2}$", re.I)
    numbered_pattern = re.compile(r"^(\d+)[.)]\s+(.+)$")
    option_pattern = re.compile(r"^(?:[-*]\s*)?([A-D])[).:\-]\s*(.*)$", re.I)
    answer_pattern = re.compile(r"^(?:correct\s+)?(?:answer|correct option)\s*[:\-]\s*(.*)$", re.I)
    explanation_pattern = re.compile(r"^(?:short\s+)?explanation\s*[:\-]\s*(.*)$", re.I)

    blocks: list[list[str]] = []
    preface: list[str] = []
    for line in lines:
        is_heading = bool(question_pattern.match(line)) or bool(numbered_pattern.match(line) and not option_pattern.match(line))
        if is_heading:
            blocks.append([line])
        elif blocks:
            blocks[-1].append(line)
        else:
            preface.append(line)
    if not blocks:
        blocks = [lines]

    rendered = list(preface)
    for index, block in enumerate(blocks, start=1):
        q_match = question_pattern.match(block[0]) if block else None
        n_match = numbered_pattern.match(block[0]) if block else None
        question_label = int(q_match.group(1)) if q_match else (int(n_match.group(1)) if n_match else index)
        question_parts = [q_match.group(2)] if q_match and q_match.group(2) else []
        if n_match:
            question_parts.append(n_match.group(2))
        options: dict[str, str] = {}
        answer_text = ""
        explanation = ""
        for line in block[1:] if (q_match or n_match) else block:
            option = option_pattern.match(line)
            answer_match = answer_pattern.match(line)
            explanation_match = explanation_pattern.match(line)
            if option:
                options[option.group(1).upper()] = option.group(2).strip()
            elif answer_match:
                candidate = answer_match.group(1).strip()
                if candidate != "Not provided by the model.":
                    answer_text = candidate
            elif explanation_match:
                candidate = explanation_match.group(1).strip()
                if candidate != "Not provided by the model.":
                    explanation = candidate
            else:
                question_parts.append(line)

        title = " ".join(question_parts).strip() or "Question text not provided by the model."
        rendered.extend([f"### Question {question_label}", title])
        for letter in "ABCD":
            rendered.append(f"- **{letter}.** {options.get(letter, '[Option not provided by the model]')}")

        answer_letter = ""
        answer_start = re.match(r"^\s*([A-D])(?:[).:\s]|$)", answer_text, re.I)
        if answer_start:
            answer_letter = answer_start.group(1).upper()
        checked_letter, math_note = _check_arithmetic(title, options)
        if checked_letter is not None:
            answer_letter = checked_letter
            citation_tokens = re.findall(r"【\s*\d+\s*】|〔\s*\d+\s*〕|\[(?:source\s*)?\d+\]", explanation, re.I)
            explanation = " ".join(part for part in (math_note, *citation_tokens) if part)
        answer_display = answer_letter if answer_letter else (answer_text or "Not provided by the model.")
        if answer_letter and answer_text:
            answer_display = f"{answer_letter} — {answer_text[answer_start.end():].strip()}" if answer_start and answer_text[answer_start.end():].strip() else answer_letter
        rendered.append(f"**Correct Answer:** {answer_display}")
        rendered.append(f"**Explanation:** {explanation or 'Not provided by the model.'}")
        rendered.append("")
    return "\n".join(rendered).strip()


def prepare_answer(question: str, answer: str, source_count: int) -> str:
    """Apply safe, bounded formatting and citation normalization."""
    answer = format_mcq_answer(question, answer)
    return normalize_citations(answer, source_count)

def render_quiz(data: dict, source_count: int, expected_count: int = 5) -> str:
    """Validate structured model output before displaying any questions."""
    questions = data.get('questions')
    if not isinstance(questions, list) or len(questions) != expected_count:
        raise ValueError(f'Quiz must contain exactly {expected_count} questions.')
    seen = set()
    blocks = []
    for index, item in enumerate(questions, 1):
        title = item.get('question', '').strip()
        options = item.get('options', {})
        answer = item.get('correct_answer')
        explanation = item.get('explanation', '').strip()
        sources = item.get('source_ids', [])
        if not title or title.casefold() in seen:
            raise ValueError('Quiz contains an empty or duplicate question.')
        seen.add(title.casefold())
        if set(options) != set('ABCD') or any(not isinstance(v, str) or not v.strip() for v in options.values()):
            raise ValueError('Each question requires four options A-D.')
        if len({v.strip().casefold() for v in options.values()}) != 4:
            raise ValueError('Quiz options must be distinct.')
        if not isinstance(answer, str) or answer not in 'ABCD' or len(answer) != 1 or not explanation:
            raise ValueError('Each question requires a valid answer and explanation.')
        if not isinstance(sources, list) or any(type(n) is not int or not 1 <= n <= source_count for n in sources):
            raise ValueError('Quiz references an unsupported source.')
        checked, note = _check_arithmetic(title, options)
        if checked == '':
            raise ValueError('Arithmetic result does not identify one option.')
        if checked:
            answer, explanation = checked, note
        lines = [f'### Question {index}', title]
        lines += [f'- **{letter}.** {options[letter]}' for letter in 'ABCD']
        lines += [f'**Correct Answer:** {answer}', f'**Explanation:** {explanation}']
        if sources:
            lines += ['**Source:** ' + ' '.join(f'[{n}]' for n in dict.fromkeys(sources))]
        blocks.append('\n\n'.join(lines))
    return '\n\n'.join(blocks)
