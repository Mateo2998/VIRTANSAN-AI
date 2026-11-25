
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

from itsdangerous import (
    URLSafeTimedSerializer,
    BadSignature,
    SignatureExpired,
)

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
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

app = FastAPI(title="VIRTANSANLARA AI")

ticket_lock = threading.Lock()
human_lock = threading.Lock()
employee_lock = threading.Lock()

SESSION_SECRET = os.getenv(
    "SESSION_SECRET",
    "dev-only-change-this-session-secret",
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="virtansan_admin_session",
    same_site="lax",
    https_only=False,
)

EMPLOYEE_SESSION_COOKIE = "virtansan_employee_session"
EMPLOYEE_SESSION_MAX_AGE = 60 * 60 * 12

employee_session_serializer = URLSafeTimedSerializer(
    SESSION_SECRET,
    salt="virtansan-employee-session",
)


def current_time():
    return datetime.now(timezone.utc).isoformat()


# ==========================================
# EMPLOYEE SESSION HELPERS
# ==========================================

def create_employee_session_token(employee_id):
    return employee_session_serializer.dumps({
        "employee_id": employee_id
    })


def get_employee_id_from_cookie(request: Request):
    token = request.cookies.get(EMPLOYEE_SESSION_COOKIE)

    if not token:
        return None

    try:
        session_data = employee_session_serializer.loads(
            token,
            max_age=EMPLOYEE_SESSION_MAX_AGE,
        )

        employee_id = session_data.get("employee_id")

        if isinstance(employee_id, str) and employee_id:
            return employee_id

    except (BadSignature, SignatureExpired, TypeError, AttributeError):
        return None

    return None


def set_employee_session_cookie(response, employee_id):
    token = create_employee_session_token(employee_id)

    response.set_cookie(
        key=EMPLOYEE_SESSION_COOKIE,
        value=token,
        max_age=EMPLOYEE_SESSION_MAX_AGE,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
    )


def clear_employee_session_cookie(response):
    response.delete_cookie(
        key=EMPLOYEE_SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=False,
        samesite="lax",
    )


# ==========================================
# ADMIN AUTHENTICATION
# ==========================================

ADMIN_EMAIL = "admin@work.com"
ADMIN_PASSWORD = "admin123"


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
# JSON STORAGE HELPERS
# ==========================================

def read_json_list(file_path, error_message):
    if not os.path.exists(file_path):
        return []

    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(error_message)

    return data


def write_json(file_path, data):
    temporary_file = file_path + ".tmp"

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )

    os.replace(temporary_file, file_path)


def read_tickets():
    return read_json_list(
        TICKETS_FILE,
        "Ticket storage must contain a JSON list.",
    )


def write_tickets(tickets):
    write_json(TICKETS_FILE, tickets)


def read_employees():
    return read_json_list(
        EMPLOYEES_FILE,
        "Employee storage must contain a JSON list.",
    )


def write_employees(employees):
    write_json(EMPLOYEES_FILE, employees)


# ==========================================
# EMPLOYEE ACCOUNT STORAGE
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

        return hmac.compare_digest(actual_hash, expected_hash)

    except (ValueError, TypeError, AttributeError):
        return False


def get_logged_in_employee(request: Request):
    employee_id = get_employee_id_from_cookie(request)

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
            and employee.get("is_active", True) is True
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


def public_employee_details(employee):
    return {
        "id": employee.get("id", ""),
        "name": employee.get("name", ""),
        "email": employee.get("email", ""),
        "role": employee.get("role", "employee"),
        "is_active": employee.get("is_active", True),
        "created_at": employee.get("created_at", ""),
    }


# ==========================================
# EMPLOYEE ACCOUNT MODELS
# ==========================================

class EmployeeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=200)


class EmployeeEmailUpdate(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class AdminEmployeePasswordUpdate(BaseModel):
    password: str = Field(min_length=8, max_length=200)


class EmployeeStatusUpdate(BaseModel):
    is_active: bool


class EmployeeLogin(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class EmployeePasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


def valid_email(email):
    return bool(
        re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            email,
        )
    )


# ==========================================
# ADMIN EMPLOYEE MANAGEMENT
# ==========================================

@app.post("/admin/employees", status_code=201)
def create_employee(payload: EmployeeCreate, request: Request):
    require_admin(request)

    name = payload.name.strip()
    email = payload.email.strip().lower()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Employee name is required.",
        )

    if not valid_email(email):
        raise HTTPException(
            status_code=400,
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
            "is_active": True,
            "password_hash": hash_employee_password(payload.password),
            "created_at": current_time(),
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


@app.patch("/admin/employees/{employee_id}/email")
def update_employee_email(
    employee_id: str,
    payload: EmployeeEmailUpdate,
    request: Request,
):
    require_admin(request)

    new_email = payload.email.strip().lower()

    if not valid_email(new_email):
        raise HTTPException(
            status_code=422,
            detail="Please enter a valid email address.",
        )

    with employee_lock:
        employees = read_employees()

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

            if employee.get("email", "").strip().lower() == new_email:
                raise HTTPException(
                    status_code=409,
                    detail="That email address is already in use.",
                )

        target["email"] = new_email
        write_employees(employees)

    return {
        "message": "Employee email updated successfully.",
        "employee": public_employee_details(target),
    }


@app.patch("/admin/employees/{employee_id}/password")
def admin_change_employee_password(
    employee_id: str,
    payload: AdminEmployeePasswordUpdate,
    request: Request,
):
    require_admin(request)

    with employee_lock:
        employees = read_employees()

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

        target["password_hash"] = hash_employee_password(payload.password)
        write_employees(employees)

    return {"message": "Employee password changed successfully."}


@app.patch("/admin/employees/{employee_id}/status")
def update_employee_status(
    employee_id: str,
    payload: EmployeeStatusUpdate,
    request: Request,
):
    require_admin(request)

    with employee_lock:
        employees = read_employees()

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

        if target.get("role", "employee") != "employee":
            raise HTTPException(
                status_code=403,
                detail="This account cannot be modified here.",
            )

        target["is_active"] = payload.is_active
        write_employees(employees)

    return {
        "message": (
            "Employee account activated successfully."
            if payload.is_active
            else "Employee account deactivated successfully."
        ),
        "employee": public_employee_details(target),
    }


# ==========================================
# EMPLOYEE LOGIN AND PROFILE
# ==========================================

@app.post("/employee-login")
def employee_login(credentials: EmployeeLogin, request: Request):
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

            if employee.get("email", "").strip().lower() == email:
                employee_found = employee
                break

        if not employee_found:
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password.",
            )

        if not verify_employee_password(
            credentials.password,
            employee_found.get("password_hash", ""),
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

        if employee_found.get("is_active", True) is not True:
            raise HTTPException(
                status_code=403,
                detail="Your employee account has been deactivated. Please contact your administrator.",
            )

        employee_id = employee_found.get("id")

        if not isinstance(employee_id, str) or not employee_id:
            raise HTTPException(
                status_code=500,
                detail="The employee account is missing its ID.",
            )

    response = JSONResponse({
        "message": "Employee login successful.",
        "redirect": "/employee.html",
    })

    set_employee_session_cookie(response, employee_id)

    return response


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
    response = JSONResponse({
        "message": "Logged out successfully."
    })

    clear_employee_session_cookie(response)

    return response


@app.post("/employee-logout")
def employee_logout_legacy(request: Request):
    response = JSONResponse({
        "message": "Logged out successfully.",
        "redirect": "/",
    })

    clear_employee_session_cookie(response)

    return response


@app.post("/employee/change-password")
def employee_change_password(
    payload: EmployeePasswordChange,
    request: Request,
):
    employee = require_employee(request)

    if hmac.compare_digest(
        payload.current_password,
        payload.new_password,
    ):
        raise HTTPException(
            status_code=400,
            detail="Your new password must be different from your current password.",
        )

    with employee_lock:
        employees = read_employees()

        for stored_employee in employees:
            if not isinstance(stored_employee, dict):
                continue

            if stored_employee.get("id") != employee.get("id"):
                continue

            if not verify_employee_password(
                payload.current_password,
                stored_employee.get("password_hash", ""),
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Your current password is incorrect.",
                )

            stored_employee["password_hash"] = hash_employee_password(
                payload.new_password
            )

            write_employees(employees)

            return {
                "message": "Your password has been changed successfully."
            }

    raise HTTPException(
        status_code=401,
        detail="Employee account not found. Please log in again.",
    )


@app.get("/employee.html")
def employee_dashboard(request: Request):
    employee = get_logged_in_employee(request)

    if not employee:
        return RedirectResponse(url="/", status_code=303)

    employee_file = os.path.join(FRONTEND_DIR, "employee.html")

    if not os.path.exists(employee_file):
        raise HTTPException(
            status_code=404,
            detail="Employee dashboard was not found.",
        )

    return FileResponse(employee_file)


# ==========================================
# TICKET MODELS
# ==========================================

class TicketCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=5, max_length=3000)
    email: str = Field(default="", max_length=254)
    category: Literal["IT Support", "Password Reset"] = "IT Support"


class PublicPasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    description: str = Field(min_length=5, max_length=3000)
    confirmed: bool
    request_id: str = Field(min_length=8, max_length=120)


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
# TICKET SECURITY HELPERS
# ==========================================

def contains_sensitive_secret(text):
    patterns = [
        r"\bpassword\s*[:=]\s*\S+",
        r"\bpasscode\s*[:=]\s*\S+",
        r"\botp\s*[:=]\s*\S+",
        r"\bverification code\s*[:=]\s*\S+",
        r"\bsecurity code\s*[:=]\s*\S+",
    ]

    return any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in patterns
    )


def next_ticket_id(tickets):
    ticket_numbers = []

    for existing_ticket in tickets:
        if not isinstance(existing_ticket, dict):
            continue

        ticket_id = existing_ticket.get("id", "")

        if (
            isinstance(ticket_id, str)
            and ticket_id.startswith("TKT-")
            and ticket_id[4:].isdigit()
        ):
            ticket_numbers.append(int(ticket_id[4:]))

    next_number = max(ticket_numbers, default=0) + 1

    return f"TKT-{next_number:04d}"


def create_stored_ticket(
    title,
    description,
    email,
    category,
    status,
    request_id=None,
):
    with ticket_lock:
        try:
            tickets = read_tickets()
        except (json.JSONDecodeError, ValueError, OSError):
            raise HTTPException(
                status_code=500,
                detail="Ticket storage could not be read.",
            )

        if request_id:
            for existing_ticket in tickets:
                if (
                    isinstance(existing_ticket, dict)
                    and existing_ticket.get("request_id") == request_id
                ):
                    return existing_ticket, False

        now = current_time()

        new_ticket = {
            "id": next_ticket_id(tickets),
            "title": title,
            "description": description,
            "email": email,
            "category": category,
            "status": status,
            "admin_note": "",
            "created_at": now,
            "updated_at": now,
        }

        if request_id:
            new_ticket["request_id"] = request_id

        tickets.append(new_ticket)

        try:
            write_tickets(tickets)
        except OSError:
            raise HTTPException(
                status_code=500,
                detail="The ticket could not be saved.",
            )

    return new_ticket, True


# ==========================================
# PUBLIC PASSWORD RESET REQUEST
# ==========================================

@app.post("/public/password-reset")
def public_password_reset(payload: PublicPasswordResetRequest):
    email = payload.email.strip().lower()
    description = payload.description.strip()
    request_id = payload.request_id.strip()

    if not payload.confirmed:
        raise HTTPException(
            status_code=400,
            detail="Please confirm the password-reset request first.",
        )

    if not valid_email(email):
        raise HTTPException(
            status_code=422,
            detail="Please enter a valid email address.",
        )

    if len(description) < 5:
        raise HTTPException(
            status_code=422,
            detail="Please provide a little more information.",
        )

    if contains_sensitive_secret(description):
        raise HTTPException(
            status_code=400,
            detail="Do not include passwords, one-time codes, or verification codes in your request.",
        )

    with employee_lock:
        try:
            employees = read_employees()
        except (json.JSONDecodeError, ValueError, OSError):
            raise HTTPException(
                status_code=500,
                detail="Employee account storage could not be read.",
            )

        matching_employee = next(
            (
                employee
                for employee in employees
                if isinstance(employee, dict)
                and isinstance(employee.get("email"), str)
                and employee.get("email").strip().lower() == email
                and employee.get("role", "employee") == "employee"
            ),
            None,
        )

        if matching_employee is None:
            raise HTTPException(
                status_code=404,
                detail="This account does not exist. Please enter a registered company email address.",
            )

        if matching_employee.get("is_active", True) is not True:
            raise HTTPException(
                status_code=403,
                detail="This employee account is inactive. Please contact your administrator.",
            )

    new_ticket, created = create_stored_ticket(
        title=f"{email} - Password Reset",
        description=description,
        email=email,
        category="Password Reset",
        status="Pending Approval",
        request_id=request_id,
    )

    if not created:
        return {
            "message": "This password-reset request has already been submitted.",
            "status": "already_submitted",
            "ticket_id": new_ticket.get("id", ""),
        }

    return {
        "message": "Your password-reset request has been submitted successfully. Please wait for administrator review.",
        "status": "received",
        "ticket_id": new_ticket["id"],
    }


# ==========================================
# EMPLOYEE IT SUPPORT TICKETS
# ==========================================

@app.post("/tickets")
def create_employee_ticket(
    ticket: TicketCreate,
    request: Request,
):
    employee = require_employee(request)

    title = ticket.title.strip()
    description = ticket.description.strip()

    if len(title) < 3:
        raise HTTPException(
            status_code=422,
            detail="The ticket title must contain at least 3 characters.",
        )

    if len(description) < 5:
        raise HTTPException(
            status_code=422,
            detail="Please provide a more detailed description.",
        )

    if contains_sensitive_secret(description):
        raise HTTPException(
            status_code=400,
            detail="Do not include passwords, one-time codes, or verification codes in a ticket.",
        )

    category = ticket.category

    if category == "Password Reset":
        title = f"{employee.get('email', '')} - Password Reset"
        status = "Pending Approval"
    else:
        status = "Pending Review"

    new_ticket, created = create_stored_ticket(
        title=title,
        description=description,
        email=employee.get("email", ""),
        category=category,
        status=status,
    )

    return {
        "message": "Ticket created successfully.",
        "ticket": new_ticket,
    }


@app.get("/tickets/mine")
def list_my_tickets(request: Request):
    employee = require_employee(request)
    employee_email = employee.get("email", "").strip().lower()

    with ticket_lock:
        try:
            tickets = read_tickets()
        except (json.JSONDecodeError, ValueError, OSError):
            raise HTTPException(
                status_code=500,
                detail="Ticket storage could not be read.",
            )

    own_tickets = [
        ticket
        for ticket in tickets
        if isinstance(ticket, dict)
        and str(ticket.get("email", "")).strip().lower() == employee_email
    ]

    return {"tickets": own_tickets}


# ==========================================
# ADMIN TICKET MANAGEMENT
# ==========================================

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
        tickets = read_tickets()

        for ticket in tickets:
            if ticket.get("id") == ticket_id:
                ticket["status"] = update.status
                ticket["admin_note"] = update.admin_note.strip()
                ticket["updated_at"] = current_time()

                write_tickets(tickets)

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
    content: str = Field(max_length=4000)


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
# HUMAN SUPPORT DETECTION
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
# HUMAN SUPPORT STORAGE
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
    write_json(HUMAN_REQUESTS_FILE, requests_data)


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


def verify_human_request_owner(item, employee):
    if not item:
        return False

    stored_employee_id = item.get("employee_id")
    current_employee_id = employee.get("id")

    return (
        isinstance(stored_employee_id, str)
        and isinstance(current_employee_id, str)
        and hmac.compare_digest(
            stored_employee_id,
            current_employee_id,
        )
    )


def require_owned_human_request(conversation_id, employee):
    item = get_human_request(conversation_id)

    if not item or not verify_human_request_owner(item, employee):
        raise HTTPException(
            status_code=404,
            detail="Human-support request not found.",
        )

    return item


# ==========================================
# EMPLOYEE HUMAN SUPPORT API
# ==========================================

@app.post("/human/request")
def request_human_support(
    payload: HumanSupportRequest,
    request: Request,
):
    employee = require_employee(request)

    conversation_id = payload.conversation_id.strip()
    employee_id = employee.get("id")

    if not employee_id:
        raise HTTPException(
            status_code=401,
            detail="Employee account could not be verified.",
        )

    with human_lock:
        existing = get_human_request(conversation_id)

        if existing:
            if not verify_human_request_owner(existing, employee):
                raise HTTPException(
                    status_code=409,
                    detail="This conversation ID is already in use.",
                )

            if existing.get("status") in {
                "pending",
                "accepted",
            }:
                return {
                    "message": "A human-support request is already active.",
                    "status": existing.get("status"),
                    "conversation_id": conversation_id,
                }

        now = current_time()

        item = {
            "conversation_id": conversation_id,
            "employee_id": employee_id,
            "employee_name": employee.get("name", ""),
            "employee_email": employee.get("email", ""),
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
def human_support_status(
    conversation_id: str,
    request: Request,
):
    employee = require_employee(request)

    with human_lock:
        item = get_human_request(conversation_id)

        if not item:
            return {
                "conversation_id": conversation_id,
                "status": "none",
                "messages": [],
            }

        if not verify_human_request_owner(item, employee):
            raise HTTPException(
                status_code=404,
                detail="Human-support request not found.",
            )

        return {
            "conversation_id": conversation_id,
            "status": item.get("status", "pending"),
            "messages": item.get("messages", []),
            "message": item.get("message", ""),
        }


@app.post("/human/message")
def user_human_message(
    payload: HumanMessageRequest,
    request: Request,
):
    employee = require_employee(request)

    message = payload.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Please enter a message.",
        )

    with human_lock:
        item = require_owned_human_request(
            payload.conversation_id,
            employee,
        )

        if item.get("status") != "accepted":
            raise HTTPException(
                status_code=409,
                detail="A human agent has not accepted this request.",
            )

        now = current_time()

        item.setdefault("messages", []).append({
            "id": secrets.token_hex(8),
            "message": message,
            "sender": "user",
            "created_at": now,
        })

        item["updated_at"] = now

        save_human_request(payload.conversation_id, item)

    return {"success": True}


# ==========================================
# ADMIN HUMAN SUPPORT API
# ==========================================

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

    return {
        "requests": list(requests_data.values())
    }


@app.get("/admin/human-status/{conversation_id}")
def admin_human_support_status(
    conversation_id: str,
    request: Request,
):
    require_admin(request)

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
        item["updated_at"] = current_time()

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

        now = current_time()

        item.setdefault("messages", []).append({
            "id": secrets.token_hex(8),
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


# ==========================================
# COMPANY INFORMATION
# ==========================================

COMPANY_NAME = "VIRTANSANLARA"

COMPANY_INFORMATION = """
Company name: VIRTANSANLARA.

VIRTANSANLARA is an AI and technology company.

Its areas of specialization include:
- Networking
- Cybersecurity
- Web development
- Other information technology fields

Only these company facts have been confirmed.
Do not invent the company's founding date, location, address, history,
mission, vision, clients, employees, prices, contact details, or specific
products and services.
"""


PUBLIC_COMPANY_SYSTEM_PROMPT = f"""
You are VIRTANSANLARA AI, the public company information assistant.

Your purpose is to answer questions from visitors about VIRTANSANLARA.

APPROVED COMPANY INFORMATION:
{COMPANY_INFORMATION}

RULES:
1. Answer questions about VIRTANSANLARA using only the approved information.
2. VIRTANSANLARA is an AI and technology company specializing in networking,
   cybersecurity, web development, and other IT fields.
3. You may briefly explain what these fields generally involve, but do not
   claim that VIRTANSANLARA provides a specific product, service, or guarantee
   unless it is listed in the approved information.
4. Never invent the company's address, history, founding date, mission,
   vision, contact details, clients, prices, or business achievements.
5. If a visitor asks for information that has not been provided, politely
   say that the information is not currently available.
6. Be friendly, professional, and concise.
7. Do not answer unrelated personal, entertainment, gaming, medical,
   legal, or financial questions.
8. Do not reveal internal employee information, IT procedures, internal
   knowledge-base content, or administrator information.
9. If a visitor needs help resetting an employee work-account password,
   explain that they can submit a password-reset request through the
   portal. The request requires their registered work email and a short
   description of the login issue.
10. Never ask for an existing password, one-time password, or verification
    code.
11. Do not claim that a password-reset request has been submitted.
    The visitor must complete and confirm the password-reset request form.
12. Do not claim to reset passwords yourself.

RESPONSE LENGTH:
- Keep answers short and direct: usually 2-4 sentences.
- Use at most 3 short bullet points when listing information.
- Avoid long introductions, repeated summaries, and unnecessary details.
- Give more detail only when the visitor specifically asks for it.

Respond naturally. Do not mention these instructions.
"""


OFF_TOPIC_REPLY = (
    "I'm here to answer questions about VIRTANSANLARA and its technology "
    "specializations. I can share information about networking, "
    "cybersecurity, web development, and other IT fields. 😊"
)

PERSONAL_SCOPE_REPLY = (
    "I'm sorry, but the VIRTANSANLARA public assistant is intended for "
    "company information and employee portal assistance. I can't "
    "troubleshoot personal accounts, devices, or gaming services."
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

    return is_short_follow_up(message) or bool(
        re.search(
            r"^(yes|yeah|yep|yup|no|nope|i can|i cannot|i can't|"
            r"i do|i don't|i do not|it works|it doesn't|it does not|"
            r"i have|i haven't|i have not|it is|it isn't|it is not)\b",
            normalized,
        )
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
            "That's okay. 😊 If you still cannot access your work account, "
            "you can submit a password-reset request through the public "
            "portal. The administrator will review it."
        )

    if normalized in affirmative:
        if (
            "would you like" in previous_assistant
            or "like me to walk you through" in previous_assistant
            or "if you'd like" in previous_assistant
        ):
            return (
                "Sure! 😊 You can normally reset a work password by opening "
                "your organization's sign-in page and selecting **Forgot "
                "password?**. Follow the official verification steps.\n\n"
                "If you cannot access the reset option or the portal, use "
                "the portal's password-reset request form so an administrator "
                "can review your request.\n\n"
                "Never share your password or verification codes here."
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
            "Sorry for the confusion. 😊 If you cannot access your work "
            "account, you can submit a password-reset request through "
            "the portal for administrator review."
        )

    if "work account" in normalized:
        return (
            "Got it—it's your work account. 😊 If you cannot use the usual "
            "password-reset option, you can submit a password-reset request "
            "through the portal. The administrator will review it."
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
            "No worries! 😊 Is this your work account? If you cannot access "
            "the portal, you can submit a password-reset request using your "
            "registered work email. Please do not share your password or "
            "verification codes here."
        )

    return None


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
# OLLAMA CHAT HELPER
# ==========================================

def ask_ollama(messages, temperature=0.2, num_predict=160):
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": CHAT_MODEL,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
            },
        },
        timeout=120,
    )

    response.raise_for_status()

    result = response.json()
    reply = result.get("message", {}).get("content", "").strip()

    if not reply:
        raise ValueError("The AI service returned an empty response.")

    return reply


# ==========================================
# PUBLIC COMPANY CHAT
# ==========================================

def public_company_chat(message, history):
    normalized = normalize_message(message)

    greetings = {
        "hi", "hello", "hey", "hiya", "howdy",
        "good morning", "good afternoon", "good evening",
    }

    if normalized in greetings and not history:
        return (
            "Hello! 😊 Welcome to VIRTANSANLARA.\n\n"
            "I'm VIRTANSANLARA's public AI assistant. I can answer questions "
            "about the company and its areas of specialization, including "
            "networking, cybersecurity, and web development.\n\n"
            "What would you like to know?"
        )

    help_messages = {
        "help", "what can you do", "what can you help me with",
        "what do you do", "how can you help me",
    }

    if normalized in help_messages:
        return (
            "I can tell you about VIRTANSANLARA and its areas of specialization, "
            "including networking, cybersecurity, web development, and "
            "other IT fields. I can also guide employees who need to request "
            "a work-account password reset."
        )

    if is_password_related(message):
        password_reply = get_password_reply(message, history)

        if password_reply:
            return password_reply

        return (
            "If you cannot access your employee account, you can submit "
            "a password-reset request through the portal. You will need "
            "your registered work email and a short description of the "
            "login problem. The administrator will review your request.\n\n"
            "Never share your password or verification codes."
        )

    if re.search(
        r"\b(steam|roblox|epic games|personal gmail|my personal account)\b",
        message,
        re.IGNORECASE,
    ):
        return PERSONAL_SCOPE_REPLY

    ollama_messages = [
        {
            "role": "system",
            "content": PUBLIC_COMPANY_SYSTEM_PROMPT,
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

    return ask_ollama(
        ollama_messages,
        temperature=0.2,
        num_predict=120,
    )


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
# EMPLOYEE IT CHAT
# ==========================================

def employee_it_chat(
    message,
    history,
    conversation_id=None,
    employee_id=None,
):
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
        return (
            "Hey there! 😊 Welcome to VIRTANSANLARA AI.\n\n"
            "I'm your company IT assistant. Tell me what's happening "
            "with a company IT service, and I'll help you work through it."
        )

    if not history and normalized in help_messages:
        return (
            "Of course! 😊 I can help with company account issues, "
            "work devices, software access, networking, VPN connections, "
            "and other company IT problems."
        )

    if wants_human_assistance(message):
        return HUMAN_SUPPORT_REPLY

    if conversation_id and employee_id:
        with human_lock:
            human_item = get_human_request(conversation_id)

        if (
            human_item
            and verify_human_request_owner(
                human_item,
                {"id": employee_id},
            )
            and human_item.get("status") in {
                "pending",
                "accepted",
            }
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Human support is handling this conversation. "
                    "Please wait for the human agent."
                ),
            )

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
            return OFF_TOPIC_REPLY

        if intent == "NO_PROBLEM":
            return "I'm here whenever you need company IT assistance."

        if intent == "SMALL_TALK":
            return "I'm here whenever you need help with a company IT issue."

        if intent == "UNCLEAR":
            return (
                "Could you tell me a little more about what you need "
                "help with? 😊"
            )

        if is_it_follow_up:
            scope = (
                "PERSONAL"
                if is_personal_issue(history)
                else "COMPANY"
            )
        else:
            scope = classify_scope(message, history)

        if scope == "PERSONAL":
            return PERSONAL_SCOPE_REPLY

        if scope == "UNCLEAR":
            return (
                "I can help with company-related IT issues. 😊 "
                "Is this problem related to a company account, work "
                "device, application, or network service?"
            )

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
            return password_reply

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
        else:
            knowledge = ""

        if not knowledge:
            return (
                "I couldn't find enough information in my knowledge base "
                "to answer confidently. Could you explain the company IT "
                "issue in a little more detail? Your IT support team may "
                "need to help with company-specific settings."
            )

        system_prompt = f"""
You are VIRTANSANLARA AI, a friendly company IT helpdesk assistant.

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
13. Keep responses concise: usually 2-4 short sentences.
14. For troubleshooting, give only 1-3 clear steps at a time.
15. Avoid long introductions, repeated explanations, and unnecessary summaries.
16. Ask only one short follow-up question when needed.
17. Give a longer explanation only when the employee specifically requests it.

RESPONSE STYLE:
- Be friendly, natural, and direct.
- Use simple words and short sentences.
- Prefer short numbered steps over long paragraphs.
- Do not repeat the entire troubleshooting procedure after every reply.

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

        return ask_ollama(
            ollama_messages,
            temperature=0.2,
            num_predict=160,
        )

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
# CHAT ENDPOINT
# ==========================================

@app.post("/chat")
def chat(payload: ChatRequest, request: Request):
    message = payload.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Please enter a message.",
        )

    history = payload.history[-12:]

    if (
        history
        and history[-1].role == "user"
        and history[-1].content.strip() == message
    ):
        history = history[:-1]

    employee = get_logged_in_employee(request)

    try:
        if employee:
            reply = employee_it_chat(
                message,
                history,
                payload.conversation_id.strip()
                if payload.conversation_id
                else None,
                employee.get("id"),
            )

            mode = "employee"
        else:
            reply = public_company_chat(message, history)
            mode = "public"

        return {
            "reply": reply,
            "mode": mode,
        }

    except requests.RequestException:
        raise HTTPException(
            status_code=502,
            detail=(
                "I couldn't connect to the local AI service. "
                "Please check that Ollama is running and try again."
            ),
        )


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
        "chat_modes": [
            "public_company_information",
            "authenticated_employee_it_helpdesk",
        ],
    }


# ==========================================
# STATIC FRONTEND FILES
# ==========================================

app.mount(
    "/static",
    StaticFiles(directory=FRONTEND_DIR),
    name="static",
)
