import os
import hmac
import json
import threading
from datetime import datetime, timezone
from typing import Literal

import chromadb
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware


app = FastAPI(title="VIRTANSAN AI")


# =========================
# TICKET STORAGE
# =========================

TICKETS_FILE = os.path.join(os.path.dirname(__file__), "tickets.json")
ticket_lock = threading.Lock()


class TicketCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=5, max_length=3000)
    email: str = Field(default="", max_length=254)
    category: Literal["IT Support", "Password Reset"] = "IT Support"


class TicketUpdate(BaseModel):
    status: Literal[
        "Pending Review",
        "Pending Approval",
        "Accepted",
        "Approved",
        "In Progress",
        "Fixed",
        "Cannot Fix",
        "Denied"
    ]
    admin_note: str = Field(default="", max_length=2000)


def read_tickets():
    if not os.path.exists(TICKETS_FILE):
        return []

    with open(TICKETS_FILE, "r", encoding="utf-8") as file:
        tickets = json.load(file)

    if not isinstance(tickets, list):
        raise ValueError("tickets.json must contain a JSON list.")

    return tickets


def write_tickets(tickets):
    temporary_file = TICKETS_FILE + ".tmp"

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(tickets, file, indent=2, ensure_ascii=False)

    os.replace(temporary_file, TICKETS_FILE)


def require_admin(request: Request):
    if not request.session.get("is_admin"):
        raise HTTPException(
            status_code=401,
            detail="Admin login required."
        )


# =========================
# ADMIN AUTHENTICATION
# =========================

ADMIN_EMAIL = "admin@work.com"
ADMIN_PASSWORD = "admin123"

SESSION_SECRET = os.getenv(
    "SESSION_SECRET",
    "dev-only-change-this-session-secret"
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="virtansan_session",
    same_site="lax",
    https_only=False
)

class AdminLogin(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=200)

@app.post("/admin-login")
def admin_login(credentials: AdminLogin, request: Request):
    email_matches = hmac.compare_digest(
        credentials.email.strip().lower(),
        ADMIN_EMAIL.lower()
    )

    password_matches = hmac.compare_digest(
        credentials.password,
        ADMIN_PASSWORD
    )

    if not email_matches or not password_matches:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    request.session.clear()
    request.session["is_admin"] = True

    return {"message": "Login successful"}


@app.post("/admin-logout")
def admin_logout(request: Request):
    request.session.clear()
    return {"message": "Logged out successfully"}


@app.get("/admin.html")
def admin_dashboard(request: Request):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/", status_code=303)

    return FileResponse("admin.html")


# =========================
# TICKET API
# =========================

@app.post("/tickets")
def create_ticket(ticket: TicketCreate):
    email = ticket.email.strip()
    title_input = ticket.title.strip()
    description = ticket.description.strip()

    if len(title_input) < 3:
        raise HTTPException(
            status_code=422,
            detail="The ticket title must contain at least 3 characters."
        )

    if len(description) < 5:
        raise HTTPException(
            status_code=422,
            detail="Please provide a more detailed description."
        )

    if ticket.category == "Password Reset" and not email:
        raise HTTPException(
            status_code=400,
            detail="A work email is required for password-reset requests."
        )

    if ticket.category == "Password Reset":
        title = f"{email} - Password Reset"
        status = "Pending Approval"
    else:
        title = title_input
        status = "Pending Review"

    with ticket_lock:
        try:
            tickets = read_tickets()
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(
                status_code=500,
                detail="Ticket storage is invalid. Please check tickets.json."
            )
        except OSError:
            raise HTTPException(
                status_code=500,
                detail="Ticket storage could not be read."
            )

        existing_numbers = []

        for item in tickets:
            ticket_id = item.get("id", "")

            if (
                isinstance(ticket_id, str)
                and ticket_id.startswith("TKT-")
                and ticket_id[4:].isdigit()
            ):
                existing_numbers.append(int(ticket_id[4:]))

        next_number = max(existing_numbers, default=0) + 1
        new_ticket_id = f"TKT-{next_number:04d}"
        now = datetime.now(timezone.utc).isoformat()

        new_ticket = {
            "id": new_ticket_id,
            "title": title,
            "description": description,
            "email": email,
            "category": ticket.category,
            "status": status,
            "admin_note": "",
            "created_at": now,
            "updated_at": now
        }

        tickets.append(new_ticket)

        try:
            write_tickets(tickets)
        except OSError:
            raise HTTPException(
                status_code=500,
                detail="The ticket could not be saved."
            )

    return {
        "message": "Ticket created successfully.",
        "ticket": new_ticket
    }


@app.get("/admin/tickets")
def list_tickets(request: Request):
    require_admin(request)

    with ticket_lock:
        try:
            tickets = read_tickets()
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(
                status_code=500,
                detail="Ticket storage is invalid. Please check tickets.json."
            )
        except OSError:
            raise HTTPException(
                status_code=500,
                detail="Ticket storage could not be read."
            )

    return {"tickets": tickets}


@app.patch("/admin/tickets/{ticket_id}")
def update_ticket(
    ticket_id: str,
    update: TicketUpdate,
    request: Request
):
    require_admin(request)

    with ticket_lock:
        try:
            tickets = read_tickets()
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(
                status_code=500,
                detail="Ticket storage is invalid. Please check tickets.json."
            )
        except OSError:
            raise HTTPException(
                status_code=500,
                detail="Ticket storage could not be read."
            )

        for ticket in tickets:
            if ticket.get("id") == ticket_id:
                ticket["status"] = update.status
                ticket["admin_note"] = update.admin_note.strip()
                ticket["updated_at"] = datetime.now(
                    timezone.utc
                ).isoformat()

                try:
                    write_tickets(tickets)
                except OSError:
                    raise HTTPException(
                        status_code=500,
                        detail="The ticket update could not be saved."
                    )

                return {
                    "message": "Ticket updated successfully.",
                    "ticket": ticket
                }

    raise HTTPException(
        status_code=404,
        detail="Ticket not found."
    )


# =========================
# CHROMADB
# =========================

client = chromadb.PersistentClient(path="./chroma_data")
collection = client.get_or_create_collection(name="it_knowledge")


# =========================
# OLLAMA SETTINGS
# =========================

OLLAMA_URL = "http://localhost:11434/api/chat"
EMBEDDING_URL = "http://localhost:11434/api/embeddings"
CHAT_MODEL = "qwen2.5:7b"
EMBEDDING_MODEL = "nomic-embed-text"


OFF_TOPIC_REPLY = (
    "I'm here to help with company-related IT questions. 😊\n\n"
    "I can assist with company accounts, work devices, "
    "software access, networking, and VPN troubleshooting.\n\n"
    "Is there a company IT issue I can help you with?"
)

PERSONAL_SCOPE_REPLY = (
    "I'm sorry you're experiencing that issue. 😊\n\n"
    "VIRTANSAN AI only supports company-related IT issues, "
    "so I can't troubleshoot personal accounts, games, "
    "or devices.\n\n"
    "I can help with company accounts, work devices, "
    "software access, networking, and VPN issues."
)


# =========================
# REQUEST MODELS
# =========================

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list)





# =========================
# FRONTEND
# =========================

@app.get("/")
def home():
    return FileResponse("frontend/index.html")


# =========================
# HEALTH CHECK
# =========================

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "knowledge_base": collection.name,
        "documents_indexed": collection.count()
    }


# =========================
# EMBEDDINGS
# =========================

def create_embedding(text):
    response = requests.post(
        EMBEDDING_URL,
        json={
            "model": EMBEDDING_MODEL,
            "prompt": text
        },
        timeout=120
    )

    response.raise_for_status()

    return response.json()["embedding"]


# =========================
# INTENT CLASSIFICATION
# =========================

def classify_intent(message, history):
    recent_conversation = "\n".join(
        f"{item.role}: {item.content}"
        for item in history[-8:]
    )

    prompt = f"""
You are an intent classifier for an enterprise IT helpdesk.

Classify the latest message into exactly one category.

IT_RELATED: The user is asking about a technical problem or
IT support issue.

SMALL_TALK: A greeting, thanks, goodbye, or simple social comment
that is not part of an ongoing support issue.

NO_PROBLEM: The user clearly says they have no issue or no longer
need help. Do not use this category for "no" answering a question.

UNCLEAR: The user has not explained what they need and context
does not clarify their meaning.

OFF_TOPIC: A request unrelated to IT, such as recipes, entertainment,
or travel planning.

Use conversation history to understand short replies.

A greeting combined with an IT problem is IT_RELATED.
A personal technical problem may be IT_RELATED here, but its company
scope must be checked separately.
Return only one category name.

Recent conversation:
{recent_conversation}

Latest user message:
{message}
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": CHAT_MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {"temperature": 0}
        },
        timeout=120
    )

    response.raise_for_status()

    result = response.json()["message"]["content"].strip().upper()

    allowed_categories = {
        "IT_RELATED",
        "SMALL_TALK",
        "NO_PROBLEM",
        "UNCLEAR",
        "OFF_TOPIC"
    }

    if result in allowed_categories:
        return result

    return "UNCLEAR"


# =========================
# COMPANY SCOPE CLASSIFICATION
# =========================

def classify_scope(message, history):
    recent_conversation = "\n".join(
        f"{item.role}: {item.content}"
        for item in history[-8:]
    )

    prompt = f"""
You classify requests for an enterprise IT helpdesk.

Return exactly one category:

COMPANY: The issue clearly concerns an organization's account,
work device, company application, company network, work VPN,
or another company IT service.

PERSONAL: The issue clearly concerns a personal account, personal
device, gaming account, entertainment service, or other personal
technology unrelated to company operations.

UNCLEAR: It is not clear whether the issue concerns company IT
or personal technology.

Rules:
- Only company-related IT issues may be troubleshot.
- Technical or cybersecurity-related does not automatically mean COMPANY.
- Personal Steam, Epic Games, Roblox, social media, and personal email
  accounts are PERSONAL unless the user clearly establishes that the
  issue concerns an organization-owned account or company operations.
- A hacked personal account is PERSONAL.
- Do not assume "my account" means a company account.
- A company-related issue mentioned earlier does not make a new,
  clearly personal issue a company issue.
- Use conversation history only when it genuinely clarifies the scope.
- If the user says "my company account", "work laptop", "company VPN",
  or clearly identifies a company service, classify it as COMPANY.
- If the message is ambiguous, return UNCLEAR.
- Do not provide troubleshooting instructions. Only classify the scope.

Recent conversation:
{recent_conversation}

Latest user message:
{message}

Return only COMPANY, PERSONAL, or UNCLEAR.
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": CHAT_MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {"temperature": 0}
        },
        timeout=120
    )

    response.raise_for_status()

    result = response.json()["message"]["content"].strip().upper()

    if result in {"COMPANY", "PERSONAL", "UNCLEAR"}:
        return result

    return "UNCLEAR"


# =========================
# PASSWORD SUPPORT
# =========================

def is_password_related(text):
    text = text.lower()

    terms = [
        "password",
        "forgot my pass",
        "forgotten my pass",
        "can't remember my pass",
        "cannot remember my pass",
        "work account",
        "reset my pass",
        "reset pass"
    ]

    return any(term in text for term in terms)


def get_password_reply(message, history):
    normalized = message.lower().strip().rstrip("!.,?")

    previous_assistant = ""

    for item in reversed(history):
        if item.role == "assistant":
            previous_assistant = item.content.lower()
            break

    affirmative = {
        "yes", "yes please", "yes, please", "sure",
        "okay", "ok", "yep", "yeah", "please do",
        "that would help"
    }

    negative = {
        "no", "no thanks", "not now", "no thank you"
    }

    if normalized in negative:
        return (
            "That's okay. 😊 You can use your organization's "
            "official password-reset option whenever you're ready. "
            "If you can't access it, contact your IT support team."
        )

    if normalized in affirmative:
        if (
            "would you like" in previous_assistant
            or "like me to walk you through" in previous_assistant
            or "if you'd like" in previous_assistant
            or "would you like me to" in previous_assistant
        ):
            return (
                "Sure! 😊 Here's how to reset your work password:\n\n"
                "1. Open your organization's usual work sign-in page.\n"
                "2. Select **Forgot password?** or the equivalent option.\n"
                "3. Follow the verification steps shown by your organization.\n"
                "4. Create a new password and try signing in again.\n\n"
                "If you don't see a reset option, or your account is "
                "locked, contact your IT support team. I don't know "
                "your organization's exact reset link, so I won't guess. "
                "Never share your password or verification codes here."
            )

        if (
            "which sign-in system" in previous_assistant
            or "which application" in previous_assistant
        ):
            return (
                "I can help with that. 😊 Which sign-in system do you "
                "use for work—for example, Microsoft 365, Google "
                "Workspace, or another company system?"
            )

    if normalized in {
        "what", "what?", "huh",
        "i don't understand", "i dont understand"
    }:
        return (
            "Sorry for the confusion. 😊 Since you forgot your work "
            "password, we'll use your organization's official reset "
            "process. I can guide you through the general steps, but "
            "your IT team may be needed if your company manages resets."
        )

    if "work account" in normalized or "my work account" in normalized:
        return (
            "Got it—it's your work account. 😊 Would you like me to "
            "walk you through the general password-reset steps?"
        )

    if (
        "forgot my password" in normalized
        or "forgot password" in normalized
        or "forgotten password" in normalized
        or "can't remember my password" in normalized
        or "cannot remember my password" in normalized
        or "reset my password" in normalized
        or "reset password" in normalized
    ):
        return (
            "No worries! 😊 Is this your work account, or are you "
            "trying to sign in to a specific application? Please "
            "don't share your password or verification codes here."
        )

    return None


# =========================
# AI CHATBOT
# =========================

@app.post("/chat")
def chat(request: ChatRequest):
    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Please enter a message."
        )

    history = request.history[-12:]

    if (
        history
        and history[-1].role == "user"
        and history[-1].content.strip() == message
    ):
        history = history[:-1]

    normalized = message.lower().strip().rstrip("!.,?")

    greetings = {
        "hi", "hello", "hey", "hiya", "howdy",
        "good morning", "good afternoon", "good evening"
    }

    help_messages = {
        "help", "what can you do", "what can you help me with",
        "what can you help me do", "what do you do",
        "how do i use you", "how can you help me"
    }

    if not history and normalized in greetings:
        return {
            "reply": (
                "Hey there! 😊 Welcome to VIRTANSAN AI.\n\n"
                "I'm your friendly company IT assistant. Tell me "
                "what's happening with a company IT service, and "
                "I'll help you work through it."
            ),
            "source": "Introduction Guide"
        }

    if not history and normalized in help_messages:
        return {
            "reply": (
                "Of course! 😊 I can help with company account issues, "
                "work devices, software access, networking, VPN "
                "connections, and other company IT problems."
            ),
            "source": "Introduction Guide"
        }

    try:
        intent = classify_intent(message, history)

        if intent == "OFF_TOPIC":
            return {
                "reply": OFF_TOPIC_REPLY,
                "source": "Scope Guard"
            }

        if intent == "NO_PROBLEM":
            return {
                "reply": "I'm here whenever you need company IT assistance.",
                "source": "Conversation Guide"
            }

        if intent == "SMALL_TALK":
            return {
                "reply": (
                    "I'm here whenever you need "
                    "help with a company IT issue."
                ),
                "source": "Conversation Guide"
            }

        if intent == "UNCLEAR":
            return {
                "reply": (
                    "Could you tell me a little more about what you need "
                    "help with? 😊"
                ),
                "source": "Conversation Guide"
            }

        scope = classify_scope(message, history)

        if scope == "PERSONAL":
            return {
                "reply": PERSONAL_SCOPE_REPLY,
                "source": "Company Scope Guard"
            }

        if scope == "UNCLEAR":
            return {
                "reply": (
                    "I can help with company-related IT issues. 😊 "
                    "Is this problem related to a company account, "
                    "work device, application, or network service?"
                ),
                "source": "Company Scope Guard"
            }

    except requests.RequestException:
        raise HTTPException(
            status_code=502,
            detail=(
                "I couldn't connect to the local AI service. "
                "Please check that Ollama is running and try again."
            )
        )

    password_context = any(
        item.role == "user" and is_password_related(item.content)
        for item in history
    )

    if password_context or is_password_related(message):
        password_reply = get_password_reply(message, history)

        if password_reply:
            return {
                "reply": password_reply,
                "source": "Password Support Guide"
            }

    try:
        embedding = create_embedding(message)

        results = collection.query(
            query_embeddings=[embedding],
            n_results=1
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        if documents and documents[0]:
            knowledge = documents[0]
            source = (
                metadatas[0].get("source", "Unknown")
                if metadatas and metadatas[0]
                else "Unknown"
            )
        else:
            knowledge = ""
            source = "No relevant source found"

        if not knowledge:
            return {
                "reply": (
                    "I couldn't find enough information in my knowledge "
                    "base to answer confidently. Could you explain the "
                    "company IT issue in a little more detail? Your IT "
                    "support team may need to help with company-specific "
                    "settings."
                ),
                "source": source
            }

        system_prompt = f"""
You are VIRTANSAN AI, a friendly enterprise IT helpdesk assistant.

SCOPE RESTRICTION:
You ONLY support company-related IT issues.
Never troubleshoot personal accounts, personal gaming services,
personal devices, or technology unrelated to company operations.
A technical or cybersecurity-related topic is not automatically
a company IT issue.
Do not provide troubleshooting instructions for personal issues.
If the request is outside company IT scope, politely decline and
redirect the user to company-related IT support.

RESPONSE RULES:
- Use the conversation to understand follow-up messages.
- Do not restart the conversation or repeat questions already answered.
- Use the knowledge-base reference when relevant.
- Do not copy the entire knowledge-base document.
- Give concise, simple, relevant answers.
- Do not invent company policies, links, server addresses, or procedures.
- Never ask for passwords or verification codes.
- If information is missing, ask one clear follow-up question.
- If the knowledge base does not support an answer, say so.
- Never claim a ticket was created or an action completed unless confirmed.

Knowledge-base reference:
{knowledge}
"""

        ollama_messages = [
            {"role": "system", "content": system_prompt}
        ]

        for item in history[-8:]:
            ollama_messages.append({
                "role": item.role,
                "content": item.content
            })

        ollama_messages.append({
            "role": "user",
            "content": message
        })

        response = requests.post(
            OLLAMA_URL,
            json={
                "model": CHAT_MODEL,
                "messages": ollama_messages,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 250
                }
            },
            timeout=120
        )

        response.raise_for_status()

        result = response.json()

        return {
            "reply": result["message"]["content"].strip(),
            "source": source
        }

    except requests.RequestException:
        raise HTTPException(
            status_code=502,
            detail=(
                "I couldn't connect to the local AI service. "
                "Please check that Ollama is running and try again."
            )
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail=(
                "Something went wrong while preparing my response. "
                "Please try again."
            )
        )


# =========================
# STATIC FRONTEND FILES
# =========================

app.mount(
    "/static",
    StaticFiles(directory="frontend"),
    name="static"
)