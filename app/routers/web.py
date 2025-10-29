from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["web"])

LOGIN_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Sales Agent Login</title>
  <style>
    :root {
      color-scheme: light dark;
    }
    body {
      font-family: Arial, sans-serif;
      margin: 0;
      padding: 0;
      background: #f5f6fa;
      color: #222;
      min-height: 100vh;
      display: flex;
      justify-content: center;
      align-items: center;
    }
    .container {
      max-width: 960px;
      width: 100%;
      padding: 2rem;
      background: #fff;
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.08);
      border-radius: 12px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 2rem;
    }
    h1 {
      grid-column: 1 / -1;
      margin: 0 0 1.5rem 0;
      font-size: 1.75rem;
      text-align: center;
      color: #1f2937;
    }
    form {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      padding: 1.5rem;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      background: #fafafa;
    }
    label {
      font-weight: 600;
      font-size: 0.95rem;
    }
    input {
      padding: 0.65rem 0.75rem;
      border: 1px solid #d1d5db;
      border-radius: 6px;
      font-size: 0.95rem;
    }
    button {
      padding: 0.75rem;
      font-size: 1rem;
      background: #2563eb;
      border: none;
      color: #fff;
      border-radius: 6px;
      cursor: pointer;
      transition: background 0.2s ease-in-out;
    }
    button:hover {
      background: #1d4ed8;
    }
    .messages {
      grid-column: 1 / -1;
      padding: 1rem;
      background: #eef2ff;
      border-radius: 10px;
      min-height: 100px;
      border: 1px solid #c7d2fe;
      color: #1f2937;
      font-size: 0.95rem;
      line-height: 1.5;
      white-space: pre-wrap;
    }
    .token {
      word-break: break-all;
      background: #111827;
      color: #10b981;
      padding: 0.75rem;
      border-radius: 8px;
      margin-top: 0.5rem;
      font-family: "Courier New", monospace;
      font-size: 0.85rem;
    }
    .actions {
      display: flex;
      gap: 0.5rem;
      margin-top: 0.5rem;
    }
    @media (max-width: 720px) {
      body {
        padding: 1rem;
        background: #fff;
      }
      .container {
        box-shadow: none;
        padding: 1rem;
      }
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>Multi-tenant Sales Agent Access</h1>

    <form id="register-form">
      <h2>Create an Account</h2>
      <label for="register-email">Email</label>
      <input type="email" id="register-email" required />

      <label for="register-password">Password (min 8 chars)</label>
      <input type="password" id="register-password" minlength="8" required />

      <label for="register-name">Display name</label>
      <input type="text" id="register-name" placeholder="Optional" />

      <label for="register-org">Organisation ID</label>
      <input type="text" id="register-org" required />

      <label for="register-branch">Branch ID</label>
      <input type="text" id="register-branch" required />

      <button type="submit">Register &amp; Get Token</button>
    </form>

    <form id="login-form">
      <h2>Sign In</h2>
      <label for="login-email">Email</label>
      <input type="email" id="login-email" required />

      <label for="login-password">Password</label>
      <input type="password" id="login-password" required />

      <button type="submit">Sign In &amp; Get Token</button>
    </form>

    <div class="messages" id="messages">
      Enter your tenant details to register. Once you login, your bearer token will show up here and is stored
      in local storage for reuse.
    </div>
  </div>

  <script>
    const messagesEl = document.getElementById("messages");
    const TOKEN_STORAGE_KEY = "sales-agent-token";

    function setMessage(text) {
      messagesEl.textContent = text;
    }

    function showToken(token, source) {
      localStorage.setItem(TOKEN_STORAGE_KEY, token);

      messagesEl.innerHTML = `
        <strong>${source} successful.</strong>
        <div class="token">${token}</div>
        <div class="actions">
          <button type="button" onclick="copyToken()">Copy token</button>
          <button type="button" onclick="clearToken()">Clear token</button>
        </div>
        <p>Add the token to API requests as <code>Authorization: Bearer &lt;token&gt;</code>.</p>
      `;
    }

    function copyToken() {
      const token = localStorage.getItem(TOKEN_STORAGE_KEY);
      if (!token) {
        setMessage("No token available in local storage.");
        return;
      }
      navigator.clipboard.writeText(token)
        .then(() => alert("Token copied to clipboard."))
        .catch(() => alert("Unable to copy automatically. Please copy the token manually from the display."));
    }

    function clearToken() {
      localStorage.removeItem(TOKEN_STORAGE_KEY);
      setMessage("Stored token cleared. Sign in again to retrieve a new one.");
    }

    async function handleRegister(event) {
      event.preventDefault();
      const payload = {
        email: document.getElementById("register-email").value,
        password: document.getElementById("register-password").value,
        name: document.getElementById("register-name").value || null,
        org_id: document.getElementById("register-org").value,
        branch_id: document.getElementById("register-branch").value,
      };
      try {
        const response = await fetch("/auth/register", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Registration failed");
        }
        showToken(data.access_token, "Registration");
      } catch (error) {
        setMessage(error.message || "Registration failed");
      }
    }

    async function handleLogin(event) {
      event.preventDefault();
      const payload = {
        email: document.getElementById("login-email").value,
        password: document.getElementById("login-password").value,
      };
      try {
        const response = await fetch("/auth/login", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Login failed");
        }
        showToken(data.access_token, "Login");
      } catch (error) {
        setMessage(error.message || "Login failed");
      }
    }

    document.getElementById("register-form").addEventListener("submit", handleRegister);
    document.getElementById("login-form").addEventListener("submit", handleLogin);

    (function preloadToken() {
      const token = localStorage.getItem(TOKEN_STORAGE_KEY);
      if (token) {
        showToken(token, "Existing token");
      }
    })();
  </script>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
async def login_page() -> HTMLResponse:
    return HTMLResponse(content=LOGIN_PAGE_HTML)
