from __future__ import annotations

import math

from library.llm.openai_adapter import _parse_tool_arguments


def test_tool_argument_parser_repairs_common_transport_syntax() -> None:
    cases = [
        ('```json\n{"text": "Phoenix"}\n```', "code_fence"),
        ('{"text": "Phoenix",}', "trailing_comma"),
        ('{"text": ["Phoenix"]', "closing_delimiter"),
        ("{'text': 'Phoenix'}", "python_literal"),
    ]
    for raw, strategy_fragment in cases:
        value, error, strategy = _parse_tool_arguments(raw)
        assert value == {"text": "Phoenix"} or value == {"text": ["Phoenix"]}
        assert error is None
        assert strategy is not None and strategy_fragment in strategy


def test_tool_argument_parser_rejects_ambiguous_or_non_json_values() -> None:
    for raw in ('{"query":}', "{'value': (1, 2)}", f"{{'value': {math.inf}}}"):
        value, error, strategy = _parse_tool_arguments(raw)
        assert value == {}
        assert error is not None
        assert strategy is None
