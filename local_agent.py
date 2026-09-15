"""The same time agent, driven by a local model over an OpenAI-compatible endpoint.

Works with LM Studio, llama.cpp's server, Ollama, vLLM -- anything exposing
/v1/chat/completions. Set LOCAL_BASE_URL and LOCAL_MODEL in .env to point it elsewhere.
"""

import json
import os
import sys

import openai
from dotenv import load_dotenv

from time_tools import geocode_location, get_time_at_coordinates

load_dotenv()

# Any OpenAI-compatible server. Override in .env if yours isn't local, e.g. a
# llama-server on another machine: LOCAL_BASE_URL=http://my-box:8080/v1
BASE_URL = os.environ.get("LOCAL_BASE_URL", "http://localhost:8080/v1")
# llama-server serves whichever model it was launched with and ignores this field,
# so leave it unset and let main() discover the served model.
MODEL = os.environ.get("LOCAL_MODEL", "")

SYSTEM_PROMPT = """You are a time assistant. You answer questions about the current \
local time in places around the world.

You have two tools. To find the time in a place, you must use both, in order:
1. Call geocode_location with the place name to get its latitude and longitude.
2. Call get_time_at_coordinates with those exact coordinates to get the time.

Never guess coordinates or times -- always call the tools. After the second tool returns, \
answer in one or two sentences."""

# Unlike the Anthropic SDK's @beta_tool decorator, the OpenAI-compatible API has no
# schema generator, so each tool is described by hand. The "description" fields are
# what the model reads when deciding what to call.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "geocode_location",
            "description": "Look up the latitude and longitude of a place from its name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location_name": {
                        "type": "string",
                        "description": 'A place name, e.g. "Paris" or "Grand Canyon".',
                    }
                },
                "required": ["location_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time_at_coordinates",
            "description": "Get the current local time at a latitude/longitude pair.",
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "description": "Latitude in decimal degrees."},
                    "longitude": {"type": "number", "description": "Longitude in decimal degrees."},
                },
                "required": ["latitude", "longitude"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "geocode_location": geocode_location,
    "get_time_at_coordinates": get_time_at_coordinates,
}

MAX_STEPS = 6  # stop a confused model from looping forever


def print_tool_call(name: str, args: dict) -> None:
    """Default tool reporter: dim line on stdout, for the CLI."""
    rendered = ", ".join(f"{k}={v!r}" for k, v in args.items())
    print(f"  \033[2m-> {name}({rendered})\033[0m")


def run_tool(call, on_tool=print_tool_call) -> str:
    """Execute one tool call, returning the result (or the error) as a string."""
    function = TOOL_FUNCTIONS.get(call.function.name)
    if function is None:
        return f"Error: no tool named {call.function.name}."
    try:
        args = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        return f"Error: arguments were not valid JSON: {call.function.arguments!r}"

    on_tool(call.function.name, args)
    try:
        return str(function(**args))
    except TypeError as e:
        return f"Error: wrong arguments for {call.function.name}: {e}"


def ask(client: openai.OpenAI, model: str, messages: list, on_tool=print_tool_call) -> str:
    """Run the agent loop until the model answers instead of calling a tool.

    on_tool(name, args) is called for each tool call, so a UI can display them.
    """
    for _ in range(MAX_STEPS):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOL_SCHEMAS,
            temperature=0.2,
        )
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            return message.content or "(empty response)"

        for call in message.tool_calls:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": run_tool(call, on_tool),
                }
            )

    return f"(gave up after {MAX_STEPS} steps without a final answer)"


def main() -> None:
    # Local servers ignore the key, but the client requires one to be present.
    client = openai.OpenAI(base_url=BASE_URL, api_key="not-needed")

    try:
        available = [m.id for m in client.models.list().data]
    except openai.APIConnectionError:
        sys.exit(f"No server reachable at {BASE_URL}. Start it, or set LOCAL_BASE_URL in .env.")

    if not available:
        sys.exit(f"{BASE_URL} has no model loaded.")
    # Use the configured model if set, else whatever the server is actually serving.
    model = MODEL or available[0]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print(f"Time agent on {os.path.basename(model)} via {BASE_URL}. Ctrl-C or 'quit' to exit.\n")

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
            print(f"\n{ask(client, model, messages)}\n")
        except openai.APIError as e:
            print(f"\nServer error: {e}\n")


if __name__ == "__main__":
    main()
