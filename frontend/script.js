
document.addEventListener("DOMContentLoaded", function () {
    // Chatbot elements
    const chatToggle = document.getElementById("chatToggle");
    const chatPanel = document.getElementById("chatPanel");
    const chatClose = document.getElementById("chatClose");
    const chatForm = document.getElementById("chatForm");
    const chatInput = document.getElementById("chatInput");
    const chatMessages = document.getElementById("chatMessages");
    const sendButton = document.getElementById("sendButton");

    // Login elements
    const loginOpen = document.getElementById("loginOpen");
    const loginBackdrop = document.getElementById("loginBackdrop");
    const loginClose = document.getElementById("loginClose");
    const loginForm = document.getElementById("loginForm");
    const loginEmail = document.getElementById("loginEmail");
    const loginPassword = document.getElementById("loginPassword");
    const loginMessage = document.getElementById("loginMessage");
    const loginModeButton = document.getElementById("loginModeButton");
    const loginTitle = document.getElementById("loginTitle");
    const loginDescription = document.getElementById("loginDescription");
    const loginEmailLabel = document.getElementById("loginEmailLabel");
    const loginSubmit = document.getElementById("loginSubmit");

    let loginMode = "employee";

    // Store chatbot conversation history
    let conversationHistory = [];

    // Display the current year
    const year = document.getElementById("year");

    if (year) {
        year.textContent = new Date().getFullYear();
    }

    // Open chatbot
    function openChat() {
        if (!chatPanel) return;

        chatPanel.classList.add("open");
        chatPanel.setAttribute("aria-hidden", "false");
        chatPanel.removeAttribute("inert");

        if (chatToggle) {
            chatToggle.setAttribute("aria-expanded", "true");
        }

        if (chatInput) {
            chatInput.focus();
        }
    }

    // Close chatbot
    function closeChat() {
        if (!chatPanel) return;

        chatPanel.classList.remove("open");
        chatPanel.setAttribute("aria-hidden", "true");
        chatPanel.setAttribute("inert", "");

        if (chatToggle) {
            chatToggle.setAttribute("aria-expanded", "false");
            chatToggle.focus();
        }
    }

    if (chatToggle) {
        chatToggle.addEventListener("click", function () {
            if (chatPanel.classList.contains("open")) {
                closeChat();
            } else {
                openChat();
            }
        });
    }

    if (chatClose) {
        chatClose.addEventListener("click", closeChat);
    }

    // Connect the support buttons
    ["heroSupport", "bandSupport"].forEach(function (id) {
        const button = document.getElementById(id);

        if (button) {
            button.addEventListener("click", openChat);
        }
    });

    // Add chatbot message
    function addMessage(message, sender, isError = false) {
        if (!chatMessages) return null;

        const element = document.createElement("div");
        element.className = "message " + sender;

        if (isError) {
            element.classList.add("error");
        }

        element.textContent = message;
        chatMessages.appendChild(element);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        return element;
    }

    // Send message to the AI backend
    if (chatForm && chatInput) {
        chatForm.addEventListener("submit", async function (event) {
            event.preventDefault();

            const message = chatInput.value.trim();

            if (!message) return;

            addMessage(message, "user");
            chatInput.value = "";
            chatInput.disabled = true;

            if (sendButton) {
                sendButton.disabled = true;
            }

            const loadingMessage = addMessage("Thinking...", "bot");

            try {
                const response = await fetch("/chat", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        message: message,
                        history: conversationHistory
                    })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(
                        data.detail || "The AI helpdesk request failed."
                    );
                }

                const reply = data.reply || "No response was returned.";

                if (loadingMessage) {
                    loadingMessage.textContent = reply;
                }

                // Save the conversation for follow-up questions
                conversationHistory.push(
                    {
                        role: "user",
                        content: message
                    },
                    {
                        role: "assistant",
                        content: reply
                    }
                );

                // Keep the latest 12 messages
                conversationHistory = conversationHistory.slice(-12);

            } catch (error) {
                if (loadingMessage) {
                    loadingMessage.textContent =
                        "Unable to connect to the AI helpdesk. Please try again.";
                    loadingMessage.classList.add("error");
                }

                console.error("Chat error:", error);
            } finally {
                chatInput.disabled = false;

                if (sendButton) {
                    sendButton.disabled = false;
                }

                if (chatMessages) {
                    chatMessages.scrollTop = chatMessages.scrollHeight;
                }

                chatInput.focus();
            }
        });
    }

    // Open login popup
    function openLogin() {
        if (!loginBackdrop) return;

        loginBackdrop.classList.add("open");
        loginBackdrop.setAttribute("aria-hidden", "false");
        loginBackdrop.removeAttribute("inert");

        if (loginMessage) {
            loginMessage.textContent = "";
        }

        if (loginEmail) {
            loginEmail.focus();
        }
    }

    // Close login popup
    function closeLogin() {
        if (!loginBackdrop) return;

        loginBackdrop.classList.remove("open");
        loginBackdrop.setAttribute("aria-hidden", "true");
        loginBackdrop.setAttribute("inert", "");

        if (loginForm) {
            loginForm.reset();
        }

        if (loginMessage) {
            loginMessage.textContent = "";
        }

        if (loginOpen) {
            loginOpen.focus();
        }
    }

    if (loginOpen) {
        loginOpen.addEventListener("click", openLogin);
    }

    if (loginClose) {
        loginClose.addEventListener("click", closeLogin);
    }

    if (loginBackdrop) {
        loginBackdrop.addEventListener("click", function (event) {
            if (event.target === loginBackdrop) {
                closeLogin();
            }
        });
    }

    // Switch between employee and admin login
    if (loginModeButton) {
        loginModeButton.addEventListener("click", function () {
            loginMode = loginMode === "employee" ? "admin" : "employee";

            if (loginMode === "admin") {
                loginTitle.textContent = "Admin Login";
                loginDescription.textContent =
                    "Sign in with your administrator credentials.";
                loginEmailLabel.textContent = "Admin email";
                loginEmail.placeholder = "admin@work.com";
                loginModeButton.textContent = "Switch to Employee Login";
                loginSubmit.textContent = "Admin Login";
            } else {
                loginTitle.textContent = "Welcome back";
                loginDescription.textContent =
                    "Sign in to access the company portal.";
                loginEmailLabel.textContent = "Company email";
                loginEmail.placeholder = "name@company.com";
                loginModeButton.textContent = "Admin Login";
                loginSubmit.textContent = "Log in";
            }

            if (loginForm) {
                loginForm.reset();
            }

            if (loginMessage) {
                loginMessage.textContent = "";
            }
        });
    }

    // Submit admin login
    if (loginForm) {
        loginForm.addEventListener("submit", async function (event) {
            event.preventDefault();

            if (loginMode !== "admin") {
                loginMessage.textContent =
                    "Employee login is not connected yet. Please use Admin Login.";
                return;
            }

            const email = loginEmail.value.trim();
            const password = loginPassword.value;

            loginMessage.textContent = "Checking credentials...";
            loginSubmit.disabled = true;

            try {
                const response = await fetch("/admin-login", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    credentials: "same-origin",
                    body: JSON.stringify({
                        email: email,
                        password: password
                    })
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(
                        data.detail || "Invalid email or password."
                    );
                }

                window.location.href = "/admin.html";
            } catch (error) {
                loginMessage.textContent =
                    error.message || "Login failed. Please try again.";

                console.error("Admin login error:", error);
            } finally {
                loginSubmit.disabled = false;
            }
        });
    }

    // Admin logout
    const logoutButton = document.getElementById("logoutButton");

    if (logoutButton) {
        logoutButton.addEventListener("click", async function () {
            logoutButton.disabled = true;

            try {
                const response = await fetch("/admin-logout", {
                    method: "POST",
                    credentials: "same-origin"
                });

                if (!response.ok) {
                    throw new Error("Logout failed.");
                }

                window.location.href = "/";
            } catch (error) {
                console.error("Logout error:", error);
                alert("Unable to log out. Please try again.");
                logoutButton.disabled = false;
            }
        });
    }

    // Close open popup with Escape
    document.addEventListener("keydown", function (event) {
        if (event.key !== "Escape") return;

        if (loginBackdrop && loginBackdrop.classList.contains("open")) {
            closeLogin();
        } else if (chatPanel && chatPanel.classList.contains("open")) {
            closeChat();
        }
    });
});
