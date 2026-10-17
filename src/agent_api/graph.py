"""LangGraph state graph: LLM ↔ ToolNode loop with Postgres checkpointer.

The checkpointer (`PostgresSaver`) is synchronous, so graph execution is run
inside `asyncio.to_thread` from the service layer to avoid blocking the
FastAPI event loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool as lc_tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.postgres import PostgresSaver

from .config import settings
from .tools import (
    TOOL_NAMES,
    calculator as calc_impl,
    current_time as time_impl,
    knowledge_base_lookup as kb_impl,
    json_format as json_fmt_impl,
    json_get as json_get_impl,
    text_transform as text_impl,
    unit_converter as unit_impl,
    base64_encode_decode as b64_impl,
    hash_text as hash_impl,
    generate_uuid as uuid_impl,
    regex_extract as regex_impl,
    math_stats as stats_impl,
    date_diff as datediff_impl,
    random_number as rand_impl,
    url_encode_decode as url_impl,
    number_base_convert as baseconv_impl,
    color_convert as color_impl,
    password_generator as pwgen_impl,
    jwt_decode as jwt_impl,
    word_frequency as wordfreq_impl,
    roman_numeral as roman_impl,
    text_similarity as sim_impl,
    ip_validate as ip_impl,
    csv_parse as csv_impl,
    xml_to_json as xml_impl,
    cron_describe as cron_impl,
    web_search as websearch_impl,
    url_extract as urlextract_impl,
    web_crawl as webcrawl_impl,
    web_map as webmap_impl,
    web_research as webresearch_impl,
)

logger = logging.getLogger("agent-api.graph")

SYSTEM_PROMPT = (
    "You are a helpful general-purpose assistant with access to tools. "
    "Use the available tools when they can answer the user's request, then "
    "give the final answer in plain language. Do not ask the user for "
    "confirmation before calling a tool. Only call tools whose names appear "
    "in the tool list."
)


def __import_agent_args(tool_name: str, **kwargs):
    """Validate tool-call arguments against the Pydantic args schema."""
    from .tools import TOOL_REGISTRY

    args_schema, _func = TOOL_REGISTRY[tool_name]
    return args_schema(**kwargs)


# LangChain @tool wrappers. Function names must match the tool allowlist.
@lc_tool
def calculator(expression: str) -> str:
    """Evaluate a small arithmetic expression using + - * / % // ** and ()"""
    return calc_impl(__import_agent_args("calculator", expression=expression))


@lc_tool
def current_time(format: str = "%Y-%m-%d %H:%M:%S UTC") -> str:
    """Return the current UTC time formatted with a strftime format string"""
    return time_impl(__import_agent_args("current_time", format=format))


@lc_tool
def knowledge_base_lookup(query: str) -> str:
    """Look up a fact in the static knowledge base stub"""
    return kb_impl(__import_agent_args("knowledge_base_lookup", query=query))


@lc_tool
def json_format(json_text: str) -> str:
    """Validate and pretty-print a JSON string"""
    return json_fmt_impl(__import_agent_args("json_format", json_text=json_text))


@lc_tool
def json_get(json_text: str, path: str) -> str:
    """Extract a value from JSON by dot-separated path (e.g. 'user.name', 'items.0.id')"""
    return json_get_impl(__import_agent_args("json_get", json_text=json_text, path=path))


@lc_tool
def text_transform(text: str, operation: str) -> str:
    """Transform text: uppercase, lowercase, titlecase, reverse, word_count, char_count, sentence_count, lines, slugify"""
    return text_impl(__import_agent_args("text_transform", text=text, operation=operation))


@lc_tool
def unit_converter(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between units (length, weight, temperature)"""
    return unit_impl(__import_agent_args("unit_converter", value=value, from_unit=from_unit, to_unit=to_unit))


@lc_tool
def base64(text: str, operation: str = "encode") -> str:
    """Encode or decode text as Base64"""
    return b64_impl(__import_agent_args("base64", text=text, operation=operation))


@lc_tool
def hash_text(text: str, algorithm: str = "sha256") -> str:
    """Hash text using SHA256, SHA1, or MD5"""
    return hash_impl(__import_agent_args("hash_text", text=text, algorithm=algorithm))


@lc_tool
def generate_uuid(count: int = 1) -> str:
    """Generate one or more UUID4 values"""
    return uuid_impl(__import_agent_args("generate_uuid", count=count))


@lc_tool
def regex_extract(text: str, pattern: str, group: int = 0) -> str:
    """Extract regex matches from text"""
    return regex_impl(__import_agent_args("regex_extract", text=text, pattern=pattern, group=group))


@lc_tool
def math_stats(numbers: list[float], operations: list[str] = None) -> str:
    """Compute statistics (mean, median, min, max, sum, count, stdev) on a list of numbers"""
    if operations is None:
        operations = ["mean", "median", "min", "max", "sum", "count"]
    return stats_impl(__import_agent_args("math_stats", numbers=numbers, operations=operations))


@lc_tool
def date_diff(date1: str, date2: str) -> str:
    """Calculate the difference in days between two dates (YYYY-MM-DD)"""
    return datediff_impl(__import_agent_args("date_diff", date1=date1, date2=date2))


@lc_tool
def random_number(min_val: int = 1, max_val: int = 100, count: int = 1) -> str:
    """Generate random integers in a range"""
    return rand_impl(__import_agent_args("random_number", min_val=min_val, max_val=max_val, count=count))


@lc_tool
def url_encode_decode(text: str, operation: str = "encode") -> str:
    """URL-encode or decode text"""
    return url_impl(__import_agent_args("url_encode_decode", text=text, operation=operation))


@lc_tool
def number_base_convert(value: str, from_base: int = 10, to_base: int = 16) -> str:
    """Convert a number between bases (2, 8, 10, 16)"""
    return baseconv_impl(__import_agent_args("number_base_convert", value=value, from_base=from_base, to_base=to_base))


@lc_tool
def color_convert(color: str, to_format: str) -> str:
    """Convert colors between hex, rgb, and hsl formats"""
    return color_impl(__import_agent_args("color_convert", color=color, to_format=to_format))


@lc_tool
def password_generator(length: int = 16, include_symbols: bool = True, count: int = 1) -> str:
    """Generate secure random passwords"""
    return pwgen_impl(__import_agent_args("password_generator", length=length, include_symbols=include_symbols, count=count))


@lc_tool
def jwt_decode(token: str) -> str:
    """Decode a JWT token (header + payload, no signature verification)"""
    return jwt_impl(__import_agent_args("jwt_decode", token=token))


@lc_tool
def word_frequency(text: str, top_n: int = 10) -> str:
    """Count word frequencies in text, returning top N"""
    return wordfreq_impl(__import_agent_args("word_frequency", text=text, top_n=top_n))


@lc_tool
def roman_numeral(value: str, to_format: str) -> str:
    """Convert between Roman numerals and Arabic integers"""
    return roman_impl(__import_agent_args("roman_numeral", value=value, to_format=to_format))


@lc_tool
def text_similarity(text1: str, text2: str) -> str:
    """Compute Levenshtein distance and similarity between two strings"""
    return sim_impl(__import_agent_args("text_similarity", text1=text1, text2=text2))


@lc_tool
def ip_validate(ip: str) -> str:
    """Validate and analyze an IPv4 or IPv6 address"""
    return ip_impl(__import_agent_args("ip_validate", ip=ip))


@lc_tool
def csv_parse(csv_text: str, delimiter: str = ",") -> str:
    """Parse CSV text with a header row into JSON"""
    return csv_impl(__import_agent_args("csv_parse", csv_text=csv_text, delimiter=delimiter))


@lc_tool
def xml_to_json(xml_text: str) -> str:
    """Convert XML to JSON"""
    return xml_impl(__import_agent_args("xml_to_json", xml_text=xml_text))


@lc_tool
def cron_describe(expression: str) -> str:
    """Describe a 5-field cron expression in human-readable form"""
    return cron_impl(__import_agent_args("cron_describe", expression=expression))


@lc_tool
def web_search(query: str, search_depth: str = "basic", max_results: int = 5, topic: str = "general") -> str:
    """Search the web for current information on any topic. Returns titles, URLs, and content snippets."""
    return websearch_impl(__import_agent_args("web_search", query=query, search_depth=search_depth, max_results=max_results, topic=topic))


@lc_tool
def url_extract(urls: list[str], extract_depth: str = "basic", include_images: bool = False) -> str:
    """Extract clean content from one or more URLs. Returns readable text from web pages."""
    return urlextract_impl(__import_agent_args("url_extract", urls=urls, extract_depth=extract_depth, include_images=include_images))


@lc_tool
def web_crawl(url: str, max_depth: int = 1, max_breadth: int = 20, limit: int = 50) -> str:
    """Crawl a website starting from a URL. Extracts content from multiple pages."""
    return webcrawl_impl(__import_agent_args("web_crawl", url=url, max_depth=max_depth, max_breadth=max_breadth, limit=limit))


@lc_tool
def web_map(url: str, max_depth: int = 1) -> str:
    """Map a website's URL structure. Returns a list of discovered URLs."""
    return webmap_impl(__import_agent_args("web_map", url=url, max_depth=max_depth))


@lc_tool
def web_research(query: str, model: str = "auto") -> str:
    """Perform comprehensive multi-source research on a topic. Returns a cited report."""
    return webresearch_impl(__import_agent_args("web_research", query=query, model=model))


_LC_TOOLS = [
    calculator, current_time, knowledge_base_lookup,
    json_format, json_get, text_transform, unit_converter, base64, hash_text,
    generate_uuid, regex_extract, math_stats, date_diff, random_number,
    url_encode_decode, number_base_convert, color_convert, password_generator,
    jwt_decode, word_frequency, roman_numeral, text_similarity, ip_validate,
    csv_parse, xml_to_json, cron_describe,
    web_search, url_extract, web_crawl, web_map, web_research,
]

# Safety: the LangChain tool names must match the allowlisted tool names.
assert {t.name for t in _LC_TOOLS} == TOOL_NAMES, (
    f"LangChain tool names {[t.name for t in _LC_TOOLS]} != allowlist {TOOL_NAMES}"
)


def _build_graph(checkpointer: PostgresSaver | None = None) -> Any:
    model = ChatOpenAI(
        model=settings.openrouter_model,
        openai_api_key=settings.openrouter_api_key,
        openai_api_base=settings.openrouter_base_url,
        temperature=0,
        default_headers={
            "HTTP-Referer": settings.openrouter_http_referer,
            "X-Title": settings.openrouter_x_title,
        },
    ).bind_tools(_LC_TOOLS)

    def call_model(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)
        response = model.invoke(messages, config)
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("model", call_model)
    builder.add_node("tools", ToolNode(_LC_TOOLS))
    builder.set_entry_point("model")
    builder.add_conditional_edges("model", tools_condition)
    builder.add_edge("tools", "model")
    return builder.compile(checkpointer=checkpointer)


def build_graph() -> Any:
    """Compile the LangGraph app (no checkpointer). Stateless runs."""
    return _build_graph(checkpointer=None)


def build_graph_with_checkpointer() -> tuple[Any, object]:
    """Compile the LangGraph app with a Postgres checkpointer (stateful)."""
    import psycopg

    conn = psycopg.connect(settings.psycopg_database_url, autocommit=True)
    saver = PostgresSaver(conn)
    saver.setup()
    return _build_graph(checkpointer=saver), conn


async def run_graph(
    messages: list[dict[str, str]],
    thread_id: str | None,
    model_override: str | None = None,
) -> dict[str, Any]:
    """Run the agent graph in a worker thread."""
    langchain_messages = [
        HumanMessage(content=m["content"])
        if m["role"] == "user"
        else AIMessage(content=m["content"])
        for m in messages
    ]

    def _run() -> dict[str, Any]:
        config: RunnableConfig = {}
        if thread_id:
            config["configurable"] = {"thread_id": thread_id}
        if thread_id:
            app, conn = build_graph_with_checkpointer()
            try:
                return app.invoke({"messages": langchain_messages}, config)
            finally:
                conn.close()
        return build_graph().invoke({"messages": langchain_messages}, config)

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:
        logger.exception("graph execution failed")
        raise RuntimeError(f"agent execution failed: {exc}") from exc

    final_messages = result.get("messages", [])
    assistant_text = ""
    tool_calls: list[dict[str, Any]] = []
    steps = 0
    for msg in final_messages:
        steps += 1
        if isinstance(msg, AIMessage):
            if msg.content:
                assistant_text = msg.content
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append(
                        {
                            "name": tc.get("name"),
                            "arguments": tc.get("args", {}),
                        }
                    )
        elif isinstance(msg, ToolMessage):
            steps += 1

    if tool_calls:
        names = ", ".join(tc["name"] for tc in tool_calls)
        citation = f"\n\n_(tool called: {names})_"
        assistant_text = (assistant_text or "") + citation

    return {
        "response": assistant_text or "(no response)",
        "tool_calls": tool_calls,
        "steps": max(steps, 1),
    }