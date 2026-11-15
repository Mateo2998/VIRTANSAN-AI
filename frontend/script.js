
document.addEventListener("DOMContentLoaded", function () {
    // ==========================================
    // ELEMENTS
    // ==========================================

    const chatToggle = document.getElementById("chatToggle");
    const chatPanel = document.getElementById("chatPanel");
    const chatClose = document.getElementById("chatClose");
    const chatForm = document.getElementById("chatForm");
    const chatInput = document.getElementById("chatInput");
    const chatMessages = document.getElementById("chatMessages");
    const sendButton = document.getElementById("sendButton");

    const chatSubtitle = document.getElementById("chatSubtitle");
    const chatNote = document.getElementById("chatNote");

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
    const loginPasswordReset = document.getElementById("loginPasswordReset");

    const resetBackdrop = document.getElementById("resetBackdrop");
    const resetClose = document.getElementById("resetClose");
    const resetForm = document.getElementById("resetForm");
    const resetEmail = document.getElementById("resetEmail");
    const resetDescriptionInput = document.getElementById("resetDescriptionInput");
    const resetConfirmation = document.getElementById("resetConfirmation");
    const resetSubmit = document.getElementById("resetSubmit");
    const resetMessage = document.getElementById("resetMessage");

    const employeeLogout = document.getElementById("employeeLogout");
    const footerLogin = document.getElementById("footerLogin");

    const year = document.getElementById("year");

    // ==========================================
    // APPLICATION STATE
    // ==========================================

    let loginMode = "employee";
    let userMode = "public";
    let employeeDetails = null;

    let conversationHistory = [];
    let humanStatus = "none";

    let isSending = false;
    let isRequestingHuman = false;
    let isSubmittingReset = false;

    let resetActionDisplayed = false;

    let conversationId =
        localStorage.getItem("aihas_conversation_id");

    if (!conversationId) {
        conversationId = createRequestId();
        localStorage.setItem("aihas_conversation_id", conversationId);
    }

    const displayedHumanMessages = new Set();

    // ==========================================
    // GENERAL HELPERS
    // ==========================================

    function createRequestId() {
        if (window.crypto && typeof window.crypto.randomUUID === "function") {
            return window.crypto.randomUUID();
        }

        return "request-" +
            Date.now() +
            "-" +
            Math.random().toString(36).slice(2, 12);
    }

    async function readResponse(response) {
        let data = {};

        try {
            data = await response.json();
        } catch (error) {
            data = {};
        }

        if (!response.ok) {
            throw new Error(
                data.detail ||
                data.message ||
                "The request could not be completed."
            );
        }

        return data;
    }

    function setButtonLoading(button, loading, loadingText, normalText) {
        if (!button) return;

        button.disabled = loading;
        button.textContent = loading ? loadingText : normalText;
    }

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

    function clearChatMessages() {
        if (chatMessages) {
            chatMessages.innerHTML = "";
        }

        conversationHistory = [];
        resetActionDisplayed = false;
    }

    function resetConversation() {
        conversationHistory = [];
        humanStatus = "none";
        displayedHumanMessages.clear();
        resetActionDisplayed = false;

        conversationId = createRequestId();

        localStorage.setItem("aihas_conversation_id", conversationId);

        if (humanSupportStatus) {
            humanSupportStatus.textContent = "";
        }

        if (humanSupportButton) {
            humanSupportButton.disabled = false;
            humanSupportButton.textContent = "Request Human Support";
        }

        hideHumanSupportButton();
    }

    // ==========================================
    // PASSWORD RESET INTENT DETECTION
    // ==========================================

    function wantsPasswordReset(message) {
        const text = message.toLowerCase().trim();

        const resetPatterns = [
            /\bforgot\b.*\bpassword\b/i,
            /\bpassword\b.*\bforgot\b/i,
            /\breset\b.*\bpassword\b/i,
            /\bpassword\b.*\breset\b/i,
            /\bchange\b.*\bpassword\b/i,
            /\bpassword\b.*\bchange\b/i,
            /\bcan't\b.*\blog\s*in\b/i,
            /\bcannot\b.*\blog\s*in\b/i,
            /\bunable\b.*\blog\s*in\b/i,
            /\bcan't\b.*\bsign\s*in\b/i,
            /\bcannot\b.*\bsign\s*in\b/i,
            /\bunable\b.*\bsign\s*in\b/i,
            /\baccount\b.*\blocked\b/i,
            /\blocked\b.*\baccount\b/i,
            /\baccount\b.*\binaccessible\b/i,
            /\bcan't\b.*\baccess\b.*\baccount\b/i,
            /\bcannot\b.*\baccess\b.*\baccount\b/i,
            /\bunable\b.*\baccess\b.*\baccount\b/i,
            /\bcan't\b.*\baccess\b.*\bportal\b/i,
            /\bcannot\b.*\baccess\b.*\bportal\b/i,
            /\bunable\b.*\baccess\b.*\bportal\b/i,
            /\blogin\s*(?:problem|issue|trouble|error)\b/i,
            /\bsign\s*in\s*(?:problem|issue|trouble|error)\b/i,
            /\baccount\s*(?:recovery|problem|issue)\b/i,
            /\bpassword\s*(?:recovery|problem|issue)\b/i
        ];

        return resetPatterns.some(function (pattern) {
            return pattern.test(text);
        });
    }

    function showPasswordResetAction() {
        if (userMode !== "public") return;
        if (resetActionDisplayed) return;
        if (!chatMessages) return;

        resetActionDisplayed = true;

        const wrapper = document.createElement("div");
        wrapper.className = "message bot";

        const message = document.createElement("div");
        message.textContent =
            "If you are an employee who cannot access your company account, " +
            "you can submit a password-reset request for administrator review.";

        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-outline";
        button.textContent = "Request Password Reset";

        button.style.marginTop = "10px";
        button.style.width = "auto";
        button.style.minHeight = "34px";
        button.style.padding = "7px 12px";
        button.style.fontSize = "12px";

        button.addEventListener("click", function () {
            openResetDialog();
        });

        wrapper.appendChild(message);
        wrapper.appendChild(button);

        chatMessages.appendChild(wrapper);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // ==========================================
    // USER SESSION / MODE
    // ==========================================

    async function checkEmployeeSession() {
        try {
            const response = await fetch("/employee/me", {
                method: "GET",
                credentials: "same-origin"
            });

            if (!response.ok) {
                userMode = "public";
                employeeDetails = null;
                updateInterface();
                return;
            }

            const data = await response.json();

            userMode = "employee";
            employeeDetails = data.employee || data;

            updateInterface();

        } catch (error) {
            console.error("Employee session check error:", error);

            userMode = "public";
            employeeDetails = null;

            updateInterface();
        }
    }

    function updateInterface() {
        if (userMode === "employee") {
            if (loginOpen) {
                loginOpen.style.display = "none";
            }

            if (employeeLogout) {
                employeeLogout.style.display = "inline-flex";
            }

            if (chatSubtitle) {
                chatSubtitle.textContent =
                    "Employee IT helpdesk assistant";
            }

            if (chatInput) {
                chatInput.placeholder = "Describe your IT issue...";
            }

            if (humanSupportArea) {
                humanSupportArea.style.display = "none";
            }

            if (chatNote) {
                chatNote.textContent =
                    "Do not share passwords or verification codes.";
            }

            if (chatMessages && chatMessages.children.length === 1) {
                const greeting = chatMessages.querySelector(".message.bot");

                if (greeting) {
                    greeting.textContent =
                        "Hello! I'm your VIRTANSAN IT Helpdesk Assistant. " +
                        "You can ask me about company IT issues, network access, " +
                        "VPN troubleshooting, software access, and account assistance.";
                }
            }

        } else {
            if (loginOpen) {
                loginOpen.style.display = "inline-flex";
            }

            if (employeeLogout) {
                employeeLogout.style.display = "none";
            }

            if (chatSubtitle) {
                chatSubtitle.textContent =
                    "Company information assistant";
            }

            if (chatInput) {
                chatInput.placeholder = "Ask about VIRTANSAN...";
            }

            hideHumanSupportButton();

            if (chatNote) {
                chatNote.textContent =
                    "Never share passwords or verification codes.";
            }

            if (chatMessages && chatMessages.children.length === 1) {
                const greeting = chatMessages.querySelector(".message.bot");

                if (greeting) {
                    greeting.textContent =
                        "Hello! I'm VIRTANSAN AI. You can ask me about " +
                        "VIRTANSAN and its specializations in networking, " +
                        "cybersecurity, web development, and other IT fields.";
                }
            }
        }
    }

    // ==========================================
    // CHAT PANEL
    // ==========================================

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

        if (userMode === "employee") {
            checkHumanStatus();
        }
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

    // ==========================================
    // HUMAN SUPPORT - EMPLOYEES ONLY
    // ==========================================

    function wantsHumanSupport(message) {
        return /\b(human|real person|live agent|human agent|human assistant|human support|talk to someone|speak to someone|talk to a person|speak to a person|customer service|support agent|real agent|talk to human|speak to human|contact a human|request human|person to help me|speak with someone|talk with someone)\b/i.test(message);
    }

    function showHumanSupportButton() {
        if (userMode !== "employee") return;

        if (humanSupportArea) {
            humanSupportArea.style.display = "block";
        }

        if (humanSupportStatus && humanStatus === "none") {
            humanSupportStatus.textContent =
                "You can request a human support agent using the button above.";
        }
    }

    function hideHumanSupportButton() {
        if (humanSupportArea) {
            humanSupportArea.style.display = "none";
        }
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
            humanSupportButton.textContent =
                "Waiting for an administrator...";

        } else if (status === "accepted") {
            humanSupportButton.disabled = true;
            humanSupportButton.textContent =
                "Human Support Connected";

        } else {
            humanSupportButton.disabled = false;
            humanSupportButton.textContent =
                "Request Human Support";
        }

        if (chatInput) {
            chatInput.placeholder = status === "accepted"
                ? "Message your support agent..."
                : "Describe your IT issue...";
        }
    }

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
        if (userMode !== "employee") return;

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
                        "A human support agent has accepted your request. " +
                        "You can now chat with them.",
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
                        "Your request was declined. You can request human support again later.",
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
                        "The human support session has ended. You can continue " +
                        "using the AI assistant or request human support again.",
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
        if (userMode !== "employee") {
            addMessage(
                "Please log in with your employee account to request human IT support.",
                "bot"
            );
            return;
        }

        if (
            isRequestingHuman ||
            humanStatus === "pending" ||
            humanStatus === "accepted"
        ) {
            return;
        }

        isRequestingHuman = true;

        setButtonLoading(
            humanSupportButton,
            true,
            "Sending request...",
            "Request Human Support"
        );

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

            const data = await readResponse(response);

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

        return await readResponse(response);
    }

    // ==========================================
    // CHAT MESSAGE SUBMISSION
    // ==========================================

    if (chatForm && chatInput) {
        chatForm.addEventListener("submit", async function (event) {
            event.preventDefault();

            const message = chatInput.value.trim();

            if (!message || isSending) return;

            const passwordResetRequested =
                userMode === "public" && wantsPasswordReset(message);

            if (userMode === "employee" && wantsHumanSupport(message)) {
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
                if (userMode === "employee") {
                    await checkHumanStatus();

                    if (humanStatus === "pending") {
                        if (loadingMessage) {
                            loadingMessage.textContent =
                                "Your request is waiting for an administrator. " +
                                "Please wait until it has been reviewed.";
                        }

                        return;
                    }

                    if (humanStatus === "accepted") {
                        if (loadingMessage) {
                            loadingMessage.textContent =
                                "Sending your message to human support...";
                        }

                        try {
                            await sendHumanMessage(message);

                            if (loadingMessage && loadingMessage.parentNode) {
                                loadingMessage.remove();
                            }

                        } catch (error) {
                            if (loadingMessage) {
                                loadingMessage.textContent =
                                    error.message ||
                                    "Unable to send your message to human support.";

                                loadingMessage.classList.add("error");
                            }
                        }

                        return;
                    }
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

                const data = await readResponse(response);
                const reply = data.reply || "No response was returned.";

                if (loadingMessage) {
                    loadingMessage.textContent = reply;
                }

                conversationHistory.push(
                    { role: "user", content: message },
                    { role: "assistant", content: reply }
                );

                conversationHistory = conversationHistory.slice(-12);

                if (passwordResetRequested) {
                    showPasswordResetAction();
                }

            } catch (error) {
                if (loadingMessage) {
                    loadingMessage.textContent =
                        error.message ||
                        "Unable to connect to VIRTANSAN AI. Please try again.";

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

    // ==========================================
    // LOGIN DIALOG
    // ==========================================

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

    if (footerLogin) {
        footerLogin.addEventListener("click", function (event) {
            event.preventDefault();
            openLogin();
        });
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
                    "Sign in to access your company account.";

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

    // ==========================================
    // EMPLOYEE / ADMIN LOGIN SUBMISSION
    // ==========================================

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

                await readResponse(response);

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

    // ==========================================
    // PASSWORD RESET DIALOG
    // ==========================================

    function openResetDialog() {
        if (!resetBackdrop) return;

        if (resetMessage) {
            resetMessage.textContent = "";
            resetMessage.style.color = "";
        }

        if (resetForm) {
            resetForm.reset();
        }

        resetBackdrop.classList.add("open");
        resetBackdrop.setAttribute("aria-hidden", "false");
        resetBackdrop.removeAttribute("inert");

        if (resetEmail) {
            resetEmail.focus();
        }
    }

    function closeResetDialog() {
        if (!resetBackdrop) return;

        resetBackdrop.classList.remove("open");
        resetBackdrop.setAttribute("aria-hidden", "true");
        resetBackdrop.setAttribute("inert", "");

        if (resetForm) {
            resetForm.reset();
        }

        if (resetMessage) {
            resetMessage.textContent = "";
            resetMessage.style.color = "";
        }
    }

    if (loginPasswordReset) {
        loginPasswordReset.addEventListener("click", function () {
            closeLogin();
            openResetDialog();
        });
    }

    if (resetClose) {
        resetClose.addEventListener("click", closeResetDialog);
    }

    if (resetBackdrop) {
        resetBackdrop.addEventListener("click", function (event) {
            if (event.target === resetBackdrop) {
                closeResetDialog();
            }
        });
    }

    // ==========================================
    // PASSWORD RESET REQUEST SUBMISSION
    // ==========================================

    if (resetForm) {
        resetForm.addEventListener("submit", async function (event) {
            event.preventDefault();

            if (isSubmittingReset) return;

            const email = resetEmail.value.trim();
            const description = resetDescriptionInput.value.trim();
            const confirmed = resetConfirmation.checked;

            if (!email || !description) {
                resetMessage.textContent =
                    "Please complete all required fields.";
                resetMessage.style.color = "";
                return;
            }

            if (!confirmed) {
                resetMessage.textContent =
                    "Please confirm that you want to submit this request.";
                resetMessage.style.color = "";
                return;
            }

            isSubmittingReset = true;

            resetMessage.textContent = "Submitting your request...";
            resetMessage.style.color = "";

            setButtonLoading(
                resetSubmit,
                true,
                "Submitting...",
                "Submit Request"
            );

            try {
                const response = await fetch("/public/password-reset", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    credentials: "same-origin",
                    body: JSON.stringify({
                        email: email,
                        description: description,
                        request_id: createRequestId(),
                        confirmed: true
                    })
                });

                const data = await readResponse(response);

                // Show success only after the backend confirms submission.
                resetMessage.textContent =
                    data.message ||
                    "Your password-reset request has been submitted successfully. " +
                    "Please wait for administrator review.";

                resetMessage.style.color = "green";

                resetForm.reset();

                addMessage(
                    data.status === "already_submitted"
                        ? "This password-reset request has already been submitted."
                        : "Your password-reset request has been submitted for administrator review. Please check your phone or personal email for the temporary password within 1 or 2 hours.",
                    "bot"
                );

            } catch (error) {
                // Display the actual backend error.
                // For example: account does not exist or account is inactive.
                resetMessage.textContent =
                    error.message ||
                    "Unable to submit your request. Please try again.";

                resetMessage.style.color = "red";

                console.error("Password reset request error:", error);

            } finally {
                isSubmittingReset = false;

                setButtonLoading(
                    resetSubmit,
                    false,
                    "Submitting...",
                    "Submit Request"
                );
            }
        });
    }

    // ==========================================
    // EMPLOYEE LOGOUT
    // ==========================================

    if (employeeLogout) {
        employeeLogout.addEventListener("click", async function () {
            employeeLogout.disabled = true;

            try {
                const response = await fetch("/employee/logout", {
                    method: "POST",
                    credentials: "same-origin"
                });

                await readResponse(response);

                window.location.href = "/";

            } catch (error) {
                console.error("Employee logout error:", error);

                alert(
                    error.message ||
                    "Unable to log out. Please try again."
                );

                employeeLogout.disabled = false;
            }
        });
    }

    // ==========================================
    // ADMIN LOGOUT COMPATIBILITY
    // ==========================================

    const adminLogoutButton = document.getElementById("logoutButton");

    if (adminLogoutButton) {
        adminLogoutButton.addEventListener("click", async function () {
            adminLogoutButton.disabled = true;

            try {
                const response = await fetch("/admin-logout", {
                    method: "POST",
                    credentials: "same-origin"
                });

                await readResponse(response);

                window.location.href = "/";

            } catch (error) {
                console.error("Admin logout error:", error);

                alert("Unable to log out. Please try again.");

                adminLogoutButton.disabled = false;
            }
        });
    }

    // ==========================================
    // KEYBOARD CONTROLS
    // ==========================================

    document.addEventListener("keydown", function (event) {
        if (event.key !== "Escape") return;

        if (resetBackdrop && resetBackdrop.classList.contains("open")) {
            closeResetDialog();

        } else if (loginBackdrop && loginBackdrop.classList.contains("open")) {
            closeLogin();

        } else if (chatPanel && chatPanel.classList.contains("open")) {
            closeChat();
        }
    });

    // ==========================================
    // INITIALIZE APPLICATION
    // ==========================================

    if (year) {
        year.textContent = new Date().getFullYear();
    }

    hideHumanSupportButton();

    checkEmployeeSession();

    setInterval(function () {
        if (userMode === "employee") {
            checkHumanStatus();
        }
    }, 4000);
});
