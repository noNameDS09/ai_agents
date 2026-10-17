"""Unit tests for allowlisted tools (no DB, no network)."""

from __future__ import annotations

import base64
import json
import uuid

from agent_api.tools import (
    Base64Args,
    CalculatorArgs,
    CurrentTimeArgs,
    DateDiffArgs,
    GenerateUuidArgs,
    HashTextArgs,
    JsonFormatArgs,
    KnowledgeBaseLookupArgs,
    MathStatsArgs,
    RandomNumberArgs,
    RegexExtractArgs,
    TextTransformArgs,
    UnitConverterArgs,
    UrlExtractArgs,
    WebCrawlArgs,
    WebMapArgs,
    WebResearchArgs,
    WebSearchArgs,
    TOOL_NAMES,
    base64_encode_decode,
    calculator,
    current_time,
    date_diff,
    generate_uuid,
    hash_text,
    json_format,
    knowledge_base_lookup,
    math_stats,
    random_number,
    regex_extract,
    text_transform,
    unit_converter,
    url_extract,
    web_crawl,
    web_map,
    web_research,
    web_search,
)


def test_tool_allowlist_names():
    assert len(TOOL_NAMES) == 31
    expected = {
        "calculator", "current_time", "knowledge_base_lookup",
        "json_format", "json_get", "text_transform", "unit_converter",
        "base64", "hash_text", "generate_uuid", "regex_extract",
        "math_stats", "date_diff", "random_number", "url_encode_decode",
        "number_base_convert", "color_convert", "password_generator",
        "jwt_decode", "word_frequency", "roman_numeral", "text_similarity",
        "ip_validate", "csv_parse", "xml_to_json", "cron_describe",
        "web_search", "url_extract", "web_crawl", "web_map", "web_research",
    }
    assert TOOL_NAMES == expected


def test_calculator_basic():
    assert calculator(CalculatorArgs(expression="23 * 17 + 5")) == "396"
    assert calculator(CalculatorArgs(expression="2 + 2")) == "4"
    assert calculator(CalculatorArgs(expression="10 / 4")) == "2.5"
    assert calculator(CalculatorArgs(expression="(3 + 4) * 2")) == "14"


def test_calculator_rejects_unsafe():
    for bad in ["__import__('os')", "2; drop table", "2 < 3", "true and false"]:
        result = calculator(CalculatorArgs(expression=bad))
        assert result.startswith("calculator error"), bad


def test_calculator_division_by_zero():
    result = calculator(CalculatorArgs(expression="1 / 0"))
    assert result.startswith("calculator error")


def test_current_time():
    out = current_time(CurrentTimeArgs(format="%Y-%m-%d %H:%M:%S UTC"))
    assert out.endswith(" UTC")
    assert len(out) == len("2026-01-01 00:00:00 UTC")


def test_knowledge_base_lookup_found():
    assert knowledge_base_lookup(KnowledgeBaseLookupArgs(query="capital of france")) == "Paris"
    assert knowledge_base_lookup(KnowledgeBaseLookupArgs(query="largest planet")) == "Jupiter"


def test_knowledge_base_lookup_not_found():
    result = knowledge_base_lookup(KnowledgeBaseLookupArgs(query="nothing here"))
    assert result.startswith("No KB entry found")


def test_json_format_valid():
    result = json_format(JsonFormatArgs(json_text='{"a":1,"b":[2,3]}'))
    parsed = json.loads(result)
    assert parsed == {"a": 1, "b": [2, 3]}
    assert "\n" in result  # pretty-printed


def test_json_format_invalid():
    result = json_format(JsonFormatArgs(json_text="{bad json"))
    assert result.startswith("json_format error")


def test_text_transform():
    assert text_transform(TextTransformArgs(text="hello world", operation="uppercase")) == "HELLO WORLD"
    assert text_transform(TextTransformArgs(text="HELLO", operation="lowercase")) == "hello"
    assert text_transform(TextTransformArgs(text="hello world", operation="titlecase")) == "Hello World"
    assert text_transform(TextTransformArgs(text="abc", operation="reverse")) == "cba"
    assert text_transform(TextTransformArgs(text="one two three", operation="word_count")) == "3"
    assert text_transform(TextTransformArgs(text="hello", operation="char_count")) == "5"
    assert text_transform(TextTransformArgs(text="a. b. c.", operation="sentence_count")) == "3"
    assert text_transform(TextTransformArgs(text="a\nb\nc", operation="lines")) == "3"


def test_text_transform_unknown():
    result = text_transform(TextTransformArgs(text="x", operation="bogus"))
    assert result.startswith("text_transform error")


def test_unit_converter():
    assert unit_converter(UnitConverterArgs(value=100, from_unit="celsius", to_unit="fahrenheit")) == "212.0"
    assert unit_converter(UnitConverterArgs(value=1, from_unit="km", to_unit="miles")) == "0.621371"
    assert unit_converter(UnitConverterArgs(value=1, from_unit="kg", to_unit="pounds")) == "2.204623"
    assert unit_converter(UnitConverterArgs(value=0, from_unit="celsius", to_unit="kelvin")) == "273.15"


def test_unit_converter_error():
    result = unit_converter(UnitConverterArgs(value=1, from_unit="foo", to_unit="bar"))
    assert result.startswith("unit_converter error")


def test_base64():
    encoded = base64_encode_decode(Base64Args(text="hello", operation="encode"))
    assert encoded == base64.b64encode(b"hello").decode()
    decoded = base64_encode_decode(Base64Args(text=encoded, operation="decode"))
    assert decoded == "hello"


def test_base64_decode_error():
    result = base64_encode_decode(Base64Args(text="not-valid-base64!!!", operation="decode"))
    assert result.startswith("base64 error")


def test_hash_text():
    import hashlib
    result = hash_text(HashTextArgs(text="hello", algorithm="sha256"))
    assert result == hashlib.sha256(b"hello").hexdigest()
    result = hash_text(HashTextArgs(text="hello", algorithm="md5"))
    assert result == hashlib.md5(b"hello").hexdigest()


def test_hash_text_unknown_algo():
    result = hash_text(HashTextArgs(text="x", algorithm="bogus"))
    assert result.startswith("hash_text error")


def test_generate_uuid():
    result = generate_uuid(GenerateUuidArgs(count=1))
    uuid.UUID(result)  # validates
    result3 = generate_uuid(GenerateUuidArgs(count=3))
    lines = result3.strip().split("\n")
    assert len(lines) == 3
    for line in lines:
        uuid.UUID(line)


def test_regex_extract():
    result = regex_extract(RegexExtractArgs(text="abc 123 def 456", pattern=r"\d+"))
    assert result == "123\n456"
    result = regex_extract(RegexExtractArgs(text="no digits", pattern=r"\d+"))
    assert result == "No matches found."


def test_regex_extract_group():
    result = regex_extract(RegexExtractArgs(text="name: John, age: 30", pattern=r"name: (\w+)", group=1))
    assert result == "John"


def test_regex_extract_error():
    result = regex_extract(RegexExtractArgs(text="x", pattern="["))
    assert result.startswith("regex_extract error")


def test_math_stats():
    result = math_stats(MathStatsArgs(numbers=[1, 2, 3, 4, 5], operations=["mean", "median", "min", "max", "sum", "count"]))
    parsed = json.loads(result)
    assert parsed["mean"] == 3.0
    assert parsed["median"] == 3.0
    assert parsed["min"] == 1
    assert parsed["max"] == 5
    assert parsed["sum"] == 15.0
    assert parsed["count"] == 5


def test_math_stats_stdev():
    result = math_stats(MathStatsArgs(numbers=[2, 4, 4, 4, 5, 5, 7, 9], operations=["stdev"]))
    parsed = json.loads(result)
    assert "stdev" in parsed


def test_math_stats_empty():
    result = math_stats(MathStatsArgs(numbers=[], operations=["mean"]))
    assert result.startswith("math_stats error")


def test_date_diff():
    assert date_diff(DateDiffArgs(date1="2024-01-01", date2="2024-01-10")) == "9 days"
    assert date_diff(DateDiffArgs(date1="2024-01-10", date2="2024-01-01")) == "-9 days"


def test_date_diff_error():
    result = date_diff(DateDiffArgs(date1="bad", date2="2024-01-01"))
    assert result.startswith("date_diff error")


def test_random_number():
    result = random_number(RandomNumberArgs(min_val=1, max_val=10, count=5))
    lines = result.strip().split("\n")
    assert len(lines) == 5
    for line in lines:
        assert 1 <= int(line) <= 10


def test_random_number_error():
    result = random_number(RandomNumberArgs(min_val=10, max_val=1, count=1))
    assert result.startswith("random_number error")


# ---------------------------------------------------------------------------
# Tavily MCP tools (mocked — no real network calls)
# ---------------------------------------------------------------------------

from unittest.mock import patch


def test_web_search_no_api_key():
    """web_search returns error when TAVILY_API_KEY is empty."""
    from agent_api import config
    original = config.settings.tavily_api_key
    config.settings.tavily_api_key = ""
    try:
        result = web_search(WebSearchArgs(query="test"))
        assert result.startswith("tavily error")
        assert "TAVILY_API_KEY" in result
    finally:
        config.settings.tavily_api_key = original


def test_web_search_mocked():
    with patch("agent_api.tavily_mcp.tavily_search_sync", return_value='{"results": [{"title": "Test", "url": "https://example.com", "content": "test content"}]}'):
        result = web_search(WebSearchArgs(query="python"))
        assert "Test" in result
        assert "example.com" in result


def test_url_extract_mocked():
    with patch("agent_api.tavily_mcp.tavily_extract_sync", return_value='{"results": [{"url": "https://example.com", "raw_content": "extracted text"}]}'):
        result = url_extract(UrlExtractArgs(urls=["https://example.com"]))
        assert "extracted text" in result


def test_web_crawl_mocked():
    with patch("agent_api.tavily_mcp.tavily_crawl_sync", return_value='{"results": [{"url": "https://example.com/page1", "raw_content": "page content"}]}'):
        result = web_crawl(WebCrawlArgs(url="https://example.com"))
        assert "page content" in result


def test_web_map_mocked():
    with patch("agent_api.tavily_mcp.tavily_map_sync", return_value='{"urls": ["https://example.com", "https://example.com/about"]}'):
        result = web_map(WebMapArgs(url="https://example.com"))
        assert "example.com" in result


def test_web_research_mocked():
    with patch("agent_api.tavily_mcp.tavily_research_sync", return_value='{"answer": "Research summary here", "sources": []}'):
        result = web_research(WebResearchArgs(query="AI trends"))
        assert "Research summary" in result