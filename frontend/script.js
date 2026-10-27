
const form = document.getElementById("chat-form");
const input = document.getElementById("message-input");
const messages = document.getElementById("messages");

const conversationHistory = [];

form.addEventListener("submit", async function (event) {
    event.preventDefault();

    const message = input.value.trim();

    if (!message) return;

    const userMessage = document.createElement("div");
    userMessage.className = "message user-message";

    const userLabel = document.createElement("strong");
    userLabel.textContent = "You";

    const userText = document.createElement("div");
    userText.className = "reply-text";
    userText.textContent = message;

    userMessage.appendChild(userLabel);
    userMessage.appendChild(userText);
    messages.appendChild(userMessage);

    conversationHistory.push({
        role: "user",
        content: message
    });

    input.value = "";
    input.focus();

    const loading = document.createElement("div");
    loading.className = "message ai-message";
    loading.textContent = "VIRTANSAN AI is thinking...";
    messages.appendChild(loading);

    messages.scrollTop = messages.scrollHeight;

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message: message,
                history: conversationHistory.slice(-12)
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "Request failed.");
        }

        loading.remove();

        const replyText =
            data.reply || "I'm sorry, I couldn't prepare a response.";

        const aiMessage = document.createElement("div");
        aiMessage.className = "message ai-message";

        const aiLabel = document.createElement("strong");
        aiLabel.textContent = "VIRTANSAN AI";

        const reply = document.createElement("div");
        reply.className = "reply-text";
        reply.textContent = replyText;

        aiMessage.appendChild(aiLabel);
        aiMessage.appendChild(reply);
        messages.appendChild(aiMessage);

        conversationHistory.push({
            role: "assistant",
            content: replyText
        });

    } catch (error) {
        loading.textContent =
            "Sorry, something went wrong: " + error.message;
    }

    messages.scrollTop = messages.scrollHeight;
});
