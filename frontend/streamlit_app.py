import io
from datetime import datetime
from typing import Any, Dict, Optional

import requests
import streamlit as st

st.set_page_config(
    page_title="Sales Assistant Operator Console",
    page_icon=":briefcase:",
    layout="wide",
)


def init_state() -> None:
    defaults = {
        "api_base_url": "http://localhost:8000",
        "api_token": "",
        "auth_email": "",
        "auth_password": "",
        "auth_org_id": "",
        "auth_branch_id": "",
        "auth_name": "",
        "conversation_id": "demo-thread",
        "chat_history": [],
        "leads": [],
        "lead_search_result": None,
        "oauth_authorize_url": "",
        "oauth_state": "",
        "oauth_connected": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def auth_headers() -> Dict[str, str]:
    token = st.session_state.get("api_token", "").strip()
    if not token:
        return {}
    if not token.lower().startswith("bearer "):
        token = f"Bearer {token}"
    return {"Authorization": token}


def api_request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, Any]] = None,
) -> requests.Response:
    base_url = st.session_state.get("api_base_url", "").rstrip("/")
    if not base_url:
        raise ValueError("API base URL is not configured.")
    url = f"{base_url}{path}"
    headers = auth_headers()
    response = requests.request(
        method,
        url,
        params=params,
        json=json,
        files=files,
        headers=headers,
        timeout=60,
    )
    return response


def auth_post(path: str, payload: Dict[str, Any]) -> requests.Response:
    base_url = st.session_state.get("api_base_url", "").rstrip("/")
    if not base_url:
        raise ValueError("API base URL is not configured.")
    url = f"{base_url}{path}"
    response = requests.post(url, json=payload, timeout=30)
    return response


def render_sidebar() -> None:
    st.sidebar.header("Connection")
    st.sidebar.text_input(
        "API Base URL",
        key="api_base_url",
        help="Root URL for the FastAPI backend (e.g., http://localhost:8000)",
    )
    st.sidebar.text_input(
        "Bearer Token",
        key="api_token",
        type="password",
        help="Paste `Bearer <token>` or just the JWT issued by /auth/token",
    )
    st.sidebar.text_input(
        "Conversation ID",
        key="conversation_id",
        help="Specify which conversation thread to append chat messages to.",
    )
    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Tip: generate a dev token via `/auth/token/dev` and paste it here."
    )


def authentication_tab() -> None:
    st.subheader(":lock: Authentication")
    st.write(
        "Register a new tenant user or sign in to retrieve a JWT. "
        "Successful responses update the sidebar token automatically."
    )

    register_col, login_col = st.columns(2)

    with register_col:
        st.markdown("#### Register")
        with st.form("register-form"):
            email = st.text_input(
                "Email",
                key="auth_email",
                placeholder="user@example.com",
            )
            password = st.text_input(
                "Password (min 8 characters)",
                type="password",
                key="auth_password",
            )
            name = st.text_input(
                "Display name (optional)",
                key="auth_name",
            )
            org_id = st.text_input(
                "Organisation ID",
                key="auth_org_id",
            )
            branch_id = st.text_input(
                "Branch ID",
                key="auth_branch_id",
            )
            submitted = st.form_submit_button("Register & Retrieve Token")

            if submitted:
                if len(password) < 8:
                    st.error("Password must be at least 8 characters long.")
                elif not email or not org_id or not branch_id:
                    st.error("Email, organisation ID, and branch ID are required.")
                else:
                    payload = {
                        "email": email.strip(),
                        "password": password,
                        "name": name.strip() or None,
                        "org_id": org_id.strip(),
                        "branch_id": branch_id.strip(),
                    }
                    try:
                        response = auth_post("/auth/register", payload)
                        if response.ok:
                            token = response.json().get("access_token")
                            if token:
                                st.session_state.api_token = token
                                st.success("Registration successful. Token stored in sidebar.")
                                st.code(token, language="text")
                            else:
                                st.warning("Registration succeeded but no token was returned.")
                        else:
                            st.error(f"Registration failed: {response.status_code}")
                            with st.expander("Response details"):
                                st.write(response.text)
                    except Exception as exc:  # pragma: no cover - UI path
                        st.error(f"Registration request error: {exc}")

    with login_col:
        st.markdown("#### Log In")
        with st.form("login-form"):
            login_email = st.text_input(
                "Email",
                key="login_email_input",
                placeholder="user@example.com",
            )
            login_password = st.text_input(
                "Password",
                type="password",
                key="login_password_input",
            )
            submitted = st.form_submit_button("Log In & Retrieve Token")

            if submitted:
                if not login_email or not login_password:
                    st.error("Email and password are required.")
                else:
                    payload = {
                        "email": login_email.strip(),
                        "password": login_password,
                    }
                    try:
                        response = auth_post("/auth/login", payload)
                        if response.ok:
                            token = response.json().get("access_token")
                            if token:
                                st.session_state.api_token = token
                                st.success("Login successful. Token stored in sidebar.")
                                st.code(token, language="text")
                            else:
                                st.warning("Login succeeded but no token was returned.")
                        else:
                            st.error(f"Login failed: {response.status_code}")
                            with st.expander("Response details"):
                                st.write(response.text)
                    except Exception as exc:  # pragma: no cover - UI path
                        st.error(f"Login request error: {exc}")


def google_oauth_tab() -> None:
    st.subheader(":key: Google Calendar OAuth")
    if not auth_headers():
        st.info("Provide a bearer token in the sidebar to manage Google OAuth.")
        return

    st.markdown(
        "1. Generate the authorisation link.\n"
        "2. Open it in a new tab, complete the Google consent flow, and wait for the success page.\n"
        "3. Return here and check the connection status."
    )

    if st.button("Generate Authorisation URL"):
        try:
            response = api_request("GET", "/oauth/google/init")
            if response.ok:
                data = response.json()
                auth_url = data.get("authorization_url")
                st.session_state.oauth_authorize_url = auth_url or ""
                st.session_state.oauth_state = data.get("state", "")
                if auth_url:
                    st.success("Authorisation URL generated. Open the link below in a new tab.")
                    st.markdown(f"[Connect Google Calendar]({auth_url})")
                else:
                    st.warning("Request succeeded but no URL was returned.")
            else:
                st.error(f"Failed to generate authorisation URL: {response.status_code}")
                with st.expander("Response details"):
                    st.write(response.text)
        except Exception as exc:  # pragma: no cover - UI path
            st.error(f"Error while requesting authorisation URL: {exc}")

    if st.button("Check Connection Status"):
        try:
            response = api_request("GET", "/oauth/google/status")
            if response.ok:
                data = response.json()
                connected = data.get("connected")
                st.session_state.oauth_connected = connected
                if connected:
                    st.success("Google Calendar is connected for this tenant.")
                else:
                    st.warning("Google Calendar is not connected yet.")
            else:
                st.error(f"Failed to check status: {response.status_code}")
                with st.expander("Response details"):
                    st.write(response.text)
        except Exception as exc:  # pragma: no cover - UI path
            st.error(f"Error checking OAuth status: {exc}")

    if st.session_state.get("oauth_authorize_url"):
        st.caption("Last generated URL:")
        st.code(st.session_state.oauth_authorize_url, language="text")

    if st.session_state.get("oauth_connected") is not None:
        status = "connected :white_check_mark:" if st.session_state.oauth_connected else "not connected :x:"
        st.info(f"Latest status: Google Calendar is {status}.")


def document_ingestion_tab() -> None:
    st.subheader(":page_facing_up: Document Ingestion")
    uploaded_file = st.file_uploader(
        "Upload PDF for knowledge base ingestion", type=["pdf"]
    )
    if uploaded_file:
        if st.button("Ingest Document"):
            try:
                files = {
                    "file": (
                        uploaded_file.name,
                        uploaded_file.getvalue(),
                        uploaded_file.type or "application/pdf",
                    )
                }
                response = api_request("POST", "/api/ingest", files=files)
                if response.ok:
                    payload = response.json()
                    st.success("Ingestion complete")
                    st.json(payload)
                else:
                    st.error(f"Ingestion failed: {response.status_code}")
                    with st.expander("Response details"):
                        st.write(response.text)
            except Exception as exc:  # pragma: no cover - UI path
                st.error(f"Error during ingestion: {exc}")
    else:
        st.info("Choose a PDF to enable the ingest button.")


def chat_console_tab() -> None:
    st.subheader(":speech_balloon: Chat Console")
    conversation_id = st.session_state.get("conversation_id")
    if not conversation_id:
        st.warning("Set a conversation ID in the sidebar to enable chat.")
        return

    chat_col, history_col = st.columns([2, 1])
    with chat_col:
        user_message = st.text_area("Send a message", height=120, key="chat_input")
        if st.button("Send Message"):
            if not user_message.strip():
                st.warning("Enter a message before sending.")
            else:
                payload = {
                    "conversation_id": conversation_id,
                    "query": user_message.strip(),
                }
                try:
                    response = api_request("POST", "/api/chat", json=payload)
                    if response.ok:
                        data = response.json()
                        record = {
                            "timestamp": datetime.utcnow().isoformat(),
                            "user": user_message.strip(),
                            "assistant": data.get("answer", ""),
                            "intent": data.get("intent", {}),
                            "lead_id": data.get("lead_id"),
                            "sources": data.get("sources", []),
                        }
                        st.session_state.chat_history.append(record)
                        st.success("Message sent")
                        st.write("**Assistant Response**")
                        st.write(data.get("answer", ""))
                        if data.get("intent"):
                            with st.expander("Detected Intent"):
                                st.json(data["intent"])
                        if data.get("sources"):
                            with st.expander("Sources"):
                                st.json(data["sources"])
                    else:
                        st.error(
                            f"Chat request failed: {response.status_code}",
                        )
                        with st.expander("Response details"):
                            st.write(response.text)
                except Exception as exc:  # pragma: no cover - UI path
                    st.error(f"Chat request error: {exc}")

    with history_col:
        st.write("### Recent Messages")
        if st.session_state.chat_history:
            for entry in reversed(st.session_state.chat_history[-10:]):
                st.markdown(
                    f"**You:** {entry['user']}\n\n"
                    f"**Assistant:** {entry['assistant']}"
                )
                if entry.get("lead_id"):
                    st.caption(f"Lead captured: {entry['lead_id']}")
                st.divider()
        else:
            st.info("No messages yet. Send a message to start the conversation.")


def leads_and_appointments_tab() -> None:
    st.subheader(":card_index_dividers: Leads & Appointments")
    if st.button("Refresh Leads"):
        try:
            response = api_request("GET", "/api/leads")
            if response.ok:
                st.session_state.leads = response.json()
                st.success("Leads refreshed")
            else:
                st.error(f"Failed to fetch leads: {response.status_code}")
                with st.expander("Response details"):
                    st.write(response.text)
        except Exception as exc:  # pragma: no cover - UI path
            st.error(f"Error fetching leads: {exc}")

    leads = st.session_state.get("leads", [])
    if not leads:
        st.info("No leads available. Trigger booking or purchase intents in chat.")
        return

    def format_datetime(value: Optional[str]) -> str:
        if not value:
            return ""
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime(
                "%Y-%m-%d %H:%M"
            )
        except ValueError:
            return value

    table_rows = []
    for lead in leads:
        table_rows.append(
            {
                "Lead ID": lead.get("id"),
                "Intent": lead.get("intent"),
                "Confidence": lead.get("confidence"),
                "Status": lead.get("status"),
                "Latest Message": lead.get("latest_message"),
                "Appointment Start": format_datetime(lead.get("appointment_start")),
                "Appointment End": format_datetime(lead.get("appointment_end")),
                "Calendar ID": lead.get("calendar_id"),
                "Event ID": lead.get("appointment_event_id"),
            }
        )

    st.dataframe(table_rows, use_container_width=True)


def lead_search_tab() -> None:
    st.subheader(":mag: Lead Search")
    query = st.text_area(
        "Search Query",
        value=st.session_state.get("lead_search_query", ""),
        placeholder="Example: show open leads\n(You can also paste a JSON payload to bypass the LLM.)",
        height=120,
    )
    summarize = st.checkbox(
        "Include summary (requires Gemini)",
        value=st.session_state.get("lead_search_summarize", False),
    )

    if st.button("Run Search"):
        st.session_state["lead_search_query"] = query
        st.session_state["lead_search_summarize"] = summarize

        if not query.strip():
            st.warning("Enter a natural-language query or JSON payload.")
        else:
            try:
                params = {"q": query}
                if summarize:
                    params["summarize"] = "true"
                response = api_request("GET", "/api/leads/search", params=params)
                if response.ok:
                    payload = response.json()
                    st.session_state.lead_search_result = payload
                    st.success(f"Found {payload.get('count', 0)} lead(s).")
                else:
                    st.error(f"Search failed: {response.status_code}")
                    with st.expander("Response details"):
                        st.write(response.text)
            except Exception as exc:  # pragma: no cover - UI path
                st.error(f"Lead search error: {exc}")

    result = st.session_state.get("lead_search_result")
    if result:
        query_meta = result.get("query")
        if query_meta:
            with st.expander("Executed Filter", expanded=False):
                st.json(query_meta)
        friendly_text = _friendly_lead_summary(result)
        if friendly_text:
            st.info(friendly_text)
        if result.get("results"):
            st.json(result["results"])
        else:
            st.write("No leads matched the query yet.")
    else:
        st.caption("Run a search to see results here.")


def render_tabs() -> None:
    tabs = st.tabs(
        [
            "Authentication",
            "Google OAuth",
            "Document Ingestion",
            "Chat Console",
            "Leads & Appointments",
            "Lead Search",
        ]
    )
    with tabs[0]:
        authentication_tab()
    with tabs[1]:
        google_oauth_tab()
    with tabs[2]:
        document_ingestion_tab()
    with tabs[3]:
        chat_console_tab()
    with tabs[4]:
        leads_and_appointments_tab()
    with tabs[5]:
        lead_search_tab()


def _friendly_lead_summary(result: dict | None) -> str:
    if not result:
        return ""
    summary = result.get("summary")
    if summary:
        return summary

    count = result.get("count", 0)
    filter_doc = result.get("query", {}).get("filter", {})
    filter_parts = [
        f"{key}={value}"
        for key, value in filter_doc.items()
        if key not in {"org_id", "branch_id"}
    ]
    if filter_parts:
        filter_text = ", ".join(filter_parts)
    else:
        filter_text = "current tenant scope"

    lines = [f"{count} lead(s) matched the filters ({filter_text})."]
    results = result.get("results") or []
    if results:
        preview = []
        for lead in results[:3]:
            parts = []
            if "intent" in lead:
                parts.append(lead["intent"])
            if "status" in lead:
                parts.append(f"status={lead['status']}")
            if "confidence" in lead:
                parts.append(f"confidence={lead['confidence']:.2f}")
            preview.append(f"{lead.get('conversation_id', lead.get('_id'))}: " + ", ".join(parts))
        lines.append("Preview: " + "; ".join(preview))

    return " ".join(lines)


def main() -> None:
    init_state()
    st.title("Sales Assistant Operator Console")
    render_sidebar()
    render_tabs()


if __name__ == "__main__":
    main()
