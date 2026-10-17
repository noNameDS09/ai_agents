"""Allowlisted agent tools.

All tools are deterministic, local (no outbound network), and accept a
Pydantic-validated argument schema. Add a tool here *and* register it in
`graph.py`'s `TOOL_NAMES` allowlist before the model can invoke it.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import operator
import random
import re
import statistics
import string
import uuid
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import quote, unquote

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Arg schemas
# ---------------------------------------------------------------------------

class CalculatorArgs(BaseModel):
    expression: str = Field(..., description="A safe arithmetic expression using numbers and + - * / % // ** ( )", examples=["23 * 17 + 5"])


class CurrentTimeArgs(BaseModel):
    format: str = Field("%Y-%m-%d %H:%M:%S UTC", description="strftime format for the current UTC time")


class KnowledgeBaseLookupArgs(BaseModel):
    query: str = Field(..., description="Free-text query to look up in the KB stub")


class JsonFormatArgs(BaseModel):
    json_text: str = Field(..., description="A JSON string to validate and pretty-print")


class JsonGetArgs(BaseModel):
    json_text: str = Field(..., description="A JSON string")
    path: str = Field(..., description="Dot-separated path to extract (e.g. 'user.name' or 'items.0.id')")


class TextTransformArgs(BaseModel):
    text: str = Field(..., description="Input text")
    operation: str = Field(..., description="Operation: 'uppercase', 'lowercase', 'titlecase', 'reverse', 'word_count', 'char_count', 'sentence_count', 'lines', 'slugify'")


class UnitConverterArgs(BaseModel):
    value: float = Field(..., description="Numeric value to convert")
    from_unit: str = Field(..., description="Source unit (e.g. 'celsius', 'fahrenheit', 'km', 'miles', 'kg', 'pounds')")
    to_unit: str = Field(..., description="Target unit")


class Base64Args(BaseModel):
    text: str = Field(..., description="Text to encode or decode")
    operation: str = Field("encode", description="Operation: 'encode' or 'decode'")


class HashTextArgs(BaseModel):
    text: str = Field(..., description="Text to hash")
    algorithm: str = Field("sha256", description="Hash algorithm: 'sha256', 'sha1', 'md5'")


class GenerateUuidArgs(BaseModel):
    count: int = Field(1, ge=1, le=10, description="Number of UUIDs to generate (1-10)")


class RegexExtractArgs(BaseModel):
    text: str = Field(..., description="Input text")
    pattern: str = Field(..., description="Regular expression pattern")
    group: int = Field(0, ge=0, description="Capture group to extract (0 = full match)")


class MathStatsArgs(BaseModel):
    numbers: list[float] = Field(..., description="List of numbers to compute statistics on")
    operations: list[str] = Field(["mean", "median", "min", "max", "sum", "count"], description="Statistics to compute: mean, median, min, max, sum, count, stdev")


class DateDiffArgs(BaseModel):
    date1: str = Field(..., description="First date in YYYY-MM-DD format")
    date2: str = Field(..., description="Second date in YYYY-MM-DD format")


class RandomNumberArgs(BaseModel):
    min_val: int = Field(1, description="Minimum value (inclusive)")
    max_val: int = Field(100, description="Maximum value (inclusive)")
    count: int = Field(1, ge=1, le=20, description="How many numbers to generate")


class UrlEncodeArgs(BaseModel):
    text: str = Field(..., description="Text to URL-encode or decode")
    operation: str = Field("encode", description="Operation: 'encode' or 'decode'")


class NumberBaseArgs(BaseModel):
    value: str = Field(..., description="Number as string (e.g. '255', '0xFF', '0b11111111')")
    from_base: int = Field(10, description="Source base: 2, 8, 10, or 16")
    to_base: int = Field(16, description="Target base: 2, 8, 10, or 16")


class ColorConvertArgs(BaseModel):
    color: str = Field(..., description="Color value: hex (#FF5733), rgb (255,87,51), or hsl (9,100%,60%)")
    to_format: str = Field(..., description="Target format: 'hex', 'rgb', 'hsl'")


class PasswordGenArgs(BaseModel):
    length: int = Field(16, ge=4, le=64, description="Password length (4-64)")
    include_symbols: bool = Field(True, description="Include special characters")
    count: int = Field(1, ge=1, le=10, description="Number of passwords to generate")


class JwtDecodeArgs(BaseModel):
    token: str = Field(..., description="JWT token to decode (header + payload only, no verification)")


class WordFrequencyArgs(BaseModel):
    text: str = Field(..., description="Text to analyze")
    top_n: int = Field(10, ge=1, le=50, description="Number of top words to return")


class RomanNumeralArgs(BaseModel):
    value: str = Field(..., description="Roman numeral (e.g. 'XIV') or integer (e.g. '14')")
    to_format: str = Field(..., description="Target format: 'roman' or 'arabic'")


class TextSimilarityArgs(BaseModel):
    text1: str = Field(..., description="First text")
    text2: str = Field(..., description="Second text")


class IpValidateArgs(BaseModel):
    ip: str = Field(..., description="IP address to validate and analyze (IPv4 or IPv6)")


class CsvParseArgs(BaseModel):
    csv_text: str = Field(..., description="CSV text with header row")
    delimiter: str = Field(",", description="Column delimiter")


class XmlToJsonArgs(BaseModel):
    xml_text: str = Field(..., description="XML string to convert to JSON")


class CronDescribeArgs(BaseModel):
    expression: str = Field(..., description="Cron expression (5 fields: minute hour day month weekday)")


# ---------------------------------------------------------------------------
# Tavily MCP tools (service-backed, require TAVILY_API_KEY)
# ---------------------------------------------------------------------------

class WebSearchArgs(BaseModel):
    query: str = Field(..., description="Search query for the web")
    search_depth: str = Field("basic", description="Search depth: 'basic' or 'advanced'")
    max_results: int = Field(5, ge=1, le=20, description="Maximum number of results (1-20)")
    topic: str = Field("general", description="Topic: 'general' or 'news'")


class UrlExtractArgs(BaseModel):
    urls: list[str] = Field(..., description="List of URLs to extract content from")
    extract_depth: str = Field("basic", description="Extraction depth: 'basic' or 'advanced'")
    include_images: bool = Field(False, description="Include images in extraction")


class WebCrawlArgs(BaseModel):
    url: str = Field(..., description="Starting URL to crawl")
    max_depth: int = Field(1, ge=1, le=3, description="Maximum crawl depth (1-3)")
    max_breadth: int = Field(20, ge=1, le=50, description="Maximum breadth per level")
    limit: int = Field(50, ge=1, le=100, description="Maximum pages to crawl")


class WebMapArgs(BaseModel):
    url: str = Field(..., description="Starting URL to map")
    max_depth: int = Field(1, ge=1, le=3, description="Maximum map depth (1-3)")


class WebResearchArgs(BaseModel):
    query: str = Field(..., description="Research question or topic")
    model: str = Field("auto", description="Research model: 'auto', 'fast', or 'pro'")


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------

def calculator(args: CalculatorArgs) -> str:
    """Evaluate a small arithmetic expression safely (no eval)."""
    _BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
               ast.Div: operator.truediv, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv,
               ast.Pow: operator.pow}
    _UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
            return _UNARYOPS[type(node.op)](_eval(node.operand))
        raise ValueError(f"unsupported: {type(node).__name__}")

    try:
        tree = ast.parse(args.expression, mode="eval")
        result = _eval(tree)
    except Exception as exc:
        return f"calculator error: {exc}"
    if result == int(result) and abs(result) < 1e15:
        return str(int(result))
    return str(result)


def current_time(args: CurrentTimeArgs) -> str:
    """Return the current UTC time formatted per `args.format`."""
    try:
        return datetime.now(timezone.utc).strftime(args.format)
    except Exception as exc:
        return f"current_time error: {exc}"


def knowledge_base_lookup(args: KnowledgeBaseLookupArgs) -> str:
    """Static knowledge-base stub (no retrieval pipeline)."""
    kb = {"capital of france": "Paris", "capital of japan": "Tokyo",
          "largest planet": "Jupiter", "speed of light": "299,792,458 meters per second"}
    return kb.get(args.query.strip().lower(), f"No KB entry found for: {args.query}")


def json_format(args: JsonFormatArgs) -> str:
    """Validate and pretty-print a JSON string."""
    try:
        return json.dumps(json.loads(args.json_text), indent=2, ensure_ascii=False)
    except json.JSONDecodeError as exc:
        return f"json_format error: {exc}"


def json_get(args: JsonGetArgs) -> str:
    """Extract a value from JSON by dot-separated path (e.g. 'user.name', 'items.0.id')."""
    try:
        data = json.loads(args.json_text)
    except json.JSONDecodeError as exc:
        return f"json_get error: invalid JSON: {exc}"
    for part in args.path.split("."):
        if isinstance(data, dict):
            if part not in data:
                return f"json_get error: key '{part}' not found"
            data = data[part]
        elif isinstance(data, list):
            try:
                idx = int(part)
                data = data[idx]
            except (ValueError, IndexError):
                return f"json_get error: invalid index '{part}'"
        else:
            return f"json_get error: cannot traverse into {type(data).__name__}"
    if isinstance(data, (dict, list)):
        return json.dumps(data, ensure_ascii=False)
    return str(data)


def text_transform(args: TextTransformArgs) -> str:
    """Transform text: uppercase, lowercase, titlecase, reverse, word_count, char_count, sentence_count, lines, slugify."""
    op = args.operation.lower().strip()
    text = args.text
    ops = {
        "uppercase": lambda: text.upper(),
        "lowercase": lambda: text.lower(),
        "titlecase": lambda: text.title(),
        "reverse": lambda: text[::-1],
        "word_count": lambda: str(len(text.split())),
        "char_count": lambda: str(len(text)),
        "sentence_count": lambda: str(len([s for s in re.split(r"[.!?]+", text) if s.strip()])),
        "lines": lambda: str(len(text.splitlines())),
        "slugify": lambda: re.sub(r"[^a-z0-9]+", "-", text.lower().strip()).strip("-"),
    }
    if op in ops:
        return ops[op]()
    return f"text_transform error: unknown operation '{args.operation}'"


_LENGTH = {"meters": 1.0, "meter": 1.0, "m": 1.0, "kilometers": 1000.0, "kilometer": 1000.0, "km": 1000.0,
           "centimeters": 0.01, "centimeter": 0.01, "cm": 0.01, "millimeters": 0.001, "millimeter": 0.001, "mm": 0.001,
           "miles": 1609.344, "mile": 1609.344, "mi": 1609.344, "feet": 0.3048, "foot": 0.3048, "ft": 0.3048,
           "inches": 0.0254, "inch": 0.0254, "in": 0.0254, "yards": 0.9144, "yard": 0.9144, "yd": 0.9144}
_WEIGHT = {"kilograms": 1.0, "kilogram": 1.0, "kg": 1.0, "grams": 0.001, "gram": 0.001, "g": 0.001,
           "milligrams": 1e-6, "milligram": 1e-6, "mg": 1e-6, "pounds": 0.45359237, "pound": 0.45359237,
           "lbs": 0.45359237, "lb": 0.45359237, "ounces": 0.028349523125, "ounce": 0.028349523125, "oz": 0.028349523125}
_TEMP = {"celsius", "fahrenheit", "kelvin", "c", "f", "k"}


def unit_converter(args: UnitConverterArgs) -> str:
    """Convert between common units (length, weight, temperature)."""
    fu, tu, v = args.from_unit.lower().strip(), args.to_unit.lower().strip(), args.value
    if fu in _TEMP and tu in _TEMP:
        c = (v - 32) * 5 / 9 if fu in ("fahrenheit", "f") else (v - 273.15 if fu in ("kelvin", "k") else v)
        result = c * 9 / 5 + 32 if tu in ("fahrenheit", "f") else (c + 273.15 if tu in ("kelvin", "k") else c)
        return str(round(result, 6))
    if fu in _LENGTH and tu in _LENGTH:
        return str(round(v * _LENGTH[fu] / _LENGTH[tu], 6))
    if fu in _WEIGHT and tu in _WEIGHT:
        return str(round(v * _WEIGHT[fu] / _WEIGHT[tu], 6))
    return f"unit_converter error: cannot convert {args.from_unit} to {args.to_unit}"


def base64_encode_decode(args: Base64Args) -> str:
    """Encode or decode text as Base64."""
    op = args.operation.lower().strip()
    try:
        if op == "encode":
            return base64.b64encode(args.text.encode("utf-8")).decode("ascii")
        if op == "decode":
            return base64.b64decode(args.text.encode("ascii"), validate=True).decode("utf-8")
        return f"base64 error: unknown operation '{args.operation}'"
    except Exception as exc:
        return f"base64 error: {exc}"


def hash_text(args: HashTextArgs) -> str:
    """Hash text using SHA256, SHA1, or MD5."""
    algo = args.algorithm.lower().strip()
    if algo not in ("sha256", "sha1", "md5"):
        return f"hash_text error: unknown algorithm '{args.algorithm}'"
    h = hashlib.new(algo)
    h.update(args.text.encode("utf-8"))
    return h.hexdigest()


def generate_uuid(args: GenerateUuidArgs) -> str:
    """Generate one or more UUID4 values."""
    return "\n".join(str(uuid.uuid4()) for _ in range(args.count))


def regex_extract(args: RegexExtractArgs) -> str:
    """Extract regex matches from text."""
    try:
        if args.group > 0:
            results = [m.group(args.group) for m in re.finditer(args.pattern, args.text) if m.lastindex and args.group <= m.lastindex]
            return "\n".join(results) if results else "No matches found."
        matches = re.findall(args.pattern, args.text)
        if not matches:
            return "No matches found."
        if isinstance(matches[0], tuple):
            return "\n".join(", ".join(m) for m in matches)
        return "\n".join(str(m) for m in matches)
    except re.error as exc:
        return f"regex_extract error: {exc}"


def math_stats(args: MathStatsArgs) -> str:
    """Compute statistics (mean, median, min, max, sum, count, stdev) on a list of numbers."""
    nums = args.numbers
    if not nums:
        return "math_stats error: empty list"
    results = {}
    for op in args.operations:
        op = op.lower().strip()
        if op == "mean":
            results["mean"] = round(statistics.mean(nums), 6)
        elif op == "median":
            results["median"] = round(statistics.median(nums), 6)
        elif op == "min":
            results["min"] = min(nums)
        elif op == "max":
            results["max"] = max(nums)
        elif op == "sum":
            results["sum"] = round(sum(nums), 6)
        elif op == "count":
            results["count"] = len(nums)
        elif op == "stdev":
            results["stdev"] = round(statistics.stdev(nums), 6) if len(nums) >= 2 else 0
        else:
            results[op] = "unknown operation"
    return json.dumps(results)


def date_diff(args: DateDiffArgs) -> str:
    """Calculate the difference in days between two dates (YYYY-MM-DD)."""
    try:
        d1 = datetime.strptime(args.date1, "%Y-%m-%d").date()
        d2 = datetime.strptime(args.date2, "%Y-%m-%d").date()
        return f"{(d2 - d1).days} days"
    except ValueError as exc:
        return f"date_diff error: {exc}"


def random_number(args: RandomNumberArgs) -> str:
    """Generate random integers in a range."""
    if args.min_val > args.max_val:
        return "random_number error: min_val must be <= max_val"
    return "\n".join(str(random.randint(args.min_val, args.max_val)) for _ in range(args.count))


def url_encode_decode(args: UrlEncodeArgs) -> str:
    """URL-encode or decode text."""
    op = args.operation.lower().strip()
    try:
        if op == "encode":
            return quote(args.text, safe="")
        if op == "decode":
            return unquote(args.text)
        return f"url_encode_decode error: unknown operation '{args.operation}'"
    except Exception as exc:
        return f"url_encode_decode error: {exc}"


def number_base_convert(args: NumberBaseArgs) -> str:
    """Convert a number between bases (2, 8, 10, 16)."""
    if args.from_base not in (2, 8, 10, 16) or args.to_base not in (2, 8, 10, 16):
        return "number_base_convert error: bases must be 2, 8, 10, or 16"
    try:
        val = int(args.value, args.from_base)
    except ValueError:
        return f"number_base_convert error: invalid number '{args.value}' for base {args.from_base}"
    prefixes = {2: "0b", 8: "0o", 16: "0x"}
    if args.to_base == 2:
        return bin(val)
    if args.to_base == 8:
        return oct(val)
    if args.to_base == 16:
        return hex(val)
    return str(val)


def color_convert(args: ColorConvertArgs) -> str:
    """Convert colors between hex, rgb, and hsl formats."""
    color = args.color.strip().lower()
    target = args.to_format.lower().strip()

    # Parse input to RGB
    r, g, b = None, None, None
    if color.startswith("#"):
        hex_c = color.lstrip("#")
        if len(hex_c) == 3:
            hex_c = "".join(c * 2 for c in hex_c)
        if len(hex_c) == 6:
            r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    elif color.startswith("rgb"):
        m = re.findall(r"\d+", color)
        if len(m) >= 3:
            r, g, b = int(m[0]), int(m[1]), int(m[2])
    elif color.startswith("hsl"):
        m = re.findall(r"[\d.]+", color)
        if len(m) >= 3:
            h, s, l = float(m[0]), float(m[1]) / 100, float(m[2]) / 100
            # HSL to RGB
            import colorsys
            r_f, g_f, b_f = colorsys.hls_to_rgb(h / 360, l, s)
            r, g, b = round(r_f * 255), round(g_f * 255), round(b_f * 255)

    if r is None:
        return f"color_convert error: cannot parse '{args.color}'"

    if target == "hex":
        return f"#{r:02x}{g:02x}{b:02x}"
    if target == "rgb":
        return f"rgb({r}, {g}, {b})"
    if target == "hsl":
        import colorsys
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        return f"hsl({round(h * 360)}, {round(s * 100)}%, {round(l * 100)}%)"
    return f"color_convert error: unknown target '{args.to_format}'"


def password_generator(args: PasswordGenArgs) -> str:
    """Generate secure random passwords."""
    chars = string.ascii_letters + string.digits
    if args.include_symbols:
        chars += "!@#$%^&*()-_=+[]{}|;:,.<>?"
    passwords = []
    for _ in range(args.count):
        pw = "".join(random.choice(chars) for _ in range(args.length))
        passwords.append(pw)
    return "\n".join(passwords)


def jwt_decode(args: JwtDecodeArgs) -> str:
    """Decode a JWT token (header + payload, no signature verification)."""
    parts = args.token.split(".")
    if len(parts) != 3:
        return "jwt_decode error: token must have 3 parts (header.payload.signature)"
    try:
        def _decode_part(part):
            # Add padding
            padded = part + "=" * (4 - len(part) % 4)
            return json.loads(base64.urlsafe_b64decode(padded))
        header = _decode_part(parts[0])
        payload = _decode_part(parts[1])
        return json.dumps({"header": header, "payload": payload}, indent=2)
    except Exception as exc:
        return f"jwt_decode error: {exc}"


def word_frequency(args: WordFrequencyArgs) -> str:
    """Count word frequencies in text, returning top N."""
    words = re.findall(r"\b\w+\b", args.text.lower())
    if not words:
        return "No words found."
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    sorted_freq = sorted(freq.items(), key=lambda x: -x[1])[:args.top_n]
    return json.dumps(dict(sorted_freq))


def roman_numeral(args: RomanNumeralArgs) -> str:
    """Convert between Roman numerals and Arabic integers."""
    roman_map = [("M", 1000), ("CM", 900), ("D", 500), ("CD", 400), ("C", 100),
                 ("XC", 90), ("L", 50), ("XL", 40), ("X", 10), ("IX", 9),
                 ("V", 5), ("IV", 4), ("I", 1)]

    def to_roman(n):
        if n < 1 or n > 3999:
            return None
        result = ""
        for symbol, value in roman_map:
            while n >= value:
                result += symbol
                n -= value
        return result

    def to_arabic(s):
        s = s.upper().strip()
        total = 0
        i = 0
        while i < len(s):
            if i + 1 < len(s) and s[i:i+2] in {r[0] for r in roman_map if len(r[0]) == 2}:
                for symbol, value in roman_map:
                    if symbol == s[i:i+2]:
                        total += value
                        i += 2
                        break
            else:
                for symbol, value in roman_map:
                    if symbol == s[i]:
                        total += value
                        i += 1
                        break
                else:
                    return None
        return total

    target = args.to_format.lower().strip()
    if target == "roman":
        try:
            n = int(args.value)
        except ValueError:
            return "roman_numeral error: value must be an integer"
        result = to_roman(n)
        if result is None:
            return "roman_numeral error: value must be between 1 and 3999"
        return result
    if target == "arabic":
        result = to_arabic(args.value)
        if result is None:
            return "roman_numeral error: invalid Roman numeral"
        return str(result)
    return f"roman_numeral error: unknown target '{args.to_format}'"


def text_similarity(args: TextSimilarityArgs) -> str:
    """Compute Levenshtein distance and similarity between two strings."""
    a, b = args.text1, args.text2
    if len(a) < len(b):
        a, b = b, a
    if len(b) == 0:
        return json.dumps({"distance": len(a), "similarity": 0.0})
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[-1] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    distance = prev[-1]
    max_len = max(len(args.text1), len(args.text2))
    similarity = round(1 - distance / max_len, 4) if max_len > 0 else 1.0
    return json.dumps({"distance": distance, "similarity": similarity})


def ip_validate(args: IpValidateArgs) -> str:
    """Validate and analyze an IPv4 or IPv6 address."""
    import ipaddress
    try:
        ip = ipaddress.ip_address(args.ip)
        result = {
            "valid": True,
            "version": ip.version,
            "is_private": ip.is_private,
            "is_loopback": ip.is_loopback,
            "is_multicast": ip.is_multicast,
            "is_global": ip.is_global,
            "compressed": str(ip),
        }
        if ip.version == 4:
            result["binary"] = bin(int(ip))[2:].zfill(32)
            result["hex"] = hex(int(ip))
        else:
            result["binary"] = bin(int(ip))[2:].zfill(128)
        return json.dumps(result)
    except ValueError:
        return json.dumps({"valid": False, "error": f"'{args.ip}' is not a valid IP address"})


def csv_parse(args: CsvParseArgs) -> str:
    """Parse CSV text with a header row into JSON."""
    import csv
    import io
    try:
        reader = csv.DictReader(io.StringIO(args.csv_text), delimiter=args.delimiter)
        rows = list(reader)
        return json.dumps(rows, ensure_ascii=False)
    except Exception as exc:
        return f"csv_parse error: {exc}"


def xml_to_json(args: XmlToJsonArgs) -> str:
    """Convert XML to JSON."""
    try:
        root = ET.fromstring(args.xml_text)
    except ET.ParseError as exc:
        return f"xml_to_json error: {exc}"

    def _element_to_dict(elem):
        result = {}
        if elem.attrib:
            result["@attributes"] = elem.attrib
        children = list(elem)
        if children:
            child_dict = {}
            for child in children:
                child_data = _element_to_dict(child)
                if child.tag in child_dict:
                    if not isinstance(child_dict[child.tag], list):
                        child_dict[child.tag] = [child_dict[child.tag]]
                    child_dict[child.tag].append(child_data)
                else:
                    child_dict[child.tag] = child_data
            result.update(child_dict)
        text = (elem.text or "").strip()
        if text:
            if len(result) == 0:
                return text
            result["#text"] = text
        return result if result else (elem.text or "").strip()

    return json.dumps({root.tag: _element_to_dict(root)}, indent=2, ensure_ascii=False)


def cron_describe(args: CronDescribeArgs) -> str:
    """Describe a 5-field cron expression in human-readable form."""
    parts = args.expression.split()
    if len(parts) != 5:
        return "cron_describe error: expression must have 5 fields (minute hour day month weekday)"
    minute, hour, day, month, weekday = parts
    day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    def _describe_field(val, name):
        if val == "*":
            return f"every {name}"
        if "/" in val:
            base, step = val.split("/")
            return f"every {step} {name}s" + (f" starting at {base}" if base != "*" else "")
        if "," in val:
            return f"{name}s {val}"
        if "-" in val:
            return f"{name}s {val.replace('-', ' through ')}"
        return f"{name} {val}"

    desc = (
        f"Runs at minute {_describe_field(minute, 'minute')}, "
        f"hour {_describe_field(hour, 'hour')}, "
        f"day of month {_describe_field(day, 'day')}, "
        f"month {_describe_field(month, 'month')}, "
        f"day of week {_describe_field(weekday, 'weekday')}."
    )
    if weekday != "*":
        try:
            wd = int(weekday)
            if 0 <= wd <= 6:
                desc += f" ({day_names[wd]})"
        except ValueError:
            pass
    return desc


# ---------------------------------------------------------------------------
# Tavily MCP tools (service-backed)
# ---------------------------------------------------------------------------

def web_search(args: WebSearchArgs) -> str:
    """Search the web via Tavily MCP and return results with titles, URLs, and snippets."""
    from .tavily_mcp import tavily_search_sync

    return tavily_search_sync(
        query=args.query,
        search_depth=args.search_depth,
        max_results=args.max_results,
        topic=args.topic,
    )


def url_extract(args: UrlExtractArgs) -> str:
    """Extract clean content from one or more URLs via Tavily MCP."""
    from .tavily_mcp import tavily_extract_sync

    return tavily_extract_sync(
        urls=args.urls,
        extract_depth=args.extract_depth,
        include_images=args.include_images,
    )


def web_crawl(args: WebCrawlArgs) -> str:
    """Crawl a website starting from a URL via Tavily MCP."""
    from .tavily_mcp import tavily_crawl_sync

    return tavily_crawl_sync(
        url=args.url,
        max_depth=args.max_depth,
        max_breadth=args.max_breadth,
        limit=args.limit,
    )


def web_map(args: WebMapArgs) -> str:
    """Map a website's URL structure via Tavily MCP."""
    from .tavily_mcp import tavily_map_sync

    return tavily_map_sync(url=args.url, max_depth=args.max_depth)


def web_research(args: WebResearchArgs) -> str:
    """Perform comprehensive multi-source research via Tavily MCP."""
    from .tavily_mcp import tavily_research_sync

    return tavily_research_sync(query=args.query, model=args.model)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, tuple[type[BaseModel], Any]] = {
    # Core
    "calculator": (CalculatorArgs, calculator),
    "current_time": (CurrentTimeArgs, current_time),
    "knowledge_base_lookup": (KnowledgeBaseLookupArgs, knowledge_base_lookup),
    # Data / JSON
    "json_format": (JsonFormatArgs, json_format),
    "json_get": (JsonGetArgs, json_get),
    "csv_parse": (CsvParseArgs, csv_parse),
    "xml_to_json": (XmlToJsonArgs, xml_to_json),
    # Text
    "text_transform": (TextTransformArgs, text_transform),
    "regex_extract": (RegexExtractArgs, regex_extract),
    "word_frequency": (WordFrequencyArgs, word_frequency),
    "text_similarity": (TextSimilarityArgs, text_similarity),
    # Encoding / hashing
    "base64": (Base64Args, base64_encode_decode),
    "hash_text": (HashTextArgs, hash_text),
    "url_encode_decode": (UrlEncodeArgs, url_encode_decode),
    # Math / stats
    "unit_converter": (UnitConverterArgs, unit_converter),
    "math_stats": (MathStatsArgs, math_stats),
    "number_base_convert": (NumberBaseArgs, number_base_convert),
    "random_number": (RandomNumberArgs, random_number),
    "roman_numeral": (RomanNumeralArgs, roman_numeral),
    # Date / time
    "date_diff": (DateDiffArgs, date_diff),
    "cron_describe": (CronDescribeArgs, cron_describe),
    # Security / identity
    "generate_uuid": (GenerateUuidArgs, generate_uuid),
    "password_generator": (PasswordGenArgs, password_generator),
    "jwt_decode": (JwtDecodeArgs, jwt_decode),
    "ip_validate": (IpValidateArgs, ip_validate),
    # Color
    "color_convert": (ColorConvertArgs, color_convert),
    # Web / Tavily MCP (service-backed)
    "web_search": (WebSearchArgs, web_search),
    "url_extract": (UrlExtractArgs, url_extract),
    "web_crawl": (WebCrawlArgs, web_crawl),
    "web_map": (WebMapArgs, web_map),
    "web_research": (WebResearchArgs, web_research),
}

TOOL_NAMES = frozenset(TOOL_REGISTRY)

__all__ = [
    "CalculatorArgs", "CurrentTimeArgs", "KnowledgeBaseLookupArgs",
    "JsonFormatArgs", "JsonGetArgs", "TextTransformArgs", "UnitConverterArgs",
    "Base64Args", "HashTextArgs", "GenerateUuidArgs", "RegexExtractArgs",
    "MathStatsArgs", "DateDiffArgs", "RandomNumberArgs", "UrlEncodeArgs",
    "NumberBaseArgs", "ColorConvertArgs", "PasswordGenArgs", "JwtDecodeArgs",
    "WordFrequencyArgs", "RomanNumeralArgs", "TextSimilarityArgs",
    "IpValidateArgs", "CsvParseArgs", "XmlToJsonArgs", "CronDescribeArgs",
    "WebSearchArgs", "UrlExtractArgs", "WebCrawlArgs", "WebMapArgs", "WebResearchArgs",
    "calculator", "current_time", "knowledge_base_lookup",
    "json_format", "json_get", "text_transform", "unit_converter",
    "base64_encode_decode", "hash_text", "generate_uuid", "regex_extract",
    "math_stats", "date_diff", "random_number", "url_encode_decode",
    "number_base_convert", "color_convert", "password_generator",
    "jwt_decode", "word_frequency", "roman_numeral", "text_similarity",
    "ip_validate", "csv_parse", "xml_to_json", "cron_describe",
    "web_search", "url_extract", "web_crawl", "web_map", "web_research",
    "TOOL_REGISTRY", "TOOL_NAMES",
]
