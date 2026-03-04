import base64
import io
import os
import sqlite3
import sys

import pyotp
import qrcode
from dotenv import load_dotenv
from flask import (
    Flask,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
)
from markupsafe import escape
from pathlib import Path

# ---------------------------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------------------------

load_dotenv()


def get_required_config(key):
    """
    Retrieve a required environment variable.
    Aborts application startup with a clear error if the variable is missing,
    preventing the app from running in an insecure or misconfigured state.
    """
    value = os.environ.get(key)
    if not value:
        print(f"SECURITY ERROR: Required environment variable '{key}' is not set.")
        print("Application startup aborted.")
        sys.exit(1)
    return value


def get_optional_config(key, default):
    """
    Retrieve an optional environment variable.
    Falls back to the provided default value if the variable is absent or empty.
    """
    return os.environ.get(key) or default


# Application-level configuration derived from environment variables.
SECRET_KEY = get_required_config("SECRET_KEY")
DATABASE = get_optional_config("DATABASE_NAME", "data/users.db")
MAX_FAILED_ATTEMPTS = int(get_optional_config("MAX_FAILED_ATTEMPTS", 5))
FLASK_DEBUG = get_optional_config("FLASK_DEBUG", "False") == "True"

# ---------------------------------------------------------------------------
# Application initialisation
# ---------------------------------------------------------------------------

directory = Path(DATABASE).parent
directory.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = SECRET_KEY

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def get_db():
    """
    Return a SQLite connection scoped to the current request context.
    A single connection is opened per request and reused across calls,
    reducing overhead and ensuring consistent transaction state.
    """
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row  # Enables column-name access on rows
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    """
    Release the database connection at the end of every request or
    application context teardown, regardless of whether an exception occurred.
    """
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """
    Bootstrap the database schema on application startup.
    Uses CREATE TABLE IF NOT EXISTS so repeated startups are idempotent.
    Called at module level to guarantee the table exists whether the app is
    launched directly (python app.py) or via a WSGI server (gunicorn, etc.).
    """
    with app.app_context():
        db = get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username        TEXT    PRIMARY KEY,
                secret          TEXT    NOT NULL,
                failed_attempts INTEGER DEFAULT 0,
                blocked         INTEGER DEFAULT 0
            )
        """)
        db.commit()


# ---------------------------------------------------------------------------
# Helper: uniform notification responses
# ---------------------------------------------------------------------------


def notify(title, message, status=200):
    """
    Render the shared output template with a title and body message.
    Using a single template for all informational responses keeps the UI
    consistent and avoids scattering raw string returns across the codebase.

    Args:
        title   (str): Heading shown in the page <title> and <h2>.
        message (str): Descriptive body text shown to the user.
        status  (int): HTTP status code for the response (default 200).

    Returns:
        A Flask Response object with the rendered template and status code.
    """
    return render_template("output.html", title=title, message=message), status


# ---------------------------------------------------------------------------
# HTTP error handlers
# ---------------------------------------------------------------------------


@app.errorhandler(400)
def bad_request(e):
    """
    Handle 400 Bad Request errors.
    Rendered when the server cannot process the request due to malformed syntax
    or invalid input that was not caught by application-level validation.
    """
    return notify(
        "Bad Request",
        "Your request could not be understood by the server. Please check your input and try again.",
        400,
    )


@app.errorhandler(401)
def unauthorized(e):
    """
    Handle 401 Unauthorized errors.
    Rendered when authentication is required but has not been provided or has failed.
    """
    return notify(
        "Unauthorized",
        "You are not authorized to access this resource. Please log in and try again.",
        401,
    )


@app.errorhandler(403)
def forbidden(e):
    """
    Handle 403 Forbidden errors.
    Rendered when the server refuses to fulfill a valid request due to
    insufficient permissions, regardless of authentication status.
    """
    return notify("Forbidden", "You do not have permission to access this page.", 403)


@app.errorhandler(404)
def not_found(e):
    """
    Handle 404 Not Found errors.
    Rendered when the requested URL does not match any registered route.
    """
    return notify(
        "Page Not Found",
        f"The page '{request.path}' does not exist. Please check the URL or return to the login page.",
        404,
    )


@app.errorhandler(405)
def method_not_allowed(e):
    """
    Handle 405 Method Not Allowed errors.
    Rendered when a valid route is accessed with an HTTP method it does not support
    (e.g. sending a DELETE request to a GET-only endpoint).
    """
    return notify(
        "Method Not Allowed",
        f"The {request.method} method is not permitted for this URL. "
        f"Please use the correct form or link to interact with this page.",
        405,
    )


@app.errorhandler(500)
def internal_server_error(e):
    """
    Handle 500 Internal Server Error.
    Rendered as a catch-all for unhandled exceptions. The raw exception is
    intentionally not exposed to the user to avoid leaking implementation details.
    """
    return notify(
        "Internal Server Error",
        "An unexpected error occurred on the server. Please try again later or contact support if the problem persists.",
        500,
    )


# ---------------------------------------------------------------------------
# Static asset serving
# ---------------------------------------------------------------------------


@app.route("/static/styles.css")
def serve_styles():
    """
    Serve styles.css from the project root at the /static/styles.css path.
    This allows templates to reference a predictable URL regardless of
    where the working directory is at runtime.
    """
    return send_from_directory(".", "styles.css", mimetype="text/css")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """
    Root endpoint – immediately redirects visitors to the login page.
    No content is rendered here; the route exists solely to avoid a 404
    when users navigate to the application root.
    """
    return redirect("/login")


@app.route("/register", methods=["GET", "POST"])
def register():
    """
    Handle new user registration and TOTP secret provisioning.

    GET  – Renders the blank registration form.
    POST – Validates the submitted username, generates a TOTP secret,
           persists the user record, and returns a QR code the user must
           scan with an authenticator app before the account is confirmed.

    The username is stored in the session under 'temp_user' until the
    follow-up OTP verification step completes successfully.
    """
    if request.method == "POST":
        username = escape(request.form.get("username", "").strip())

        # Enforce a minimum username length to reduce trivial/garbage accounts.
        if not username or len(username) < 3:
            return notify(
                "Invalid Username",
                "Username must be at least 3 characters long. Please try again.",
                400,
            )

        db = get_db()

        # Reject duplicate registrations before issuing a new secret.
        existing_user = db.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()

        if existing_user:
            return notify(
                "Username Taken",
                f"The username '{username}' is already registered. Please choose another.",
                409,
            )

        # Generate a cryptographically random TOTP secret (RFC 6238).
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)

        db.execute(
            "INSERT INTO users (username, secret) VALUES (?, ?)", (username, secret)
        )
        db.commit()

        # Build an otpauth:// URI compatible with Google Authenticator, Authy, etc.
        uri = totp.provisioning_uri(name=username, issuer_name="OTP-Demo-App")
        qr = qrcode.make(uri)

        # Encode the QR image as base64 so it can be embedded inline in HTML
        # without requiring a separate image endpoint.
        buffer = io.BytesIO()
        qr.save(buffer, format="PNG")
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()

        # Park the username in the session; it will be promoted to a full
        # session on successful OTP verification.
        session["temp_user"] = username

        return render_template(
            "register.html", secret=secret, qr_code=qr_base64, show_otp_field=True
        )

    return render_template("register.html", show_otp_field=False)


@app.route("/verify_registration", methods=["POST"])
def verify_registration():
    """
    Confirm the OTP entered during registration to prove the user has
    successfully set up their authenticator app.

    Reads the pending username from the session rather than accepting it
    from the form, preventing an attacker from verifying a different user's
    account by tampering with form fields.

    A valid_window of 1 (±30 s) is permitted to accommodate minor clock drift
    between the server and the user's device.
    """
    username = session.get("temp_user")
    otp = request.form.get("otp", "").strip()

    # Guard against a missing or expired session (e.g. browser restart).
    if not username:
        return redirect("/register")

    db = get_db()
    user = db.execute(
        "SELECT secret FROM users WHERE username = ?", (username,)
    ).fetchone()

    if not user:
        return redirect("/register")

    totp = pyotp.TOTP(user["secret"])

    if totp.verify(otp, valid_window=1):
        # Clear the temporary session key – registration is complete.
        session.pop("temp_user", None)
        return notify(
            "Registration Successful",
            "Your account has been created and your authenticator app is linked. Go to /login to sign in.",
        )

    return notify(
        "Invalid OTP",
        "The code you entered is incorrect or has expired. Please try again.",
        401,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Authenticate an existing user via TOTP.

    GET  – Renders the login form.
    POST – Looks up the user, checks for account blocks, verifies the OTP,
           and either grants access or increments the failed-attempt counter.

    Brute-force protection:
        After MAX_FAILED_ATTEMPTS consecutive failures the account is
        permanently blocked and a dedicated blocked page is shown. A
        successful login resets the counter to zero.

    Security note:
        Returning a generic "Invalid credentials" message for both unknown
        usernames and incorrect OTPs prevents username enumeration.
    """
    if request.method == "POST":
        username = escape(request.form.get("username", "").strip())
        otp = request.form.get("otp", "").strip()

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        # Use the same response for "no such user" and "wrong OTP" to avoid
        # leaking whether a given username is registered (username enumeration).
        if not user:
            return notify(
                "Invalid Credentials",
                "Username or OTP is incorrect. Please try again.",
                401,
            )

        # A blocked account cannot authenticate regardless of OTP validity.
        if user["blocked"]:
            return render_template("blocked.html")

        totp = pyotp.TOTP(user["secret"])

        if totp.verify(otp, valid_window=1):
            # Successful authentication – reset the failure counter.
            db.execute(
                "UPDATE users SET failed_attempts = 0 WHERE username = ?", (username,)
            )
            db.commit()
            return render_template("success.html", username=username)

        # Authentication failed – record the attempt and enforce the limit.
        failed_attempts = user["failed_attempts"] + 1

        if failed_attempts >= MAX_FAILED_ATTEMPTS:
            db.execute("UPDATE users SET blocked = 1 WHERE username = ?", (username,))
            db.commit()
            return render_template("blocked.html")

        db.execute(
            "UPDATE users SET failed_attempts = ? WHERE username = ?",
            (failed_attempts, username),
        )
        db.commit()

        remaining = MAX_FAILED_ATTEMPTS - failed_attempts
        return notify(
            "Invalid OTP",
            f"The code you entered is incorrect. "
            f"You have {remaining} attempt{'s' if remaining != 1 else ''} remaining before your account is blocked.",
            401,
        )

    return render_template("login.html")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

# Initialise the database schema at import time so the table is always present
# regardless of how Flask is invoked (direct execution or WSGI server).
init_db()

if __name__ == "__main__":
    app.run(debug=FLASK_DEBUG)
