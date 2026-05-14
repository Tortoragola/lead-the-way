"""Wraps the Gemini filter_dataframe function-call request."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from google import genai
from google.genai import types

from .client import MODEL_EXTRACTION
from .prompts import build_system_prompt
from .tools import FILTER_DATAFRAME_TOOL


@dataclass
class FilterCallResult:
    filters: list[dict]
    logic: str
    called: bool


def request_filters(client: genai.Client, df: pd.DataFrame, query: str) -> FilterCallResult:
    """Ask Gemini to translate the natural-language query into filter rules."""
    system_prompt = build_system_prompt(df)
    response = client.models.generate_content(
        model=MODEL_EXTRACTION,
        contents=f"{system_prompt}\n\nKullanıcı sorgusu: {query}",
        config=types.GenerateContentConfig(
            tools=[FILTER_DATAFRAME_TOOL],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY",
                    allowed_function_names=["filter_dataframe"],
                )
            ),
        ),
    )

    fc = None
    for part in response.candidates[0].content.parts:
        if part.function_call and part.function_call.name == "filter_dataframe":
            fc = part.function_call
            break

    if fc is None:
        return FilterCallResult(filters=[], logic="AND", called=False)

    args = dict(fc.args)
    filters = [dict(f) for f in args.get("filters", [])]
    logic = args.get("logic", "AND")
    return FilterCallResult(filters=filters, logic=logic, called=True)
