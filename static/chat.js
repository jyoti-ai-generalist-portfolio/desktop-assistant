const chatWindow = document.getElementById("chat-window");
const inputBox = document.getElementById("input-box");
const sendBtn = document.getElementById("send-btn");
const resetBtn = document.getElementById("reset-btn");

function addMessage(text, role) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  return div;
}

// auto-grow the textarea a little as the user types
inputBox.addEventListener("input", () => {
  inputBox.style.height = "auto";
  inputBox.style.height = Math.min(inputBox.scrollHeight, 120) + "px";
});

inputBox.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
sendBtn.addEventListener("click", sendMessage);

resetBtn.addEventListener("click", async () => {
  await fetch("/api/reset", { method: "POST" });
  chatWindow.innerHTML = "";
});

async function sendMessage() {
  const text = inputBox.value.trim();
  if (!text) return;

  addMessage(text, "user");
  inputBox.value = "";
  inputBox.style.height = "auto";
  sendBtn.disabled = true;

  const aiDiv = addMessage("", "ai");
  let receivedAny = false;

  try {
    const resp = await fetch("/api/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE messages are separated by double newlines
      const parts = buffer.split("\n\n");
      buffer = parts.pop(); // keep incomplete chunk for next read

      for (const part of parts) {
        if (!part.startsWith("data: ")) continue;
        const data = JSON.parse(part.slice(6));

        if (data.error) {
          aiDiv.textContent = "⚠ " + data.error;
          aiDiv.className = "msg error";
        } else if (data.token) {
          receivedAny = true;
          aiDiv.textContent += data.token;
          chatWindow.scrollTop = chatWindow.scrollHeight;
        }
      }
    }
  } catch (err) {
    aiDiv.textContent = "⚠ Connection error: " + err.message;
    aiDiv.className = "msg error";
  }

  if (!receivedAny && aiDiv.textContent === "") {
    aiDiv.textContent = "⚠ No response received.";
    aiDiv.className = "msg error";
  }

  sendBtn.disabled = false;
  inputBox.focus();
}
