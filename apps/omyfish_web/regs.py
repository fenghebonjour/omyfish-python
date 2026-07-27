"""Regs & Tips tab — free-form Q&A over Quebec fishing regulations and
angling tips, backed by the regs_advisor domain in the shared omyfish-ai
service. Thin chat UI; all retrieval/LLM logic lives in the service."""

import streamlit as st

from apps.omyfish_web.regs_client import fetch_ask

_HISTORY_KEY = "regs_chat_history"


def render_regs_tab():
    st.caption("Ask about Quebec fishing regulations, limits, or tackle tips.")
    st.caption("⚠️ Informational only — verify current regulations at quebec.ca before fishing.")

    if _HISTORY_KEY not in st.session_state:
        st.session_state[_HISTORY_KEY] = []

    for message in st.session_state[_HISTORY_KEY]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input("e.g. What's the walleye limit in zone 27?")
    if question:
        st.session_state[_HISTORY_KEY].append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                result = fetch_ask(question)
            if result:
                st.markdown(result["answer"])
                if result.get("sources"):
                    st.caption("Sources: " + ", ".join(result["sources"]))
            else:
                st.error("Couldn't reach the regs assistant — try again in a moment.")

        st.session_state[_HISTORY_KEY].append({
            "role": "assistant",
            "content": result["answer"] if result else "Couldn't reach the regs assistant — try again in a moment.",
        })
