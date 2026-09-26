# TODO

Planned and proposed work. Each item stays here while it's discussed; once decided it moves
to **Done** or **Decided against**, with the reason, so the thinking isn't lost.

**Status:** `proposed` (idea, not yet discussed) · `discussing` · `accepted` (will do) ·
`in progress` · `done` · `rejected`

---

## Context and memory

### Background

"The model has no memory" (see README) covers three separate problems:

1. **Resending costs.** Sending the full `messages` list every round is how all chat APIs
   work. Prompt caching softens the cost: llama-server reuses its computed state for the
   unchanged start of the prompt, so each round mostly processes only the new messages.
   Claude and OpenAI sell the same thing as "prompt caching".
2. **The context fills up.** The 8192-token window overflows after a few questions in the
   web UI. This is the problem we actually hit.
3. **Nothing persists across sessions.** Restarting the server forgets everything.
   "Persistent memory" solves this by storing facts outside the model and copying relevant
   ones back into the prompt. It doesn't reduce what is sent.

### 1. Measure what fills the context
**Status:** `proposed`

Run `trace_agent.py` over a few follow-up questions and see where the tokens go before
changing anything. Two things to check:
- Whether gpt-oss's hidden reasoning text is saved into `messages` (`local_agent.py:117`
  stores the reply as returned) and resent on every later round.
- Whether llama-server's prompt cache is actually being hit. Its response reports how many
  prompt tokens it had to process.

### 2. Clear old tool results after each answered question
**Status:** `proposed`

Once a question is answered, its tool calls and results are dead weight: the coordinates
aren't needed again. Keep only the user question and the final answer. That turns about 7
messages per question into 2, roughly a 3× saving, with almost no loss. It's about 10 lines
in `ask()`. Claude Code and Anthropic's API call this "compaction" / "context editing".

- Open question: apply it in `ask()` (all entry points) or only in `app.py`?

### 3. Sliding window as a safety net
**Status:** `proposed`

Keep the system prompt plus the last N exchanges and drop older ones whole, so the list can
never overflow even after #2. Drop complete exchanges only: an assistant `tool_calls` message
must never be separated from its `role: "tool"` results, or the server rejects the request.

- Open question: count exchanges, or count tokens?

### 4. Persistent memory via `remember` / `recall` tools
**Status:** `proposed`

Add two tools that save facts to a JSON file and read them back, so the agent can remember
things like "my home city is Baton Rouge" across restarts. It fits the project's idea that
tools are plain Python functions. This is a new feature, not a fix for the overflow.

- Open questions: should the model decide what to remember, or only save when the user says
  "remember…"? Load all facts into the system prompt, or only when `recall` is called?

### Considered, not planned yet

- **Bigger context:** start llama-server with a larger `-c`. It's trivial but costs RAM, and
  it delays the problem rather than fixing it.
- **Summarizing old history:** have the model summarize the older part of the conversation.
  It costs an extra model call per summary; worth it only if #2 and #3 aren't enough.
- **Retrieval (RAG), MemGPT/Letta, Mem0:** research-grade memory systems. They're overkill
  at this project's size, but useful references if #4 grows.

---

## Done

_Nothing yet._

## Decided against

_Nothing yet._
