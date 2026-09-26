# simple-react-loop

A tiny, framework-free ReAct agent for local LLMs — with a trace mode that shows every
reasoning step and tool call.

The loop is the point; the demo task is answering "what time is it in X?" by chaining two
tools. It runs a **ReAct** cycle — reason, act, observe, repeat — using native tool calling
rather than the original paper's text parsing:

```
Thought      "Likely South Korea. Use geocode_location."
Action       geocode_location({"location_name": "Korea"})
Observation  Koréa, Ivory Coast ... Africa/Abidjan
Thought      "That's wrong. We need South Korea."
Action       geocode_location({"location_name": "South Korea"})
Observation  South Korea ... Asia/Seoul
Thought      -> final answer
```

That self-correction isn't scripted — no code sequences the calls. The model chose to retry
after reading a bad result. `trace_agent.py` prints all of it.

## Architecture

```mermaid
flowchart LR
    User(["User<br/>'time in korea'"]) --> Entry["app.py · local_agent.py<br/>trace_agent.py"]
    Entry --> Send

    subgraph Loop["The ReAct loop — ask() in local_agent.py"]
        direction TB
        Send["1 · Send ENTIRE history<br/>+ tool schemas"]
        Check{"2 · Reply has<br/>tool_calls?"}
        Exec["3 · run_tool()<br/>parse JSON args,<br/>call the function"]
        Send --> Check
        Check -->|"yes · ACTION"| Exec
        Exec -->|"OBSERVATION<br/>append role:tool"| Send
    end

    Send <-.->|"POST /v1/chat/completions"| LLM["llama-server<br/>gpt-oss-20b<br/><i>chooses the tool</i>"]
    Check -->|"no · FINISH"| Answer(["Final answer"])
    Exec --> Geo
    Exec --> Time

    subgraph Tools["time_tools.py — plain functions, no SDK"]
        direction TB
        Geo["geocode_location()"] -->|"HTTP GET"| OM["Open-Meteo"]
        Time["get_time_at_coordinates()"] -->|"HTTP GET"| TA["TimeAPI.io"]
    end

    %% Stroke-only accents: no fill or text colors are overridden, so the node
    %% background and label follow GitHub's light/dark theme automatically.
    style User stroke:#f59e0b,stroke-width:3px
    style LLM stroke:#3b82f6,stroke-width:3px
    style Answer stroke:#22c55e,stroke-width:3px
    style Send stroke:#3b82f6,stroke-width:2px
    style Check stroke:#3b82f6,stroke-width:2px
    style Exec stroke:#3b82f6,stroke-width:2px
```

The model never touches an API. It emits a JSON tool call and stops; **your Python** parses
it, runs the function, makes the HTTP request, and appends the result to history. Steps 1-3
repeat until the model replies without a tool call.

## The model has no memory

Each request to the model starts from nothing: it doesn't remember the last call. So every
round sends the **entire** `messages` list, and the list grows as tool calls and results are
appended to it. For "what time is it in Paris?":

```python
# Round 1: 2 messages
[{"role": "system",    "content": "You are a time assistant..."},
 {"role": "user",      "content": "what time is it in Paris?"}]
# -> model replies with a tool call, not an answer

# Round 2: 4 messages (the same 2, plus the call and its result)
 {"role": "assistant", "tool_calls": [{"function": {"name": "geocode_location",
                        "arguments": "{\"location_name\": \"Paris\"}"}, ...}]},
 {"role": "tool",      "content": "Paris, Île-de-France, France is at latitude 48.85, longitude 2.35 ..."}
# -> model asks for get_time_at_coordinates(48.85, 2.35)

# Round 3: 6 messages (the same 4, plus the second call and its result)
 {"role": "assistant", "tool_calls": [{"function": {"name": "get_time_at_coordinates", ...}}]},
 {"role": "tool",      "content": "Saturday 09/26/2026 at 14:05 (Europe/Paris, DST active: True)."}
# -> model replies in plain text; that reply is appended as message 7
```

In round 2 the model can use the coordinates only because the tool result is in the list it
was sent. The list is its only memory.

The web UI keeps one list for as long as the server runs, so a follow-up like "and Tokyo?"
sends the whole Paris exchange too. That's what makes follow-ups work, and it's also what
fills the 8192-token context after a few questions. **Reset** clears everything but the
system prompt. `trace_agent.py` prints the message count and token count for each round, so
you can watch the list grow.

## What's in the repo

**The local app** is the main project. The model runs on your machine in llama-server, and
all three entry points share the loop in `local_agent.py`:

| File | What | Needs |
|---|---|---|
| `app.py` | web chat UI (Flask) | a running server |
| `local_agent.py` | terminal chat, and home of the `ask()` loop | a running server |
| `trace_agent.py` | one query, every step printed | a running server |

**The Claude version** in [`claude_agent/`](claude_agent/) is optional and separate. It's the
same agent on Claude (`claude-opus-5`) over the internet, kept as a comparison. Nothing in the
local app imports it, and you don't need it (or an API key) to run anything above.

Both versions import the same `time_tools.py`. Only the loop differs — which is the point:
tools are plain functions, and the provider is swappable around them.

## Setup

Local app (needs llama-server running):

```bash
.venv/bin/python app.py              # web UI -> http://localhost:5001
.venv/bin/python local_agent.py      # same thing, in the terminal
```

Port 5001, not 5000 — macOS AirPlay Receiver occupies 5000.

Rebuild the venv with `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
Point `local_agent.py` somewhere else with `LOCAL_BASE_URL` / `LOCAL_MODEL` in `.env`.

Claude version (optional; needs `ANTHROPIC_API_KEY` in `.env`, not llama-server). Run it from
the repo root:

```bash
cp .env.example .env && .venv/bin/python -m claude_agent.agent
```

## Seeing what actually happens

```bash
.venv/bin/python trace_agent.py "time in korea"
```

Runs a single query and prints every round trip: the model's own reasoning, the raw JSON
tool call it emits, the real outbound HTTP request, what came back, and how the token
count grows each round. The best way to understand the loop.

## The tools

`time_tools.py` holds two plain Python functions — no SDK imports:

| Function | Calls | Returns |
|---|---|---|
| `geocode_location(name)` | Open-Meteo geocoding | coordinates + timezone |
| `get_time_at_coordinates(lat, lon)` | TimeAPI.io | current local time |

Test them without any model: `.venv/bin/python time_tools.py`. Costs nothing, and isolates
API breakage from agent bugs.

## How the two loops differ

**`claude_agent/agent.py`** wraps each function in `@beta_tool`, which generates the JSON schema from the
signature, type hints, and docstring. `client.beta.messages.tool_runner(...)` then runs the
whole loop — executing tools and feeding results back — until Claude writes a final answer.

**`local_agent.py`** writes the schemas out by hand (the OpenAI-compatible API has no
generator) and runs the loop itself: call the model, check `message.tool_calls`, execute,
append a `role: "tool"` message, repeat. Capped at `MAX_STEPS` so a confused model can't spin.

Either way the tool descriptions are prompt text — that's what the model reads when deciding
what to call. A vague description produces wrong tool calls.

A turn looks like:

```
you> what time is it at the grand canyon?
  -> geocode_location(location_name='Grand Canyon')
  -> get_time_at_coordinates(latitude=36.05443, longitude=-112.13934)

It's 6:41 PM on Monday, September 14 at the Grand Canyon (America/Phoenix).
```

Nothing hardcodes that order. The model chains the two because the first one's output is
what the second one needs.

## Things to try

- Ask about somewhere ambiguous ("Springfield") and see which one it picks.
- Delete a tool description and watch the calls get worse.
- Add a third tool: write the function, then add it to `TOOL_FUNCTIONS` + `TOOL_SCHEMAS`
  (local) or `TOOLS` in `claude_agent/agent.py` (Claude).

## Roadmap

Planned and proposed work, with the reasoning behind each item, is in [TODO.md](TODO.md).
