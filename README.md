# Simple TOTP Authentication

## Overview

**Simple TOTP Authentication** is a minimal Flask-based web application demonstrating Time-Based One-Time Password (TOTP) authentication using authenticator apps (e.g., Google Authenticator, Microsoft Authenticator).

The project illustrates how to:

- Generate and provision a TOTP secret
- Display a QR code for authenticator enrollment
- Verify OTP codes during registration and login
- Implement brute-force protection with account blocking
- Manage secure configuration via environment variables

This project is intended for educational and demonstration purposes.

---

## Features

- User registration with TOTP secret generation
- QR code provisioning for authenticator apps
- OTP verification during registration
- OTP-based login
- Failed login attempt tracking
- Automatic account blocking after configurable failed attempts
- Environment-based configuration management

---

## Technology Stack

- Python 3
- Flask
- SQLite
- PyOTP
- QRCode
- python-dotenv
- Google Fonts (for UI typography)

---

## Configuration

Create a `.env` file in the root directory:

```env
SECRET_KEY=your_secret_key_here
DATABASE_NAME=users.db
MAX_FAILED_ATTEMPTS=5
FLASK_DEBUG=True
```

### Required

- `SECRET_KEY`

### Optional

- `DATABASE_NAME` (default: `users.db`)
- `MAX_FAILED_ATTEMPTS` (default: `5`)
- `FLASK_DEBUG` (default: `False`)

---

## Installation

### Clone the GitHub repository

```bash
git clone https://github.com/mateocallec/simple-totp-authentication
cd simple-totp-authentication
pip install -r requirements.txt
```

GitHub repository:
[https://github.com/mateocallec/simple-totp-authentication](https://github.com/mateocallec/simple-totp-authentication)

---

## Docker

Docker Hub image:

```
mateocallec/simple-totp-authentication
```

To run using Docker:

```bash
docker run -p 5000:5000 mateocallec/simple-totp-authentication
```

---

## Run the Application

```bash
python app.py
```

The application will be available at:

```
http://localhost:5000
```

The root URL (`/`) redirects to `/login`.

---

## Security Notes

This project demonstrates:

- TOTP verification with time window tolerance
- Account lockout after repeated failed attempts
- Secure secret storage
- Environment-based secret management

⚠️ This is a demo project and should not be used as-is in production without additional hardening (HTTPS, CSRF protection, password-based primary authentication, rate limiting, secure session configuration, etc.).

---

## Author

**Matéo Florian CALLEC**
📧 [mateo@callec.net](mailto:mateo@callec.net)

---

## License

This project is licensed under the MIT License.

See the `LICENSE` file for details.
