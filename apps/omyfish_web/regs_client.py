"""Thin HTTP client for the regs_advisor domain in the shared omyfish-ai
service (sibling to bite_prediction — see timing.py for the same pattern).
Used by the Identify tab to show legal-limit and consumption-advisory
info cards next to a fish ID, and by any future "Regs & Tips" chat tab."""

import requests
import streamlit as st

from shared.config import settings


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_limits(lat: float, lon: float, species: str | None = None) -> dict | None:
    params = {"lat": lat, "lon": lon}
    if species:
        params["species"] = species
    try:
        resp = requests.get(f"{settings.bite_service_url}/regs/limits", params=params, timeout=10)
        if resp.status_code != 200:
            return None
        return resp.json()
    except requests.RequestException:
        return None


def fetch_ask(question: str) -> dict | None:
    try:
        resp = requests.post(
            f"{settings.bite_service_url}/regs/ask", json={"question": question}, timeout=30,
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    except requests.RequestException:
        return None


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_zones_geojson() -> dict | None:
    try:
        resp = requests.get(f"{settings.bite_service_url}/regs/zones/geojson", timeout=15)
        if resp.status_code != 200:
            return None
        return resp.json()
    except requests.RequestException:
        return None


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_consumption_stations(lat: float, lon: float, limit: int = 15) -> list[dict] | None:
    try:
        resp = requests.get(
            f"{settings.bite_service_url}/regs/consumption/stations",
            params={"lat": lat, "lon": lon, "limit": limit}, timeout=10,
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    except requests.RequestException:
        return None


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_consumption(lat: float, lon: float, species: str, size_cm: float | None = None) -> dict | None:
    params = {"lat": lat, "lon": lon, "species": species}
    if size_cm:
        params["size_cm"] = size_cm
    try:
        resp = requests.get(f"{settings.bite_service_url}/regs/consumption", params=params, timeout=10)
        if resp.status_code != 200:
            return None
        return resp.json()
    except requests.RequestException:
        return None
