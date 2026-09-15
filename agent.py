"""A minimal Claude agent that answers questions about local time anywhere in the world.

The model decides which tools to call and in what order. Typically it chains them:
geocode_location -> get_time_at_coordinates -> a written answer.
"""

import os
import sys

import anthropic
from anthropic import beta_tool
from dotenv import load_dotenv

from time_tools import geocode_location, get_time_at_coordinates

load_dotenv()

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """You are a time assistant. You answer questions about the current \
local time in places around the world.

To find the time somewhere, first geocode the place name to coordinates, then look up \
the time at those coordinates. If a place name is ambiguous, say which place you used. \
Keep answers to one or two sentences."""

# The decorator turns a plain function into a tool definition: the name, the JSON
# schema, and the description all come from the signature, type hints, and docstring.
TOOLS = [beta_tool(geocode_location), beta_tool(get_time_at_coordinates)]


def describe_tool_calls(message: anthropic.types.beta.BetaMessage) -> None:
    """Print the tool calls in a message so you can watch the agent work."""
    for block in message.content:
        if block.type == "tool_use":
            args = ", ".join(f"{k}={v!r}" for k, v in block.input.items())
            print(f"  \033[2m-> {block.name}({args})\033[0m")


def ask(client: anthropic.Anthropic, messages: list) -> str:
    """Run one turn of the agent loop to completion and return the final text."""
    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=messages,
        thinking={"type": "adaptive"},
        # Effort controls how hard the model thinks. Time lookups are easy, so "low"
        # keeps this fast and cheap. Raise to "high" or "max" for harder work.
        output_config={"effort": "low"},
    )

    final = None
    for message in runner:
        final = message
        describe_tool_calls(message)
        # Mirror the runner's history into our own list so the next turn has context.
        messages.append({"role": "assistant", "content": message.content})
        tool_response = runner.generate_tool_call_response()
        if tool_response is not None:
            messages.append(tool_response)

    if final is None:
        return "(no response)"
    if final.stop_reason == "refusal":
        return "(the model declined to answer that)"
    return "".join(block.text for block in final.content if block.type == "text")


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Put it in a .env file (see .env.example).")

    client = anthropic.Anthropic()
    messages: list = []

    print("Time agent. Ask about the time anywhere. Ctrl-C or 'quit' to exit.\n")
    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit"}:
            return

        messages.append({"role": "user", "content": user_input})
        try:
            print(f"\n{ask(client, messages)}\n")
        except anthropic.AuthenticationError:
            sys.exit("That API key was rejected. Check ANTHROPIC_API_KEY in your .env file.")
        except anthropic.APIError as e:
            print(f"\nAPI error: {e}\n")


if __name__ == "__main__":
    main()
