"""Run one query and print every step: what is sent, what the model thinks, which tools
it calls, what they return, and how the context grows.

    .venv/bin/python trace_agent.py "time in korea"
"""

import json
import sys

import openai
import requests

from local_agent import BASE_URL, MAX_STEPS, MODEL, SYSTEM_PROMPT, TOOL_FUNCTIONS, TOOL_SCHEMAS

DIM, BOLD, CYAN, GREEN, YELLOW, OFF = "\033[2m", "\033[1m", "\033[36m", "\033[32m", "\033[33m", "\033[0m"
WIDTH = 78


def rule(title: str = "", color: str = "") -> None:
    if not title:
        print(f"{DIM}{'─' * WIDTH}{OFF}")
    else:
        pad = "─" * max(0, WIDTH - len(title) - 3)
        print(f"\n{color}{BOLD}── {title} {pad}{OFF}")


def wrap(text: str, indent: str = "    ", limit: int = 600) -> str:
    """Indent a block of text, truncating anything enormous."""
    text = text.strip()
    if len(text) > limit:
        text = text[:limit] + f"... [{len(text) - limit} more chars]"
    return "\n".join(indent + line for line in text.splitlines())


# --- Show the real outbound HTTP calls the tools make ------------------------------
_real_get = requests.get


def logged_get(url, **kwargs):
    response = _real_get(url, **kwargs)
    print(f"{DIM}      HTTP GET {response.url}{OFF}")
    print(f"{DIM}      <- {response.status_code} {response.reason}, {len(response.content)} bytes{OFF}")
    return response


requests.get = logged_get
# -----------------------------------------------------------------------------------


def main() -> None:
    query = " ".join(sys.argv[1:]) or "time in korea"

    client = openai.OpenAI(base_url=BASE_URL, api_key="not-needed")
    try:
        model = MODEL or client.models.list().data[0].id
    except openai.APIConnectionError:
        sys.exit(f"No server at {BASE_URL}")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]

    rule("SETUP", CYAN)
    print(f"  server   {BASE_URL}")
    print(f"  model    {model.split('/')[-1]}")
    print(f"  tools    {', '.join(t['function']['name'] for t in TOOL_SCHEMAS)}")
    print(f"\n  The model is sent {len(messages)} messages to start:")
    print(f"    [0] system  {DIM}{len(SYSTEM_PROMPT)} chars of instructions{OFF}")
    print(f"    [1] user    {YELLOW}{query!r}{OFF}")

    total_rounds = 0
    for step in range(1, MAX_STEPS + 1):
        total_rounds = step
        rule(f"ROUND {step}: sending {len(messages)} messages to the model", CYAN)

        response = client.chat.completions.create(
            model=model, messages=messages, tools=TOOL_SCHEMAS, temperature=0.2
        )
        choice = response.choices[0]
        message = choice.message
        usage = response.usage

        print(f"  {DIM}context: {usage.prompt_tokens} prompt + {usage.completion_tokens} "
              f"generated = {usage.total_tokens} tokens{OFF}")
        print(f"  {DIM}finish_reason: {choice.finish_reason}{OFF}")

        reasoning = getattr(message, "reasoning_content", None)
        if reasoning:
            print(f"\n  {BOLD}Model's reasoning:{OFF}")
            print(f"{DIM}{wrap(reasoning)}{OFF}")

        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            print(f"\n  {GREEN}{BOLD}No tool calls -> this is the final answer:{OFF}")
            print(f"{GREEN}{wrap(message.content or '(empty)')}{OFF}")
            break

        print(f"\n  {BOLD}Model emitted {len(message.tool_calls)} tool call(s):{OFF}")
        for call in message.tool_calls:
            print(f"\n    {YELLOW}{call.function.name}{OFF}")
            print(f"      raw JSON from model: {DIM}{call.function.arguments}{OFF}")
            args = json.loads(call.function.arguments or "{}")

            print(f"      {DIM}our code now runs this function:{OFF}")
            result = str(TOOL_FUNCTIONS[call.function.name](**args))
            print(f"      returns -> {GREEN}{result}{OFF}")

            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        print(f"\n  {DIM}Results appended to history. Looping back to the model.{OFF}")

    rule("SUMMARY", CYAN)
    print(f"  {total_rounds} round-trips to the model")
    print(f"  {sum(1 for m in messages if m.get('role') == 'tool')} tool executions")
    print(f"  conversation grew from 2 to {len(messages)} messages")
    print(f"\n  {DIM}Each round resent the ENTIRE history -- the model is stateless.{OFF}")
    print(f"  {DIM}That growth is what eventually fills the 8192-token context.{OFF}\n")


if __name__ == "__main__":
    main()
