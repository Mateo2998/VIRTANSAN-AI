
const form = document.getElementById("chat-form");
const input = document.getElementById("message-input");
const messages = document.getElementById("messages");

form.addEventListener("submit", async function (event) {
    event.preventDefault();

    const message = input.value.trim();

    if (!message) return;

    messages.innerHTML += `<p><strong>You:</strong> ${escapeHTML(message)}</p>`;
    input.value = "";

    const loading = document.createElement("p");
    loading.textContent = "VIRTANSAN AI is responding...";
    messages.appendChild(loading);

    try {
        const response = await fetch("http://127.0.0.1:8000/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ message: message })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "Request failed.");
        }

        loading.remove();

        const reply = document.createElement("p");
        reply.textContent = "VIRTANSAN AI: " + data.reply;
        messages.appendChild(reply);

        const source = document.createElement("p");
        source.className = "source";
        source.textContent = "Source: " + data.source;
        messages.appendChild(source);

    } catch (error) {
        loading.textContent = "Error: " + error.message;
    }
});

function escapeHTML(text) {
    const element = document.createElement("span");
    element.textContent = text;
    return element.innerHTML;
}
