# agent-api — Capability Roadmap & Plan

Source: gap analysis of the current 26-tool implementation against common
expectations for a general-purpose AI agent.

## Current state

26 deterministic, local tools across:
- Core: calculator, current_time, knowledge_base_lookup
- Data/JSON: json_format, json_get, csv_parse, xml_to_json
- Text: text_transform, regex_extract, word_frequency, text_similarity
- Encoding/hash: base64, hash_text, url_encode_decode
- Math/numbers: unit_converter, math_stats, number_base_convert, random_number, roman_numeral
- Date/time: date_diff, cron_describe
- Security/identity: generate_uuid, password_generator, jwt_decode, ip_validate
- Color: color_convert

Plus: LangGraph ReAct loop, PostgreSQL checkpoints + audit, OpenRouter free models,
FastAPI backend, React/Vite frontend, 57 tests.

## Guiding principle

Keep deterministic utilities (calculator, json_format, text_transform) as LOCAL
tools. Implement web search, document processing, code execution, and third-party
integrations as SERVICE-BACKED tools with explicit security boundaries
(isolation, permission checks, resource limits, outbound-network controls).
Do NOT add them to the existing local-tool allowlist without security review.

## Priority 1 — Web & information retrieval (critical)

| Tool | What users can do | Priority | Notes |
|------|-------------------|----------|-------|
| Web search | Search the internet for current information | Critical | Service-backed; needs search provider (Brave/Tavily/DuckDuckGo) |
| URL reader | Retrieve and summarize web pages | Critical | Service-backed; fetch + extract readable text; SSRF controls |
| News search | Find recent news and developments | High | Could reuse web search with news filter |
| Website content extraction | Extract readable text from websites | High | Reuse URL reader extraction pipeline |
| YouTube transcript reader | Extract and summarize video transcripts | High | Service-backed; yt-dlp or youtube-transcript-api |
| Academic paper search | Find research papers and publications | Medium | arXiv/Semantic Scholar API |
| Webpage comparison | Compare information across multiple URLs | Medium | Depends on URL reader |

## Priority 2 — File & document tools (critical)

| Tool | What users can do | Priority | Notes |
|------|-------------------|----------|-------|
| PDF text extraction | Extract text from PDF documents | Critical | PyMuPDF / pdfplumber; service-backed (file upload) |
| PDF summarization | Summarize uploaded documents | Critical | Depends on PDF extraction + LLM |
| Excel/CSV analyzer | Analyze tabular data, answer questions | Critical | pandas; extends existing csv_parse |
| DOCX reader | Read Word documents | High | python-docx |
| OCR | Extract text from images / scanned docs | High | pytesseract or cloud OCR |
| Markdown reader/writer | Read and generate Markdown files | High | Local tool (deterministic) |
| File conversion | Convert document formats | High | pandoc / libreoffice (service) |
| PowerPoint reader | Extract presentation content | Medium | python-pptx |
| Document comparison | Diff two documents | Medium | Depends on extraction |
| ZIP archive reader | List and inspect archive contents | Medium | zipfile (local, sandboxed) |

## Priority 3 — Productivity & everyday (high)

| Tool | What users can do | Priority | Notes |
|------|-------------------|----------|-------|
| Email drafting | Compose and improve emails | High | LLM-assisted (local, no send) |
| Translation | Translate text between languages | High | Could use free translation API or LLM |
| Time-zone conversion | Compare times across locations | Medium | zoneinfo (stdlib, local) |
| Weather lookup | Current weather and forecasts | Medium | Open-Meteo (free, no key) |
| Notes management | Create, search, update notes | High | Requires persistent storage (DB) |
| Task management | Create, update, track tasks | High | Requires persistent storage (DB) |
| Reminder management | Set reminders for future events | High | Requires scheduler + DB |
| Calendar integration | View/manage calendar events | High | External integration (Google/Outlook) |
| Meeting summarization | Summarize transcripts, extract action items | High | LLM-assisted |
| Maps and directions | Find places and routes | Medium | External API (Google Maps / OSM) |

Note: Calendar, email, task, reminder tools require external integrations and
should NOT be implemented as purely local deterministic utilities.

## Priority 4 — Developer tools (high)

| Tool | What users can do | Priority | Notes |
|------|-------------------|----------|-------|
| Code execution | Execute code in isolated environment | Critical | Sandbox (Docker/nsjail); security-sensitive |
| Code explanation | Explain unfamiliar source code | High | LLM-assisted (local) |
| Code debugging | Analyze errors and suggest fixes | High | LLM-assisted (local) |
| JSON Schema validator | Validate structured data against schema | High | jsonschema (local, deterministic) |
| API tester | Make and inspect HTTP requests | High | Service-backed; SSRF controls |
| SQL query execution | Query an authorized database | High | Service-backed; read-only, allowlisted DB |
| GitHub repository reader | Inspect repos and source files | High | GitHub API (service-backed) |
| Regex tester | Test regex against sample input | Medium | Local (re module) |
| Git diff analyzer | Explain code changes | Medium | LLM-assisted |
| Documentation search | Search framework/library docs | High | Service-backed (web search + extraction) |
| Shell command execution | Execute commands in controlled env | High | Security-sensitive; sandbox + allowlist |
| Dependency vulnerability checker | Identify vulnerable packages | Medium | Service-backed (OSV API) |

Security note: Code execution, shell access, DB queries, and arbitrary HTTP
requests need isolation, permission checks, resource limits, and strict
outbound-network controls. Do NOT add them to the local-tool allowlist.

## Priority 5 — Data analysis & visualization (high)

| Tool | What users can do | Priority | Notes |
|------|-------------------|----------|-------|
| Data profiling | Inspect columns, types, missing values, distributions | Critical | pandas (service-backed or sandboxed) |
| Statistical analysis | Correlations, distributions, summary stats | High | scipy/statsmodels |
| CSV filtering/transformation | Filter, sort, group, transform datasets | High | pandas |
| Chart generation | Bar, line, scatter, pie charts | High | matplotlib/plotly (image output) |
| SQL-to-chart | Turn query results into visualizations | High | Depends on SQL + chart gen |
| Data cleaning | Detect duplicates, missing values, inconsistencies | High | pandas |
| Spreadsheet formulas | Generate and explain formulas | High | LLM-assisted |
| Report generation | Generate downloadable analysis reports | High | Depends on multiple tools |
| Regression and forecasting | Analyze trends and produce forecasts | Medium | statsmodels/sklearn |

Current csv_parse and math_stats are simple parsing/summary. Opportunity: move
into dataset understanding, analytical operations, visual output.

## Priority 6 — Image, audio, video (medium)

| Tool | What users can do | Priority | Notes |
|------|-------------------|----------|-------|
| Image understanding | Describe and answer questions about images | High | Multimodal model (OpenRouter vision) |
| Image OCR | Read text from screenshots/photos | High | pytesseract / cloud OCR |
| Speech-to-text | Transcribe audio recordings | High | Whisper / cloud STT |
| Audio summarization | Summarize recordings and conversations | High | STT + LLM |
| Image metadata reader | Inspect dimensions and metadata | Medium | Pillow |
| Text-to-speech | Generate spoken audio | Medium | TTS service |
| Video summarization | Summarize videos from accessible media | Medium | Depends on STT + LLM |
| Video metadata reader | Inspect duration, resolution, frame rate | Medium | ffmpeg |
| Image resizing/compression | Resize and optimize images | Medium | Pillow |

These may require multimodal models or specialized libraries rather than
ordinary text-based tool calls.

## Priority 7 — Advanced agent capabilities (high)

| Capability | Purpose | Priority | Notes |
|------------|---------|----------|-------|
| Persistent memory | Recall user-approved facts across conversations | High | Vector store + retrieval; distinct from PG checkpoints |
| RAG over uploaded files | Answer questions grounded in user documents | Critical | Chunk + embed + retrieve |
| Multi-step research | Search, read, compare, synthesize multiple sources | High | Orchestration of web search + URL reader |
| Tool result verification | Check whether tool outputs support the answer | High | LLM-based verification step |
| Multi-tool workflows | Chain tools together to complete a task | High | LangGraph already supports this |
| Structured output generation | Return validated JSON or typed results | High | Pydantic output parsing |
| Citation generation | Link claims to retrieved sources | High | Depends on web search + URL reader |
| Human approval workflow | Request approval before consequential actions | High | LangGraph interrupt + UI approval |
| Background jobs | Run long tasks asynchronously | Medium | Celery / ARQ + Redis |
| Scheduled workflows | Execute recurring tasks | Medium | APScheduler / cron |

Foundation exists: LangGraph ReAct loop + PostgreSQL checkpoints. But PG state
alone is NOT semantic long-term memory or RAG — those need vector stores.

## Implementation order (recommended)

1. **Web search + URL reader** — enables current-info queries, research, source-backed answers
2. **File upload + document analysis** — PDF, DOCX, CSV, XLSX; add RAG for large docs
3. **Sandboxed code execution** — data analysis, code testing, computation beyond calculator
4. **Data analysis + chart generation** — insights, visualizations, reports from datasets
5. **Persistent memory + multi-step research** — context-aware, multi-source tasks

Build these four capabilities before adding more basic utilities. They offer the
clearest expansion from the current 26-tool implementation into a practical,
general-purpose AI agent.

## Architectural distinction

- **Local deterministic tools** (calculator, json_format, text_transform, hash_text,
  base64, unit_converter, etc.): safe to run in-process, no network, no side effects.
- **Service-backed tools** (web search, URL reader, code execution, file processing,
  DB queries, HTTP requests, OCR, TTS): require isolation, permission checks,
  resource limits, and strict outbound-network controls. Implement as separate
  services with explicit security boundaries. Do NOT add them to the local-tool
  allowlist without security review.

## Security requirements for new capabilities

- Web search / URL reader: SSRF prevention, URL allowlisting, content size limits
- Code execution: sandboxed container (Docker/nsjail), CPU/memory/time limits, no network
- File processing: virus scanning, size limits, temp file cleanup
- DB queries: read-only connections, allowlisted tables, query timeout
- HTTP requests: outbound allowlist, no internal IPs, response size limits
- All service-backed tools: audit logging, rate limiting, user authorization
