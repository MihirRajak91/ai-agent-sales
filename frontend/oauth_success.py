import streamlit as st

st.set_page_config(
    page_title="OAuth Success",
    page_icon=":white_check_mark:",
)

st.title("Google OAuth Complete")
st.success("You may close this window and return to the operator console.")
st.write(
    "If you reached this page without using the console, you can safely close the tab."
)
