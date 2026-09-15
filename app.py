"""Minimal web UI for the time agent. Run: .venv/bin/python app.py -> http://localhost:5001"""

import openai
from flask import Flask, jsonify, render_template, request

from local_agent import BASE_URL, MODEL, SYSTEM_PROMPT, ask

app = Flask(__name__)

client = openai.OpenAI(base_url=BASE_URL, api_key="not-needed")
model = MODEL or client.models.list().data[0].id

# Conversation history, kept in memory. Single user, single conversation -- this is a
# local dev tool, not a deployed app.
messages = [{"role": "system", "content": SYSTEM_PROMPT}]


@app.route("/")
def index():
    return render_template("index.html", model=model.split("/")[-1])


@app.post("/chat")
def chat():
    user_input = (request.json or {}).get("message", "").strip()
    if not user_input:
        return jsonify({"error": "empty message"}), 400

    messages.append({"role": "user", "content": user_input})
    tool_calls = []

    def record(name, args):
        rendered = ", ".join(f"{k}={v!r}" for k, v in args.items())
        tool_calls.append(f"{name}({rendered})")

    try:
        reply = ask(client, model, messages, on_tool=record)
    except openai.APIError as e:
        # Drop the failed turn so a server error doesn't poison the history.
        del messages[len(messages) - 1 :]
        return jsonify({"error": str(e)}), 502

    return jsonify({"reply": reply, "tools": tool_calls})


@app.post("/reset")
def reset():
    """Clear history. The 8192-token context fills up fast, so this gets used."""
    del messages[1:]
    return jsonify({"ok": True})


if __name__ == "__main__":
    print(f"Agent UI -> http://localhost:5001  (model: {model.split('/')[-1]})")
    app.run(port=5001, debug=False)
