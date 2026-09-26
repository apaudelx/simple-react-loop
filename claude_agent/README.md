# claude_agent (optional)

The same time agent, running on **Claude** over the internet instead of the local model.
It's a side-by-side comparison, not part of the local app: nothing else imports it, and you
don't need it to run `app.py`, `local_agent.py`, or `trace_agent.py`.

It shares only `../time_tools.py` with the local version. That's the point it demonstrates:
tools are plain functions, and the model around them is swappable.

## Run

From the repo root (not from this folder), so the shared `time_tools.py` can be imported:

```bash
cp .env.example .env          # then put your ANTHROPIC_API_KEY in .env
.venv/bin/python -m claude_agent.agent
```

Needs an Anthropic API key (usage is billed) and an internet connection. It doesn't need
llama-server.

## How it differs from the local loop

`@beta_tool` generates each tool's JSON schema from the function's signature and docstring,
and the SDK's `tool_runner` runs the whole ReAct loop internally. In `local_agent.py` both
are written by hand. See "How the two loops differ" in the main README.
