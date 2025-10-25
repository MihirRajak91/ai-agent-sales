import io
from datetime import datetime
from typing import Any, Dict, Optional

import requests
import streamlit as st

st.set_page_config(
    page_title="Sales Assistant Operator Console",
    page_icon="💼",
    layout="wide",
)


def init_state() -> None:
    defaults = {
        "api_base_url": "http://localhost:8000",
        "api_token": "",
        "conversation_id": "demo-thread",
        "chat_history": [],
        "leads": [],
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


def document_ingestion_tab() -> None:
    st.subheader("📄 Document Ingestion")
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
    st.subheader("💬 Chat Console")
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
    st.subheader("📇 Leads & Appointments")
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


def render_tabs() -> None:
    tabs = st.tabs(
        [
            "Document Ingestion",
            "Chat Console",
            "Leads & Appointments",
        ]
    )
    with tabs[0]:
        document_ingestion_tab()
    with tabs[1]:
        chat_console_tab()
    with tabs[2]:
        leads_and_appointments_tab()


def main() -> None:
    init_state()
    st.title("Sales Assistant Operator Console")
    render_sidebar()
    render_tabs()


if __name__ == "__main__":
    main()
