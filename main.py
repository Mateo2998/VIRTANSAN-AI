import os
import re
import hmac
import json
import hashlib
import secrets
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


# ==========================================
# APPLICATION SETTINGS
# ==========================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
TICKETS_FILE = os.path.join(BASE_DIR, "tickets.json")
HUMAN_REQUESTS_FILE = os.path.join(BASE_DIR, "human_requests.json")
EMPLOYEES_FILE = os.path.join(BASE_DIR, "employees.json")
CHROMA_DIR = os.path.join(BASE_DIR, "chroma_data")

app = FastAPI(title="VIRTANSAN AI")

ticket_lock = threading.Lock()
human_lock = threading.Lock()
employee_lock = threading.Lock()


# ==========================================
# ADMIN AUTHENTICATION
# ==========================================

ADMIN_EMAIL = "admin@work.com"
ADMIN_PASSWORD = "admin123"

SESSION_SECRET = os.getenv(
    "SESSION_SECRET",
    "dev-only-change-this-session-secret",
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="virtansan_session",
    same_site="lax",
    https_only=False,
)


class AdminLogin(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=200)


def require_admin(request: Request):
    if not request.session.get("is_admin"):
        raise HTTPException(
            status_code=401,
            detail="Admin login required.",
        )


@app.post("/admin-login")
def admin_login(credentials: AdminLogin, request: Request):
    email_matches = hmac.compare_digest(
        credentials.email.strip().lower(),
        ADMIN_EMAIL.lower(),
    )

    password_matches = hmac.compare_digest(
        credentials.password,
        ADMIN_PASSWORD,
    )

    if not email_matches or not password_matches:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
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

    admin_file = os.path.join(BASE_DIR, "admin.html")

    if not os.path.exists(admin_file):
        raise HTTPException(
            status_code=404,
            detail="Admin page was not found.",
        )

    return FileResponse(admin_file)


# ==========================================
# TICKET MODELS
# ==========================================

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
        "Denied",
    ]
    admin_note: str = Field(default="", max_length=2000)


# ==========================================
# TICKET STORAGE
# ==========================================

def read_tickets():
    if not os.path.exists(TICKETS_FILE):
        return []

    with open(TICKETS_FILE, "r", encoding="utf-8") as file:
        tickets = json.load(file)

    if not isinstance(tickets, list):
        raise ValueError("Ticket storage must contain a JSON list.")

    return tickets


def write_tickets(tickets):
    temporary_file = TICKETS_FILE + ".tmp"

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(tickets, file, indent=2, ensure_ascii=False)

    os.replace(temporary_file, TICKETS_FILE)


# ==========================================
# EMPLOYEE ACCOUNT STORAGE
# ==========================================

def read_employees():
    if not os.path.exists(EMPLOYEES_FILE):
        return []

    with open(EMPLOYEES_FILE, "r", encoding="utf-8") as file:
        employees = json.load(file)

    if not isinstance(employees, list):
        raise ValueError(
            "Employee storage must contain a JSON list."
        )

    return employees


def write_employees(employees):
    temporary_file = EMPLOYEES_FILE + ".tmp"

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(
            employees,
            file,
            indent=2,
            ensure_ascii=False,
        )

    os.replace(temporary_file, EMPLOYEES_FILE)


# ==========================================
# EMPLOYEE PASSWORD HASHING
# ==========================================

def hash_employee_password(password):
    salt = secrets.token_hex(16)
    iterations = 600000

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()

    return f"pbkdf2_sha256${iterations}${salt}${password_hash}"


def verify_employee_password(password, stored_hash):
    try:
        algorithm, iterations, salt, expected_hash = (
            stored_hash.split("$")
        )

        if algorithm != "pbkdf2_sha256":
            return False

        iterations = int(iterations)

        if iterations < 1 or iterations > 2000000:
            return False

        actual_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        ).hex()

        return hmac.compare_digest(
            actual_hash,
            expected_hash,
        )

    except (ValueError, TypeError, AttributeError):
        return False


def get_logged_in_employee(request: Request):
    employee_id = request.session.get("employee_id")

    if not employee_id:
        return None

    with employee_lock:
        try:
            employees = read_employees()
        except (json.JSONDecodeError, ValueError, OSError):
            return None

    for employee in employees:
        if not isinstance(employee, dict):
            continue

        if (
            employee.get("id") == employee_id
            and employee.get("role", "employee") == "employee"
        ):
            return employee

    return None


def require_employee(request: Request):
    employee = get_logged_in_employee(request)

    if not employee:
        raise HTTPException(
            status_code=401,
            detail="Employee login required.",
        )

    return employee


# ==========================================
# CREATE AND LIST EMPLOYEE ACCOUNTS
# ==========================================

class EmployeeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=200)

class EmployeeEmailUpdate(BaseModel):
    email: str = Field(min_length=3, max_length=254)

class AdminEmployeePasswordUpdate(BaseModel):
    password: str = Field(min_length=8, max_length=200)


def public_employee_details(employee):
    return {
        "id": employee.get("id", ""),
        "name": employee.get("name", ""),
        "email": employee.get("email", ""),
        "role": employee.get("role", "employee"),
        "created_at": employee.get("created_at", ""),
    }


@app.post("/admin/employees", status_code=201)
def create_employee(
    payload: EmployeeCreate,
    request: Request,
):
    require_admin(request)

    name = payload.name.strip()
    email = payload.email.strip().lower()
    password = payload.password

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Employee name is required.",
        )

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(
            status_code=400,
            detail="Please enter a valid email address.",
        )

    if len(password) < 8:
        raise HTTPException(
            status_code=400,
            detail="The password must contain at least 8 characters.",
        )

    with employee_lock:
        try:
            employees = read_employees()
        except (json.JSONDecodeError, ValueError, OSError):
            raise HTTPException(
                status_code=500,
                detail="Employee account storage could not be read.",
            )

        for employee in employees:
            if not isinstance(employee, dict):
                continue

            existing_email = employee.get("email", "")

            if (
                isinstance(existing_email, str)
                and existing_email.strip().lower() == email
            ):
                raise HTTPException(
                    status_code=409,
                    detail="An employee with this email already exists.",
                )

        new_employee = {
            "id": secrets.token_hex(16),
            "name": name,
            "email": email,
            "role": "employee",
            "password_hash": hash_employee_password(password),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        employees.append(new_employee)

        try:
            write_employees(employees)
        except OSError:
            raise HTTPException(
                status_code=500,
                detail="The employee account could not be saved.",
            )

    return {
        "message": "Employee account created successfully.",
        "employee": public_employee_details(new_employee),
    }


@app.get("/admin/employees")
def list_employees(request: Request):
    require_admin(request)

    with employee_lock:
        try:
            employees = read_employees()
        except (json.JSONDecodeError, ValueError, OSError):
            raise HTTPException(
                status_code=500,
                detail="Employee account storage could not be read.",
            )

    return {
        "employees": [
            public_employee_details(employee)
            for employee in employees
            if isinstance(employee, dict)
        ]
    }


# ==========================================
# UPDATE EMPLOYEE EMAIL
# ==========================================

@app.patch("/admin/employees/{employee_id}/email")
def update_employee_email(
    employee_id: str,
    payload: EmployeeEmailUpdate,
    request: Request,
):
    require_admin(request)

    new_email = payload.email.strip().lower()

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", new_email):
        raise HTTPException(
            status_code=422,
            detail="Please enter a valid email address.",
        )

    with employee_lock:
        try:
            employees = read_employees()
        except (json.JSONDecodeError, ValueError, OSError):
            raise HTTPException(
                status_code=500,
                detail="Employee account storage could not be read.",
            )

        target = next(
            (
                employee
                for employee in employees
                if isinstance(employee, dict)
                and employee.get("id") == employee_id
            ),
            None,
        )

        if target is None:
            raise HTTPException(
                status_code=404,
                detail="Employee account not found.",
            )

        for employee in employees:
            if not isinstance(employee, dict):
                continue

            if employee.get("id") == employee_id:
                continue

            existing_email = employee.get("email", "")

            if (
                isinstance(existing_email, str)
                and existing_email.strip().lower() == new_email
            ):
                raise HTTPException(
                    status_code=409,
                    detail="That email address is already in use.",
                )

        target["email"] = new_email

        try:
            write_employees(employees)
        except OSError:
            raise HTTPException(
                status_code=500,
                detail="The employee email could not be saved.",
            )

    return {
        "message": "Employee email updated successfully.",
        "employee": public_employee_details(target),
    }


# ==========================================
# ADMIN CHANGE EMPLOYEE PASSWORD
# ==========================================

@app.patch("/admin/employees/{employee_id}/password")
def admin_change_employee_password(
    employee_id: str,
    payload: AdminEmployeePasswordUpdate,
    request: Request,
):
    require_admin(request)

    new_password = payload.password

    if len(new_password) < 8:
        raise HTTPException(
            status_code=400,
            detail="The password must contain at least 8 characters.",
        )

    with employee_lock:
        try:
            employees = read_employees()
        except (json.JSONDecodeError, ValueError, OSError):
            raise HTTPException(
                status_code=500,
                detail="Employee account storage could not be read.",
            )

        target = next(
            (
                employee
                for employee in employees
                if isinstance(employee, dict)
                and employee.get("id") == employee_id
            ),
            None,
        )

        if target is None:
            raise HTTPException(
                status_code=404,
                detail="Employee account not found.",
            )

        target["password_hash"] = hash_employee_password(new_password)

        try:
            write_employees(employees)
        except OSError:
            raise HTTPException(
                status_code=500,
                detail="The employee password could not be saved.",
            )

    return {
        "message": "Employee password changed successfully."
    }

# ==========================================
# DELETE EMPLOYEE ACCOUNT
# ==========================================

@app.delete("/admin/employees/{employee_id}")
def delete_employee(
    employee_id: str,
    request: Request,
):
    require_admin(request)

    with employee_lock:
        try:
            employees = read_employees()
        except (json.JSONDecodeError, ValueError, OSError):
            raise HTTPException(
                status_code=500,
                detail="Employee account storage could not be read.",
            )

        target = next(
            (
                employee
                for employee in employees
                if isinstance(employee, dict)
                and employee.get("id") == employee_id
            ),
            None,
        )

        if target is None:
            raise HTTPException(
                status_code=404,
                detail="Employee account not found.",
            )

        remaining_employees = [
            employee
            for employee in employees
            if not (
                isinstance(employee, dict)
                and employee.get("id") == employee_id
            )
        ]

        try:
            write_employees(remaining_employees)
        except OSError:
            raise HTTPException(
                status_code=500,
                detail="The employee account could not be deleted.",
            )

    return {
        "message": "Employee account deleted successfully.",
    }


# ==========================================
# EMPLOYEE LOGIN
# ==========================================

class EmployeeLogin(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class EmployeePasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


@app.post("/employee-login")
def employee_login(
    credentials: EmployeeLogin,
    request: Request,
):
    email = credentials.email.strip().lower()

    with employee_lock:
        try:
            employees = read_employees()
        except (json.JSONDecodeError, ValueError, OSError):
            raise HTTPException(
                status_code=500,
                detail="Employee account storage could not be read.",
            )

        employee_found = None

        for employee in employees:
            if not isinstance(employee, dict):
                continue

            employee_email = employee.get("email", "")

            if (
                isinstance(employee_email, str)
                and employee_email.strip().lower() == email
            ):
                employee_found = employee
                break

        if not employee_found:
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password.",
            )

        stored_hash = employee_found.get("password_hash", "")

        if not verify_employee_password(
            credentials.password,
            stored_hash,
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password.",
            )

        if employee_found.get("role", "employee") != "employee":
            raise HTTPException(
                status_code=403,
                detail="This account is not an employee account.",
            )

        employee_id = employee_found.get("id")

        if not isinstance(employee_id, str) or not employee_id:
            raise HTTPException(
                status_code=500,
                detail="The employee account is missing its ID.",
            )

        request.session.clear()
        request.session["employee_id"] = employee_id

    return {
        "message": "Employee login successful.",
        "redirect": "/employee.html",
    }


# ==========================================
# EMPLOYEE PROFILE
# ==========================================

@app.get("/employee/me")
def employee_profile(request: Request):
    employee = require_employee(request)

    return {
        "id": employee.get("id", ""),
        "name": employee.get("name", ""),
        "email": employee.get("email", ""),
        "role": employee.get("role", "employee"),
    }


@app.post("/employee/logout")
def employee_logout(request: Request):
    request.session.pop("employee_id", None)
    request.session.pop("is_admin", None)

    return {"message": "Logged out successfully."}



# ==========================================
# EMPLOYEE PASSWORD CHANGE
# ==========================================

@app.post("/employee/change-password")
def employee_change_password(
    payload: EmployeePasswordChange,
    request: Request,
):
    employee = require_employee(request)

    current_password = payload.current_password
    new_password = payload.new_password

    if len(new_password) < 8:
        raise HTTPException(
            status_code=400,
            detail="The new password must contain at least 8 characters.",
        )

    if hmac.compare_digest(current_password, new_password):
        raise HTTPException(
            status_code=400,
            detail=(
                "Your new password must be different "
                "from your current password."
            ),
        )

    with employee_lock:
        try:
            employees = read_employees()
        except (json.JSONDecodeError, ValueError, OSError):
            raise HTTPException(
                status_code=500,
                detail="Employee account storage could not be read.",
            )

        for stored_employee in employees:
            if not isinstance(stored_employee, dict):
                continue

            if stored_employee.get("id") != employee.get("id"):
                continue

            stored_hash = stored_employee.get("password_hash", "")

            if not verify_employee_password(
                current_password,
                stored_hash,
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Your current password is incorrect.",
                )

            stored_employee["password_hash"] = (
                hash_employee_password(new_password)
            )

            try:
                write_employees(employees)
            except OSError:
                raise HTTPException(
                    status_code=500,
                    detail="The new password could not be saved.",
                )

            return {
                "message": (
                    "Your password has been changed successfully."
                )
            }

    request.session.clear()

    raise HTTPException(
        status_code=401,
        detail="Employee account not found. Please log in again.",
    )


# ==========================================
# EMPLOYEE LOGOUT
# ==========================================

@app.post("/employee-logout")
def employee_logout(request: Request):
    request.session.clear()

    return {
        "message": "Logged out successfully.",
        "redirect": "/",
    }


# ==========================================
# EMPLOYEE DASHBOARD
# ==========================================

@app.get("/employee.html")
def employee_dashboard(request: Request):
    employee = get_logged_in_employee(request)

    if not employee:
        return RedirectResponse(
            url="/",
            status_code=303,
        )

    employee_file = os.path.join(
        FRONTEND_DIR,
        "employee.html",
    )

    if not os.path.exists(employee_file):
        raise HTTPException(
            status_code=404,
            detail="Employee dashboard was not found.",
        )

    return FileResponse(employee_file)


# ==========================================
# TICKET API
# ==========================================

@app.post("/tickets")
def create_ticket(ticket: TicketCreate):
    title_input = ticket.title.strip()
    description = ticket.description.strip()
    email = ticket.email.strip()

    if len(title_input) < 3:
        raise HTTPException(
            status_code=422,
            detail="The ticket title must contain at least 3 characters.",
        )

    if len(description) < 5:
        raise HTTPException(
            status_code=422,
            detail="Please provide a more detailed description.",
        )

    if ticket.category == "Password Reset" and not email:
        raise HTTPException(
            status_code=400,
            detail="A work email is required for password-reset requests.",
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
        except (json.JSONDecodeError, ValueError, OSError):
            raise HTTPException(
                status_code=500,
                detail="Ticket storage could not be read.",
            )

        ticket_numbers = []

        for existing_ticket in tickets:
            ticket_id = existing_ticket.get("id", "")

            if (
                isinstance(ticket_id, str)
                and ticket_id.startswith("TKT-")
                and ticket_id[4:].isdigit()
            ):
                ticket_numbers.append(int(ticket_id[4:]))

        next_number = max(ticket_numbers, default=0) + 1
        ticket_id = f"TKT-{next_number:04d}"
        current_time = datetime.now(timezone.utc).isoformat()

        new_ticket = {
            "id": ticket_id,
            "title": title,
            "description": description,
            "email": email,
            "category": ticket.category,
            "status": status,
            "admin_note": "",
            "created_at": current_time,
            "updated_at": current_time,
        }

        tickets.append(new_ticket)

        try:
            write_tickets(tickets)
        except OSError:
            raise HTTPException(
                status_code=500,
                detail="The ticket could not be saved.",
            )

    return {
        "message": "Ticket created successfully.",
        "ticket": new_ticket,
    }


@app.get("/admin/tickets")
def list_tickets(request: Request):
    require_admin(request)

    with ticket_lock:
        try:
            tickets = read_tickets()
        except (json.JSONDecodeError, ValueError, OSError):
            raise HTTPException(
                status_code=500,
                detail="Ticket storage could not be read.",
            )

    return {"tickets": tickets}


@app.patch("/admin/tickets/{ticket_id}")
def update_ticket(
    ticket_id: str,
    update: TicketUpdate,
    request: Request,
):
    require_admin(request)

    with ticket_lock:
        try:
            tickets = read_tickets()
        except (json.JSONDecodeError, ValueError, OSError):
            raise HTTPException(
                status_code=500,
                detail="Ticket storage could not be read.",
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
                        detail="The ticket update could not be saved.",
                    )

                return {
                    "message": "Ticket updated successfully.",
                    "ticket": ticket,
                }

    raise HTTPException(
        status_code=404,
        detail="Ticket not found.",
    )


# ==========================================
# CHAT MODELS
# ==========================================

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list)
    conversation_id: str | None = Field(default=None, max_length=120)


class HumanSupportRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=120)
    history: list[ChatMessage] = Field(default_factory=list)


class HumanMessageRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=4000)


class HumanRequestStatusUpdate(BaseModel):
    status: Literal["accepted", "declined", "completed"]


# ==========================================
# HUMAN ASSISTANT DETECTION
# ==========================================

def wants_human_assistance(message: str) -> bool:
    patterns = [
        r"\bhuman reviewer\b",
        r"\bhuman assistant\b",
        r"\bhuman support\b",
        r"\bhuman agent\b",
        r"\blive agent\b",
        r"\breal person\b",
        r"\breal human\b",
        r"\btalk to (?:a )?human\b",
        r"\bspeak to (?:a )?human\b",
        r"\bcontact (?:a )?human\b",
        r"\brequest (?:a )?human\b",
        r"\btalk to (?:a )?person\b",
        r"\bspeak to (?:a )?person\b",
        r"\btalk to someone\b",
        r"\bspeak to someone\b",
        r"\bneed (?:a )?human\b",
        r"\bwant (?:a )?human\b",
        r"\bneed (?:a )?human assistant\b",
        r"\bwant (?:a )?human assistant\b",
        r"\bconnect me with (?:a )?human\b",
        r"\bconnect me to (?:a )?person\b",
        r"\bcustomer service representative\b",
        r"\bsupport representative\b",
    ]

    return any(
        re.search(pattern, message, re.IGNORECASE)
        for pattern in patterns
    )


HUMAN_SUPPORT_REPLY = (
    "Of course! 😊 Click the 'Request Human Support' button below "
    "to request assistance from a human support representative. "
    "Your request will only be submitted when you click the button."
)


# ==========================================
# HUMAN SUPPORT STORAGE AND API
# ==========================================

def read_human_requests():
    if not os.path.exists(HUMAN_REQUESTS_FILE):
        return {}

    with open(HUMAN_REQUESTS_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            "Human-support storage must contain a JSON object."
        )

    return data


def write_human_requests(requests_data):
    temporary_file = HUMAN_REQUESTS_FILE + ".tmp"

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(
            requests_data,
            file,
            indent=2,
            ensure_ascii=False,
        )

    os.replace(temporary_file, HUMAN_REQUESTS_FILE)


def get_human_request(conversation_id):
    try:
        requests_data = read_human_requests()
    except (json.JSONDecodeError, ValueError, OSError):
        raise HTTPException(
            status_code=500,
            detail="Human-support storage could not be read.",
        )

    return requests_data.get(conversation_id)


def save_human_request(conversation_id, item):
    try:
        requests_data = read_human_requests()
    except (json.JSONDecodeError, ValueError, OSError):
        raise HTTPException(
            status_code=500,
            detail="Human-support storage could not be read.",
        )

    requests_data[conversation_id] = item

    try:
        write_human_requests(requests_data)
    except OSError:
        raise HTTPException(
            status_code=500,
            detail="The human-support request could not be saved.",
        )


@app.post("/human/request")
def request_human_support(payload: HumanSupportRequest):
    conversation_id = payload.conversation_id.strip()

    if not conversation_id:
        raise HTTPException(
            status_code=400,
            detail="A conversation ID is required.",
        )

    now = datetime.now(timezone.utc).isoformat()

    with human_lock:
        existing = get_human_request(conversation_id)

        if existing and existing.get("status") in {
            "pending",
            "accepted",
        }:
            return {
                "message": "A human-support request is already active.",
                "status": existing.get("status"),
                "conversation_id": conversation_id,
            }

        item = {
            "conversation_id": conversation_id,
            "status": "pending",
            "history": [
                entry.model_dump()
                for entry in payload.history[-20:]
            ],
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }

        save_human_request(conversation_id, item)

    return {
        "message": "Human-support request submitted.",
        "status": "pending",
        "conversation_id": conversation_id,
    }


@app.get("/human/status/{conversation_id}")
def human_support_status(conversation_id: str):
    with human_lock:
        item = get_human_request(conversation_id)

    if not item:
        return {
            "conversation_id": conversation_id,
            "status": "none",
            "messages": [],
        }

    return {
        "conversation_id": conversation_id,
        "status": item.get("status", "pending"),
        "messages": item.get("messages", []),
        "message": item.get("message", ""),
    }


@app.post("/human/message")
def user_human_message(payload: HumanMessageRequest):
    message = payload.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Please enter a message.",
        )

    with human_lock:
        item = get_human_request(payload.conversation_id)

        if not item:
            raise HTTPException(
                status_code=404,
                detail="Human-support request not found.",
            )

        if item.get("status") != "accepted":
            raise HTTPException(
                status_code=409,
                detail="A human agent has not accepted this request.",
            )

        now = datetime.now(timezone.utc).isoformat()

        item.setdefault("messages", []).append({
            "id": (
                f"msg-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
            ),
            "message": message,
            "sender": "user",
            "created_at": now,
        })

        item["updated_at"] = now

        save_human_request(payload.conversation_id, item)

    return {"success": True}


@app.get("/admin/human-requests")
def list_human_support_requests(request: Request):
    require_admin(request)

    with human_lock:
        try:
            requests_data = read_human_requests()
        except (json.JSONDecodeError, ValueError, OSError):
            raise HTTPException(
                status_code=500,
                detail="Human-support storage could not be read.",
            )

    return {"requests": list(requests_data.values())}


@app.patch("/admin/human-requests/{conversation_id}")
def update_human_support_request(
    conversation_id: str,
    update: HumanRequestStatusUpdate,
    request: Request,
):
    require_admin(request)

    with human_lock:
        item = get_human_request(conversation_id)

        if not item:
            raise HTTPException(
                status_code=404,
                detail="Human-support request not found.",
            )

        item["status"] = update.status
        item["updated_at"] = datetime.now(timezone.utc).isoformat()

        if update.status == "declined":
            item["message"] = (
                "Sorry, no human agent is available right now. "
                "You can request human support again or continue "
                "with the AI assistant."
            )
        elif update.status == "completed":
            item["message"] = (
                "This human-support conversation has been marked as completed."
            )

        save_human_request(conversation_id, item)

    return {
        "message": "Human-support request updated.",
        "request": item,
    }


@app.post("/admin/human-message")
def admin_human_message(
    payload: HumanMessageRequest,
    request: Request,
):
    require_admin(request)

    message = payload.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Please enter a message.",
        )

    with human_lock:
        item = get_human_request(payload.conversation_id)

        if not item:
            raise HTTPException(
                status_code=404,
                detail="Human-support request not found.",
            )

        if item.get("status") != "accepted":
            raise HTTPException(
                status_code=409,
                detail="Accept the request before replying.",
            )

        now = datetime.now(timezone.utc).isoformat()

        item.setdefault("messages", []).append({
            "id": (
                f"msg-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
            ),
            "message": message,
            "sender": "admin",
            "created_at": now,
        })

        item["updated_at"] = now

        save_human_request(payload.conversation_id, item)

    return {"message": "Reply sent to the user."}


# ==========================================
# CHROMADB
# ==========================================

client = chromadb.PersistentClient(path=CHROMA_DIR)

collection = client.get_or_create_collection(
    name="it_knowledge",
)


# ==========================================
# OLLAMA SETTINGS
# ==========================================

OLLAMA_URL = "http://localhost:11434/api/chat"
EMBEDDING_URL = "http://localhost:11434/api/embeddings"

CHAT_MODEL = "qwen2.5:7b"
EMBEDDING_MODEL = "nomic-embed-text"


OFF_TOPIC_REPLY = (
    "I'm here to help with company-related IT questions. 😊\n\n"
    "I can assist with company accounts, work devices, software access, "
    "networking, and VPN troubleshooting.\n\n"
    "Is there a company IT issue I can help you with?"
)

PERSONAL_SCOPE_REPLY = (
    "I'm sorry you're experiencing that issue. 😊\n\n"
    "VIRTANSAN AI only supports company-related IT issues, so I can't "
    "troubleshoot personal accounts, games, or devices.\n\n"
    "I can help with company accounts, work devices, software access, "
    "networking, and VPN issues."
)


# ==========================================
# MESSAGE HELPERS
# ==========================================

def normalize_message(message):
    message = message.lower().strip()
    message = re.sub(r"[^\w\s']", " ", message)
    message = re.sub(r"\s+", " ", message)
    return message.strip()


def last_assistant_message(history):
    for item in reversed(history):
        if item.role == "assistant":
            return item.content

    return ""


def is_short_follow_up(message):
    normalized = normalize_message(message)

    exact_answers = {
        "yes", "yeah", "yep", "yup", "no", "nope",
        "okay", "ok", "sure", "not yet", "still not working",
        "same issue", "please do", "that would help",
        "yes please", "no thanks", "no thank you", "not now",
    }

    if normalized in exact_answers:
        return True

    answer_patterns = [
        r"^(yes|yeah|yep|yup)\b",
        r"^(no|nope)\b",
        r"^(i can|i cannot|i can't)\b",
        r"^(i do|i don't|i do not)\b",
        r"^(it works|it does not|it doesn't)\b",
        r"^(i have|i haven't|i have not)\b",
        r"^(it is|it isn't|it is not)\b",
        r"^(not working|still not working)\b",
    ]

    return any(
        re.search(pattern, normalized)
        for pattern in answer_patterns
    )


def is_answer_to_question(message):
    normalized = normalize_message(message)

    if is_short_follow_up(message):
        return True

    answer_patterns = [
        r"^(yes|yeah|yep|yup|no|nope)\b",
        r"^(i can|i cannot|i can't)\b",
        r"^(i do|i don't|i do not)\b",
        r"^(it works|it doesn't|it does not)\b",
        r"^(i have|i haven't|i have not)\b",
        r"^(it is|it isn't|it is not)\b",
    ]

    return any(
        re.search(pattern, normalized)
        for pattern in answer_patterns
    )


def has_active_it_conversation(history):
    support_terms = (
        "vpn", "network", "internet connection",
        "access the internet", "browse the internet",
        "company account", "work account", "work laptop",
        "work device", "password", "software access",
        "troubleshoot", "troubleshooting", "it issue",
        "error message", "can't connect", "cannot connect",
        "not working", "connection issue", "connection problem",
        "wifi", "wi-fi",
    )

    for item in history:
        if item.role != "user":
            continue

        content = item.content.lower()

        if any(term in content for term in support_terms):
            return True

    return False


def is_personal_issue(history):
    personal_terms = (
        "my personal laptop", "personal laptop",
        "my personal computer", "personal computer",
        "my home computer", "personal vpn",
        "my gaming account", "my personal account",
        "my personal email", "my steam account",
        "my roblox account", "my epic games account",
    )

    for item in history:
        if item.role != "user":
            continue

        content = item.content.lower()

        if any(term in content for term in personal_terms):
            return True

    return False


def build_contextual_search_query(message, history):
    user_messages = []

    for item in history:
        if item.role != "user":
            continue

        content = item.content.strip()

        if not content or is_short_follow_up(content):
            continue

        user_messages.append(content)

    if not is_short_follow_up(message):
        user_messages.append(message.strip())

    if user_messages:
        return " ".join(user_messages[-4:])

    return message.strip()


# ==========================================
# FRONTEND
# ==========================================

@app.get("/")
def home():
    index_file = os.path.join(FRONTEND_DIR, "index.html")

    if not os.path.exists(index_file):
        raise HTTPException(
            status_code=404,
            detail="Frontend index.html was not found.",
        )

    return FileResponse(index_file)


# ==========================================
# HEALTH CHECK
# ==========================================

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "knowledge_base": collection.name,
        "documents_indexed": collection.count(),
    }


# ==========================================
# EMBEDDING FUNCTION
# ==========================================

def create_embedding(text):
    response = requests.post(
        EMBEDDING_URL,
        json={
            "model": EMBEDDING_MODEL,
            "prompt": text,
        },
        timeout=120,
    )

    response.raise_for_status()

    data = response.json()

    if "embedding" not in data:
        raise ValueError("Ollama did not return an embedding.")

    return data["embedding"]


# ==========================================
# INTENT CLASSIFICATION
# ==========================================

def classify_intent(message, history):
    recent_conversation = "\n".join(
        f"{item.role}: {item.content}"
        for item in history[-8:]
    )

    prompt = f"""
You are an intent classifier for an enterprise IT helpdesk.

Classify the latest user message into exactly one category.

IT_RELATED:
The user has an IT problem or is answering a question during an ongoing
IT support conversation.

SMALL_TALK:
A greeting or social comment unrelated to an ongoing support issue.

NO_PROBLEM:
The user clearly says they do not have a problem or no longer need help.
Do not use this category when the user answers a question with "no".

UNCLEAR:
The request is unclear and the conversation does not explain it.

OFF_TOPIC:
The user requests something unrelated to company IT.

Use the conversation history to understand the latest message.
For example, "no, I cannot" after being asked whether the user can access
the internet during VPN troubleshooting is IT_RELATED.

Return only one category name.

Conversation:
{recent_conversation}

Latest message:
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
            "options": {"temperature": 0},
        },
        timeout=120,
    )

    response.raise_for_status()

    result = (
        response.json()["message"]["content"]
        .strip()
        .upper()
    )

    allowed_categories = {
        "IT_RELATED",
        "SMALL_TALK",
        "NO_PROBLEM",
        "UNCLEAR",
        "OFF_TOPIC",
    }

    if result in allowed_categories:
        return result

    return "UNCLEAR"


# ==========================================
# COMPANY SCOPE CLASSIFICATION
# ==========================================

def classify_scope(message, history):
    recent_conversation = "\n".join(
        f"{item.role}: {item.content}"
        for item in history[-8:]
    )

    prompt = f"""
You classify requests for a company IT helpdesk.

Return exactly one category:

COMPANY:
The problem concerns a company account, work device, company application,
company network, work VPN, or another company IT service.

PERSONAL:
The problem clearly concerns a personal account, personal device,
gaming account, entertainment service, or technology unrelated to work.

UNCLEAR:
The company or personal scope cannot be determined.

Rules:
- Only company-related IT issues may be troubleshot.
- A technical issue is not automatically a company issue.
- Personal Steam, Epic Games, Roblox, social media, and personal email
  issues are PERSONAL unless company use is clearly established.
- Do not assume that "my account" means a company account.
- Use conversation history to understand short answers.
- If the user identified a company VPN and is answering a troubleshooting
  question about that VPN, classify the answer as COMPANY.
- If the user identified a personal issue, classify it as PERSONAL.
- If the scope is genuinely unclear, return UNCLEAR.

Return only COMPANY, PERSONAL, or UNCLEAR.

Conversation:
{recent_conversation}

Latest message:
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
            "options": {"temperature": 0},
        },
        timeout=120,
    )

    response.raise_for_status()

    result = (
        response.json()["message"]["content"]
        .strip()
        .upper()
    )

    if result in {"COMPANY", "PERSONAL", "UNCLEAR"}:
        return result

    return "UNCLEAR"


# ==========================================
# PASSWORD SUPPORT
# ==========================================

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
        "reset pass",
    ]

    return any(term in text for term in terms)


def get_password_reply(message, history):
    normalized = normalize_message(message)
    previous_assistant = last_assistant_message(history).lower()

    affirmative = {
        "yes", "yes please", "yeah", "yep", "yup",
        "sure", "okay", "ok", "please do", "that would help",
    }

    negative = {
        "no", "no thanks", "no thank you", "not now",
    }

    if normalized in negative:
        return (
            "That's okay. 😊 You can use your organization's official "
            "password-reset option whenever you're ready. If you can't "
            "access it, contact your IT support team."
        )

    if normalized in affirmative:
        if (
            "would you like" in previous_assistant
            or "like me to walk you through" in previous_assistant
            or "if you'd like" in previous_assistant
        ):
            return (
                "Sure! 😊 Here's the general process for resetting your "
                "work password:\n\n"
                "1. Open your organization's usual work sign-in page.\n"
                "2. Select **Forgot password?** or the equivalent option.\n"
                "3. Follow the verification steps provided by your organization.\n"
                "4. Create a new password and try signing in again.\n\n"
                "If you don't see a reset option, contact your IT support "
                "team. Never share your password or verification codes here."
            )

        if (
            "which sign-in system" in previous_assistant
            or "which application" in previous_assistant
        ):
            return (
                "Which sign-in system do you use for work—for example, "
                "Microsoft 365, Google Workspace, or another company system?"
            )

    if normalized in {
        "what", "huh", "i don't understand", "i dont understand",
    }:
        return (
            "Sorry for the confusion. 😊 I can guide you through the general "
            "work-password reset process, but your IT team may need to help "
            "if your company manages password resets."
        )

    if "work account" in normalized:
        return (
            "Got it—it's your work account. 😊 Would you like me to walk "
            "you through the general password-reset steps?"
        )

    if any(
        phrase in normalized
        for phrase in (
            "forgot my password", "forgot password",
            "forgotten password", "can't remember my password",
            "cannot remember my password", "reset my password",
            "reset password",
        )
    ):
        return (
            "No worries! 😊 Is this your work account, or are you trying "
            "to sign in to a specific application? Please don't share "
            "your password or verification codes here."
        )

    return None


# ==========================================
# CHAT ENDPOINT
# ==========================================

@app.post("/chat")
def chat(request: ChatRequest):
    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Please enter a message.",
        )

    history = request.history[-12:]

    if (
        history
        and history[-1].role == "user"
        and history[-1].content.strip() == message
    ):
        history = history[:-1]

    if wants_human_assistance(message):
        return {
            "reply": HUMAN_SUPPORT_REPLY,
            "source": "Human Support Guide",
        }

    if request.conversation_id:
        with human_lock:
            human_item = get_human_request(
                request.conversation_id.strip()
            )

        if human_item and human_item.get("status") in {
            "pending", "accepted",
        }:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Human support is handling this conversation. "
                    "Please wait for the human agent."
                ),
            )

    normalized = normalize_message(message)

    greetings = {
        "hi", "hello", "hey", "hiya", "howdy",
        "good morning", "good afternoon", "good evening",
    }

    help_messages = {
        "help", "what can you do", "what can you help me with",
        "what can you help me do", "what do you do",
        "how do i use you", "how can you help me",
    }

    if not history and normalized in greetings:
        return {
            "reply": (
                "Hey there! 😊 Welcome to VIRTANSAN AI.\n\n"
                "I'm your company IT assistant. Tell me what's happening "
                "with a company IT service, and I'll help you work through it."
            ),
            "source": "Introduction Guide",
        }

    if not history and normalized in help_messages:
        return {
            "reply": (
                "Of course! 😊 I can help with company account issues, "
                "work devices, software access, networking, VPN connections, "
                "and other company IT problems."
            ),
            "source": "Introduction Guide",
        }

    previous_assistant = last_assistant_message(history)
    previous_question = "?" in previous_assistant
    ongoing_it_issue = has_active_it_conversation(history)

    is_it_follow_up = (
        is_answer_to_question(message)
        and previous_question
        and ongoing_it_issue
    )

    try:
        if is_it_follow_up:
            intent = "IT_RELATED"
        else:
            intent = classify_intent(message, history)

        if intent == "OFF_TOPIC":
            return {
                "reply": OFF_TOPIC_REPLY,
                "source": "Scope Guard",
            }

        if intent == "NO_PROBLEM":
            return {
                "reply": (
                    "I'm here whenever you need company IT assistance."
                ),
                "source": "Conversation Guide",
            }

        if intent == "SMALL_TALK":
            return {
                "reply": (
                    "I'm here whenever you need help with a company IT issue."
                ),
                "source": "Conversation Guide",
            }

        if intent == "UNCLEAR":
            return {
                "reply": (
                    "Could you tell me a little more about what you need "
                    "help with? 😊"
                ),
                "source": "Conversation Guide",
            }

        if is_it_follow_up:
            if is_personal_issue(history):
                scope = "PERSONAL"
            else:
                scope = "COMPANY"
        else:
            scope = classify_scope(message, history)

        if scope == "PERSONAL":
            return {
                "reply": PERSONAL_SCOPE_REPLY,
                "source": "Company Scope Guard",
            }

        if scope == "UNCLEAR":
            return {
                "reply": (
                    "I can help with company-related IT issues. 😊 "
                    "Is this problem related to a company account, work "
                    "device, application, or network service?"
                ),
                "source": "Company Scope Guard",
            }

    except requests.RequestException:
        raise HTTPException(
            status_code=502,
            detail=(
                "I couldn't connect to the local AI service. "
                "Please check that Ollama is running and try again."
            ),
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
                "source": "Password Support Guide",
            }

    try:
        search_query = build_contextual_search_query(message, history)
        embedding = create_embedding(search_query)

        results = collection.query(
            query_embeddings=[embedding],
            n_results=1,
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        if documents and documents[0]:
            knowledge = documents[0]

            if metadatas and metadatas[0]:
                source = metadatas[0].get("source", "Unknown")
            else:
                source = "Unknown"
        else:
            knowledge = ""
            source = "No relevant source found"

        if not knowledge:
            return {
                "reply": (
                    "I couldn't find enough information in my knowledge base "
                    "to answer confidently. Could you explain the company IT "
                    "issue in a little more detail? Your IT support team may "
                    "need to help with company-specific settings."
                ),
                "source": source,
            }

        system_prompt = f"""
You are VIRTANSAN AI, a friendly company IT helpdesk assistant.

YOUR SCOPE:
You only support company-related IT issues, including company VPN,
company network connectivity, work accounts, work devices, and company
software access.

Do not troubleshoot personal accounts, personal gaming services, personal
devices, or technology unrelated to company operations.

CONVERSATION RULES:
1. Read the conversation history before answering.
2. Treat "yes", "no", "no, I cannot", "yes, I can", and similar messages
   as answers to the previous question when appropriate.
3. Continue troubleshooting from the last step. Do not restart the process.
4. Do not repeat a question the user has already answered.
5. If the user says they cannot access the internet during VPN troubleshooting,
   help them troubleshoot their general internet connection first.
6. If the user confirms they can access the internet, continue to the next
   VPN troubleshooting step supported by the knowledge base.
7. Ask only one clear question at a time.
8. Give simple, practical instructions.
9. Do not invent company policies, URLs, server addresses, or procedures.
10. Never ask the user to share passwords or verification codes.
11. Do not claim that a ticket was created or an action was completed unless
    the application actually confirms it.
12. If the knowledge base does not contain the needed information, say so
    and recommend contacting the IT support team.

KNOWLEDGE-BASE REFERENCE:
{knowledge}
"""

        ollama_messages = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]

        for item in history[-8:]:
            ollama_messages.append({
                "role": item.role,
                "content": item.content,
            })

        ollama_messages.append({
            "role": "user",
            "content": message,
        })

        response = requests.post(
            OLLAMA_URL,
            json={
                "model": CHAT_MODEL,
                "messages": ollama_messages,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 300,
                },
            },
            timeout=120,
        )

        response.raise_for_status()

        result = response.json()
        reply = result.get("message", {}).get("content", "").strip()

        if not reply:
            raise HTTPException(
                status_code=502,
                detail="The AI service returned an empty response.",
            )

        return {
            "reply": reply,
            "source": source,
        }

    except requests.RequestException:
        raise HTTPException(
            status_code=502,
            detail=(
                "I couldn't connect to the local AI service. "
                "Please check that Ollama is running and try again."
            ),
        )

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=500,
            detail=(
                "Something went wrong while preparing my response. "
                "Please try again."
            ),
        )


# ==========================================
# STATIC FRONTEND FILES
# ==========================================

app.mount(
    "/static",
    StaticFiles(directory=FRONTEND_DIR),
    name="static",
)