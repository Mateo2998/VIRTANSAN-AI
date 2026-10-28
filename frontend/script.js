
document.addEventListener("DOMContentLoaded", function () {
    const chatToggle = document.getElementById("chatToggle");
    const chatPanel = document.getElementById("chatPanel");
    const chatClose = document.getElementById("chatClose");
    const chatForm = document.getElementById("chatForm");
    const chatInput = document.getElementById("chatInput");
    const chatMessages = document.getElementById("chatMessages");
    const sendButton = document.getElementById("sendButton");

    const humanSupportArea = document.getElementById("humanSupportArea");
    const humanSupportButton = document.getElementById("humanSupportButton");
    const humanSupportStatus = document.getElementById("humanSupportStatus");

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

    const year = document.getElementById("year");

    let loginMode = "employee";
    let conversationHistory = [];
    let humanStatus = "none";
    let isSending = false;
    let isRequestingHuman = false;
    let humanSupportRequested = false;

    let conversationId =
        "conv-" +
        Date.now() +
        "-" +
        Math.random().toString(36).slice(2, 10);

    localStorage.setItem("aihas_conversation_id", conversationId);

    if (year) {
        year.textContent = new Date().getFullYear();
    }

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

        checkHumanStatus();
    }

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

    function wantsHumanSupport(message) {
        return /\b(human|real person|live agent|human agent|human assistant|human support|talk to someone|speak to someone|talk to a person|speak to a person|customer service|support agent|real agent|talk to human|speak to human|contact a human|request human|person to help me|speak with someone|talk with someone)\b/i.test(message);
    }

    function showHumanSupportButton() {
        humanSupportRequested = true;

        if (humanSupportArea) {
            humanSupportArea.style.display = "block";
        } else if (humanSupportButton) {
            humanSupportButton.style.display = "inline-flex";
        }

        if (humanSupportStatus && humanStatus === "none") {
            humanSupportStatus.textContent =
                "You can request a human support agent using the button above.";
        }
    }

    function hideHumanSupportButton() {
        if (humanSupportArea) {
            humanSupportArea.style.display = "none";
        } else if (humanSupportButton) {
            humanSupportButton.style.display = "none";
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

    ["heroSupport", "bandSupport"].forEach(function (id) {
        const button = document.getElementById(id);

        if (button) {
            button.addEventListener("click", openChat);
        }
    });

    function addMessage(message, sender, isError = false) {
        if (!chatMessages) return null;

        const element = document.createElement("div");
        element.className = "message " + sender;
        element.textContent = message;

        if (isError) {
            element.classList.add("error");
        }

        chatMessages.appendChild(element);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        return element;
    }

    function setHumanStatus(status, message) {
        humanStatus = status;

        if (humanSupportStatus) {
            humanSupportStatus.textContent = message || "";
        }

        if (status === "pending" || status === "accepted") {
            showHumanSupportButton();
        }

        if (!humanSupportButton) return;

        if (status === "pending") {
            humanSupportButton.disabled = true;
            humanSupportButton.textContent = "Waiting for an administrator...";
        } else if (status === "accepted") {
            humanSupportButton.disabled = true;
            humanSupportButton.textContent = "Human Support Connected";
        } else if (status === "completed") {
            humanSupportButton.disabled = false;
            humanSupportButton.textContent = "Request Human Support";
        } else if (status === "declined") {
            humanSupportButton.disabled = false;
            humanSupportButton.textContent = "Request Human Support";
        } else {
            humanSupportButton.disabled = false;
            humanSupportButton.textContent = "Request Human Support";
        }

        if (chatInput) {
            chatInput.placeholder = status === "accepted"
                ? "Message your support agent..."
                : "Describe your IT issue...";
        }
    }

    const displayedHumanMessages = new Set();

    function displayHumanMessages(messages) {
        if (!Array.isArray(messages)) return;

        messages.forEach(function (item, index) {
            const message = typeof item === "string"
                ? item
                : item.message || item.text || "";

            if (!message) return;

            const id = typeof item === "object" && item.id !== undefined
                ? String(item.id)
                : index + ":" + message;

            if (displayedHumanMessages.has(id)) return;

            displayedHumanMessages.add(id);

            const sender = typeof item === "object"
                ? String(item.sender || item.from || "admin").toLowerCase()
                : "admin";

            if (sender === "user" || sender === "employee") return;

            addMessage(message, "bot");
        });
    }

    async function checkHumanStatus() {
        try {
            const response = await fetch(
                "/human/status/" + encodeURIComponent(conversationId),
                {
                    method: "GET",
                    credentials: "same-origin"
                }
            );

            if (!response.ok) return;

            const data = await response.json();
            const status = String(data.status || "none").toLowerCase();

            if (Array.isArray(data.messages)) {
                displayHumanMessages(data.messages);
            }

            if (status === "pending") {
                setHumanStatus(
                    "pending",
                    "Your request has been sent. Please wait for an administrator."
                );
            } else if (status === "accepted") {
                if (humanStatus !== "accepted") {
                    addMessage(
                        "A human support agent has accepted your request. You can now chat with them.",
                        "bot"
                    );
                }

                setHumanStatus(
                    "accepted",
                    "A human support agent is handling this conversation."
                );
            } else if (status === "declined") {
                if (humanStatus !== "declined") {
                    addMessage(
                        data.message ||
                        "Sorry, no administrator is available right now. You can request human support again later.",
                        "bot"
                    );
                }

                setHumanStatus(
                    "declined",
                    "Your request was declined. You can request support again."
                );
            } else if (status === "completed") {
                if (humanStatus !== "completed") {
                    addMessage(
                        "The human support session has ended. You can continue using the AI assistant or request human support again.",
                        "bot"
                    );
                }

                setHumanStatus(
                    "completed",
                    "The human support session has ended."
                );
            } else {
                setHumanStatus("none", "");
            }
        } catch (error) {
            console.error("Human support status error:", error);
        }
    }

    async function requestHumanSupport() {
        if (
            isRequestingHuman ||
            humanStatus === "pending" ||
            humanStatus === "accepted"
        ) {
            return;
        }

        isRequestingHuman = true;

        if (humanSupportButton) {
            humanSupportButton.disabled = true;
            humanSupportButton.textContent = "Sending request...";
        }

        if (humanSupportStatus) {
            humanSupportStatus.textContent = "Sending your request...";
        }

        try {
            const response = await fetch("/human/request", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                credentials: "same-origin",
                body: JSON.stringify({
                    conversation_id: conversationId,
                    history: conversationHistory
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(
                    data.detail || "Unable to request human support."
                );
            }

            showHumanSupportButton();

            addMessage(
                data.message ||
                "Your human-support request has been submitted. Please wait for an administrator.",
                "bot"
            );

            setHumanStatus(
                data.status || "pending",
                "Your request has been sent. Please wait for an administrator."
            );

            await checkHumanStatus();
        } catch (error) {
            console.error("Human support request error:", error);

            addMessage(
                error.message || "Unable to request human support. Please try again.",
                "bot",
                true
            );

            setHumanStatus(
                "none",
                "Unable to send the request. Please try again."
            );

            showHumanSupportButton();
        } finally {
            isRequestingHuman = false;

            if (
                humanSupportButton &&
                humanStatus !== "pending" &&
                humanStatus !== "accepted"
            ) {
                humanSupportButton.disabled = false;
                humanSupportButton.textContent = "Request Human Support";
            }
        }
    }

    if (humanSupportButton) {
        humanSupportButton.addEventListener("click", requestHumanSupport);
    }

    async function sendHumanMessage(message) {
        const response = await fetch("/human/message", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            credentials: "same-origin",
            body: JSON.stringify({
                conversation_id: conversationId,
                message: message
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.detail || "Unable to send your message to human support."
            );
        }
    }

    if (chatForm && chatInput) {
        chatForm.addEventListener("submit", async function (event) {
            event.preventDefault();

            const message = chatInput.value.trim();

            if (!message || isSending) return;

            if (wantsHumanSupport(message)) {
                showHumanSupportButton();
            }

            addMessage(message, "user");
            chatInput.value = "";
            chatInput.disabled = true;
            isSending = true;

            if (sendButton) {
                sendButton.disabled = true;
            }

            const loadingMessage = addMessage("Thinking...", "bot");

            try {
                await checkHumanStatus();

                if (humanStatus === "pending") {
                    if (loadingMessage) {
                        loadingMessage.textContent =
                            "Your request is waiting for an administrator. You can continue once the request has been reviewed.";
                    }
                    return;
                }

                if (humanStatus === "accepted") {
                    if (loadingMessage) {
                        loadingMessage.textContent = "Sending to human support...";
                    }

                    try {
                        await sendHumanMessage(message);

                        if (loadingMessage && loadingMessage.parentNode) {
                            loadingMessage.remove();
                        }
                    } catch (error) {
                        if (loadingMessage) {
                            loadingMessage.textContent =
                                error.message || "Unable to send your message.";
                            loadingMessage.classList.add("error");
                        }
                    }

                    return;
                }

                const response = await fetch("/chat", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    credentials: "same-origin",
                    body: JSON.stringify({
                        message: message,
                        history: conversationHistory,
                        conversation_id: conversationId
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

                conversationHistory.push(
                    { role: "user", content: message },
                    { role: "assistant", content: reply }
                );

                conversationHistory = conversationHistory.slice(-12);
            } catch (error) {
                if (loadingMessage) {
                    loadingMessage.textContent =
                        error.message ||
                        "Unable to connect to the AI helpdesk. Please try again.";

                    loadingMessage.classList.add("error");
                }

                console.error("Chat error:", error);
            } finally {
                chatInput.disabled = false;
                isSending = false;

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

    // Employee and admin login are both connected to the backend.
    if (loginForm) {
        loginForm.addEventListener("submit", async function (event) {
            event.preventDefault();

            const email = loginEmail.value.trim();
            const password = loginPassword.value;

            loginMessage.textContent = "Checking credentials...";
            loginSubmit.disabled = true;

            const endpoint = loginMode === "admin"
                ? "/admin-login"
                : "/employee-login";

            try {
                const response = await fetch(endpoint, {
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

                window.location.href = loginMode === "admin"
                    ? "/admin.html"
                    : "/employee.html";

            } catch (error) {
                loginMessage.textContent =
                    error.message || "Login failed. Please try again.";

                console.error("Login error:", error);
            } finally {
                loginSubmit.disabled = false;
            }
        });
    }

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

    document.addEventListener("keydown", function (event) {
        if (event.key !== "Escape") return;

        if (loginBackdrop && loginBackdrop.classList.contains("open")) {
            closeLogin();
        } else if (chatPanel && chatPanel.classList.contains("open")) {
            closeChat();
        }
    });

    hideHumanSupportButton();
    checkHumanStatus();

    setInterval(checkHumanStatus, 4000);
});
