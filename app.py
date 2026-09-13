"""
Desktop AI Assistant — Flask + browser UI on top of a local Ollama model.

Run:
    pip install flask requests
    ollama pull gemma4:e2b        # or any model you prefer
    python app.py

Then open http://127.0.0.1:5000 in your browser.
"""

from flask import Flask, request, jsonify, render_template, Response, stream_with_context
import requests
import json

app = Flask(__name__)

# ---- Configuration -----------------------------------------------------
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "gemma4:e2b"      # swap for phi4-mini / llama3.2:3b / qwen3.5:4b etc.
MAX_CONTEXT_TOKENS = 2048       # keep small — this is what matters most on 8GB RAM
MAX_HISTORY_MESSAGES = 12       # trim old turns so requests stay cheap
KEEP_ALIVE = "5m"               # unload the model from RAM after 5 min idle

SYSTEM_PROMPT = (
    "You are a concise, helpful desktop assistant running locally on the "
    "user's machine. Keep answers short unless asked for detail."
)

# ---- In-memory conversation state --------------------------------------
# Single-user, single-session assistant — a plain list is enough.
# For multi-tab use you'd key this by a session id instead.
conversation = [{"role": "system", "content": SYSTEM_PROMPT}]


def trim_history():
    """Keep the system prompt plus the most recent N messages, so the
    request we send to Ollama — and therefore its RAM/CPU cost — stays
    bounded regardless of how long the chat has gone on."""
    global conversation
    if len(conversation) > MAX_HISTORY_MESSAGES + 1:
        conversation = [conversation[0]] + conversation[-MAX_HISTORY_MESSAGES:]


@app.route("/")
def index():
    return render_template("index.html", model_name=MODEL_NAME)


@app.route("/api/send", methods=["POST"])
def send():
    """Stream the model's reply back to the browser token-by-token so the
    UI feels responsive even on a slow CPU-only box."""
    user_message = request.json.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "empty message"}), 400

    conversation.append({"role": "user", "content": user_message})
    trim_history()

    payload = {
        "model": MODEL_NAME,
        "messages": conversation,
        "stream": True,
        "keep_alive": KEEP_ALIVE,
        "options": {"num_ctx": MAX_CONTEXT_TOKENS},
    }

    def generate():
        full_reply = ""
        try:
            with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=120) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    piece = chunk.get("message", {}).get("content", "")
                    if piece:
                        full_reply += piece
                        yield f"data: {json.dumps({'token': piece})}\n\n"
                    if chunk.get("done"):
                        break
        except requests.exceptions.ConnectionError:
            yield f"data: {json.dumps({'error': 'Cannot reach Ollama. Is it running? (ollama serve)'})}\n\n"
            return
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        conversation.append({"role": "assistant", "content": full_reply})
        trim_history()
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/api/reset", methods=["POST"])
def reset():
    global conversation
    conversation = [{"role": "system", "content": SYSTEM_PROMPT}]
    return jsonify({"ok": True})


if __name__ == "__main__":
    # debug=False, single-threaded is fine for a personal local assistant
    app.run(host="127.0.0.1", port=5000, debug=False)
