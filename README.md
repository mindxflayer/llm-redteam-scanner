# LLM Red Team Scanner v1.0

**Adaptive Prompt Injection Testing Tool for LLM Chatbots**

An intelligent, multi-phase security scanner designed to probe chatbot APIs for prompt injection vulnerabilities. It performs automated reconnaissance to profile the target, adapts payloads to target context, handles multiple transport layers, runs stateful conversational attacks, applies evasion techniques, and employs genetic fuzzing to mutate high-scoring payloads.

---

## Technical Advantages: How It Differs From Other Scanners

Most LLM red-teaming utilities (e.g., static payload sprayers) operate by delivering a fixed database of historical jailbreak prompts. They lack target awareness, leading to high false-positive rates and easy detection by simple string filters. LLM Red Team Scanner v1.0 solves this through several advanced paradigms:

1. **Reconnaissance-Driven Adaptation (System Contextualization)**
   Instead of sending generic payloads, the scanner executes an active profiling scan (Phase 1) to determine the chatbot's domain (e.g., finance, travel, flight booking), tone, language model identity, and custom guardrail responses. It then blends raw attack payloads into context-appropriate scenarios (e.g., framing an injection as a ticket booking error) to bypass semantic filters.

2. **Precision Refusal vs. Leak Separation Engine (Clause-Level Parsing)**
   Standard regex scanners flag false positives if the chatbot replies *"I cannot reveal my system prompt."* because the phrase `"system prompt"` is matched. LLM Red Team Scanner uses a smart clause-splitting compiler that isolates sentence transitions (e.g., `however`, `but`, `except`). If a leak indicator is found outside of a refusal context, it is verified as a successful exploit, reducing false-positive rates to near zero.

3. **Expanded Data and Domain Deviation Checking**
   Equipped with heuristics to detect math/logic engine bypasses (e.g., executing arithmetic expressions like `2+2 = 4` outside of role domains), rules and identity instruction leaks (e.g., printing instructions formatted with `RULES:` or in the second person `You are AegisHealth AI`), and sensitive database/CTF flag leaks (`FLAG-X`, patient database keys, admin privileges).

4. **Stateful Multi-Turn Attack Chains**
   Many modern chatbots easily reject single-turn adversarial prompts. This tool implements stateful conversations (e.g., Rapport, Game, Persona, and Continuation chains) to establish a baseline relationship or cooperative behavior first, then shifts the instructions dynamically to trigger the exploit over subsequent turns.

5. **Hybrid Detection Engine (LLM-as-a-Judge)**
   Suspicious outputs can be analyzed by a local or cloud LLM judge (e.g., OpenAI or Ollama architectures) to verify if the compromise was successful. When configured, the judge is evaluated on all findings, acting as the ultimate validator.

6. **Genetic Payload Fuzzing**
   When the scanner locates a weak spot (a payload with possible or likely injection signals), it initiates an evolutionary search. The genetic engine takes these high-scoring seed payloads and applies crossovers, urgency insertions, sentence reordering, and prefix authority mutations to discover even more potent variations.

7. **Flexible Request Templating & Unified Transport Support**
   Supports sending custom static request payloads (`--body-data`) and multiple HTTP headers (`--headers`) to test authenticated endpoints. Built-in support for REST, Server-Sent Events (SSE / text/event-stream), and bidirectional WebSockets.

---

## Installation

```bash
pip install -r requirements.txt
```

**Requirements:**
- Python 3.9+
- `requests>=2.28.0` (REST communications)
- `aiohttp>=3.9.0` (High-performance async request concurrency)
- `websockets>=12.0` (WebSocket transport infrastructure)

---

## Command Line Usage

Execute scans by specifying the chatbot's target URL and request configuration:

```bash
python tool.py -u <target-endpoint> [options]
```

### Quick Reference Command Examples

#### 1. Basic Scan
```bash
python tool.py -u http://localhost:5000/chat -m POST -d message -t json
```

#### 2. Scanning Authenticated Supabase/Backend APIs
For endpoints that require custom JSON payloads (e.g., specifying action types or session parameters) and custom API headers (like bearer tokens), combine `--body-data` and `--headers`:

```bash
python tool.py -u https://api.example.com/chat \
  -m POST \
  -d message \
  --body-data "action:chat,session_id:your_session_id,session_token:your_session_token" \
  --headers "ApiKey: your_api_key_here" "Authorization: Bearer your_bearer_token_here"
```

> [!TIP]
> **Windows/Cmd Quoting Note:** Standard JSON (e.g. `'{"action":"chat"}'`) can fail on Windows CLI because the shell strips double-quotes. To bypass this, the tool supports a **key-value pair fallback parser** using a simple `key:value,key2:value2` comma-separated list as shown above.

#### 3. Concurrent Scan with WAF Evasion
```bash
python tool.py -u http://localhost:5000/chat -m POST -d message -t json --concurrency 10 --rate-limit 20 --evasion
```

#### 4. Complex Multi-Turn & Fuzzed Attack
```bash
python tool.py -u http://localhost:5000/chat -m POST -d message -t json --concurrency 5 --evasion --multi-turn --fuzz --fuzz-generations 3
```

#### 5. Scan with Ollama/OpenAI LLM Judge
```bash
python tool.py -u http://localhost:5000/chat -m POST -d message -t json --judge-url https://api.openai.com/v1 --judge-model gpt-4o-mini --judge-api-key sk-your-key-here
```

#### 6. SSE Streaming & WebSocket Targets
```bash
# SSE Streaming
python tool.py -u https://api.example.com/chat -m POST -d message -t json --transport sse

# WebSockets
python tool.py -u ws://localhost:8080/ws --transport ws --ws-send-field query --ws-recv-field answer
```

---

## CLI Options and Flags Reference

Additionally, run `python tool.py --help` to display syntax options.

### Standard Parameters

* `-u`, `--url` (Required)
  The target endpoint URL for the chatbot API (e.g., `http://localhost:5000/chat`).

* `-m`, `--method`
  The HTTP method to use for sending payloads. Options: `GET`, `POST`, `PUT`, `PATCH`. Default: `POST`.

* `-d`, `--data-field`
  The name of the request dictionary key that contains the user's prompt string (e.g., `message`, `prompt`, `query`). Default: `message`.

* `-r`, `--response-field`
  The dictionary key path inside the JSON response containing the chatbot's text response. Default: `response`.

* `-t`, `--content-type`
  Structure type for HTTP requests. Options: `json` or `form`. Default: `json`.

* `--headers`
  List of additional request headers formatted as `Key:Value` strings. Multiple entries can be passed (e.g., `--headers "Authorization: Bearer XYZ" "X-Custom-Header: value"`).

* `--body-data`
  Additional static POST data fields. Supports a JSON string (e.g., `'{"action": "chat"}'`) or a command-line friendly key-value list (e.g., `"action:chat,session_id:123"`).

### Scan Settings

* `--max-payloads`
  Maximum limit of payloads extracted from both the defensive and adversarial corpora for analysis. Default: `200`.

* `--delay`
  Time in seconds to wait between sequential HTTP requests. Stays active when concurrency is set to 1. Default: `0.5`.

* `--timeout`
  The maximum time limit in seconds for a request to reply before marking it as timed out. Default: `30`.

### Concurrency and Rate Limiting

* `--concurrency`
  Setting this parameter to greater than 1 activates async batch requests. Requires `aiohttp` to run. Default: `1`.

* `--rate-limit`
  Controls the maximum number of requests allowed per second. Active only during concurrent execution mode. Default: `10.0`.

### LLM-as-a-Judge Configuration

* `--judge-url`
  The endpoint URL for the evaluation model engine. Supports OpenAI compatible paths (e.g., `https://api.openai.com/v1` or local instances like Ollama `/api/generate` and `/api/chat`).

* `--judge-model`
  The identifier name of the model instance used to analyze the response. Default: `gpt-4o-mini`.

* `--judge-api-key`
  Optional authentication key for accessing hosting services.

### WAF and Evasion Engine

* `--evasion`
  A boolean flag to turn on obfuscation. When active, approximately 30% of payloads will have randomly selected evasion encoding structures applied (such as Base64, Leetspeak, Unicode homoglyphs, zero-width characters, or rotation transformations).

### Multi-Turn Scripting

* `--multi-turn`
  A boolean flag to activate the stateful conversational execution phase. Highly effective for testing state retention.

* `--multi-turn-chains`
  A subset list specifying which specific conversational strategies to run. Choices options: `rapport`, `game`, `persona`, `continuation`. Default runs all four.

### Genetic Fuzzing Setup

* `--fuzz`
  Enables mutation-based testing. Selects high-scoring output candidates from the spray phase and mutates them iteratively to find cleaner bypass boundaries.

* `--fuzz-generations`
  The number of generational iteration loops for evolutionary testing. Default: `3`.

* `--fuzz-population`
  The size of the candidate population set evaluated in each generation. Default: `10`.

### Output and Diagnostics

* `-o`, `--output`
  The filesystem path directory where JSON and HTML reports are written. Default: `./reports`.

* `-v`, `--verbose`
  A boolean flag to output detailed information to the stdout console, printing full requests, latencies, and partial bot responses in real-time.

---

## File and Architecture Structure

* `tool.py`
  Main entry point coordinating flags parsing and initiating the scanner instance.

* `core/scanner.py`
  The runtime orchestrator enforcing the 4-phase testing flow.

* `core/recon.py`
  Constructs target profiles by analyzing preliminary bot behavior.

* `core/payload_loader.py`
  Loads stratified random sampling over adversarial and defensive JSON corpora.

* `core/adapter.py`
  Peels off outer structural wrappers (XML, tags, markdown fences) and fits clean payloads into domain scenarios.

* `core/evasion.py`
  Transforms payloads to attempt bypassing string detection filters.

* `core/sender.py`
  The core routing sender wrapper for REST targets. Handles static post body insertion.

* `core/async_sender.py`
  Implements non-blocking async payload delivery featuring token-bucket rate controls and custom body maps.

* `core/stream_sender.py`
  Parses incoming text packets from SSE pipelines and WebSocket flows.

* `core/analyzer.py`
  Applies sentence-level refusal checks, math expressions matching, rule and token leak evaluation to classify findings.

* `core/llm_judge.py`
  Evaluates suspicious chatbot response outputs on all findings if enabled.

* `core/multi_turn.py`
  Maintains connection context over consecutive conversational turns.

* `core/fuzzer.py`
  Coordinates crossovers and mutations over high-scoring variants.

* `core/reporter.py`
  Generates responsive HTML dashboards and JSON files summarizing findings.

---

## Output Reports

Scanning output is recorded in two formats inside the specified output directory:
- **JSON files:** Standard structured JSON objects suited for automation scripts or CI/CD pipelines.
- **HTML files:** A pure high-contrast grayscale dashboard designed for local inspection. Clickable table records detail the target profiles, overall risk grades (Critical, High, Medium, Low, Pass), and exact payload-to-response traces for debugging.

---

## Disclaimer

This scanner is designed for authorized security testing, compliance validation, and research purposes only. Do not execute tests against endpoints without prior authorization from the system owners.
