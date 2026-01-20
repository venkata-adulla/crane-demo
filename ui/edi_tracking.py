from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

import streamlit as st

from api.n8n_client import N8NClient


def _unwrap_payload(payload: Any) -> Optional[Dict[str, Any]]:
    if isinstance(payload, dict):
        if "output" in payload or "actual" in payload or "boomi" in payload or "mft" in payload:
            return payload
        if "data" in payload:
            return _unwrap_payload(payload.get("data"))
        if "json" in payload and isinstance(payload.get("json"), dict):
            return payload.get("json")
        return payload
    if isinstance(payload, list):
        merged: Dict[str, Any] = {}
        found = False
        for item in payload:
            unwrapped = _unwrap_payload(item)
            if not unwrapped:
                continue
            if any(k in unwrapped for k in ("output", "actual", "boomi", "mft")):
                merged.update(unwrapped)
                found = True
        if found:
            return merged
    return None


def _maybe_parse_json(payload: Any) -> Any:
    if isinstance(payload, str):
        text = payload.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return payload
    if isinstance(payload, dict) and isinstance(payload.get("text"), str):
        return _maybe_parse_json(payload.get("text"))
    return payload


def _merge_data_list(payload: Any) -> Dict[str, Any]:
    payload = _maybe_parse_json(payload)
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        items = payload.get("data")
    elif isinstance(payload, list):
        items = payload
    else:
        return {}

    merged: Dict[str, Any] = {}
    for item in items:
        item = _maybe_parse_json(item)
        if isinstance(item, dict):
            merged.update(item)
    return merged


def _extract_key(payload: Any, key: str) -> Any:
    payload = _maybe_parse_json(payload)
    if isinstance(payload, dict):
        if key in payload:
            return payload.get(key)
        if "data" in payload:
            return _extract_key(payload.get("data"), key)
    if isinstance(payload, list):
        for item in payload:
            found = _extract_key(item, key)
            if found is not None:
                return found
    return None


def _normalize_actual(actual: Any) -> List[Dict[str, Any]]:
    if actual is None:
        return []
    if isinstance(actual, list):
        return [row for row in actual if isinstance(row, dict)]
    if isinstance(actual, dict):
        if actual and all(isinstance(k, (int, str)) and str(k).isdigit() for k in actual.keys()):
            ordered_items = [actual[k] for k in sorted(actual.keys(), key=lambda k: int(k))]
            return [row for row in ordered_items if isinstance(row, dict)]
        return [actual]
    return [{"value": actual}]


def _ordered_columns(rows: Iterable[Dict[str, Any]]) -> List[str]:
    seen: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.append(key)
    return seen or ["value"]


def _display_cell(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, default=str)[:200] + "..."
    text = str(value)
    if len(text) > 200:
        return text[:200] + "..."
    return text


def _get_incoming_data(row: Dict[str, Any]) -> Any:
    for key, value in row.items():
        if key.lower() == "incomingdata":
            return value
    return None


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, str) and value.strip().lower() in {"na", "n/a", "null"}:
        return True
    if isinstance(value, (list, tuple, set)) and len(value) == 0:
        return True
    if isinstance(value, dict) and len(value) == 0:
        return True
    return False


def _filter_empty_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if all(_is_empty_value(value) for value in row.values()):
            continue
        cleaned.append(row)
    return cleaned


def _render_incoming_dialog(title: str, data: Any) -> None:
    @st.dialog(title)
    def _dialog() -> None:
        if isinstance(data, (dict, list)):
            st.json(data)
        else:
            st.text_area("incomingData", value=str(data), height=320)

    _dialog()


def _render_actual_table(rows: List[Dict[str, Any]]) -> None:
    rows = _filter_empty_rows(rows)
    if not rows:
        st.write("NA")
        return

    columns = [c for c in _ordered_columns(rows) if c.lower() != "incomingdata"]
    display_rows: List[Dict[str, Any]] = []
    incoming_lookup: Dict[int, Any] = {}
    for idx, row in enumerate(rows):
        ordered: Dict[str, Any] = {}
        value = _get_incoming_data(row)
        if value not in (None, "", []):
            incoming_lookup[idx] = value
        for key in columns:
            ordered[key] = _display_cell(row.get(key))
        display_rows.append(ordered)

    row_height = 35
    header_height = 38
    max_height = 520
    table_height = min(max_height, header_height + row_height * len(display_rows))

    event = st.dataframe(
        display_rows,
        use_container_width=True,
        height=table_height,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    selected_rows: List[int] = []
    if hasattr(event, "selection"):
        selected_rows = list(getattr(event.selection, "rows", []))
    elif isinstance(event, dict):
        selected_rows = list(event.get("selection", {}).get("rows", []))

    if selected_rows:
        row_idx = selected_rows[0]
        data = incoming_lookup.get(row_idx)
        if data is not None:
            _render_incoming_dialog(f"Incoming Data (Row {row_idx + 1})", data)


@st.cache_data(ttl=15, show_spinner=False)
def _fetch_tracking(document_id: str) -> Dict[str, Any]:
    client = N8NClient()
    return client.edi_document_tracking(document_id)


def render() -> None:
    st.caption("Enter a Document ID to fetch AI summary + Boomi & MFT SQL data via n8n.")

    with st.form("edi-tracking-form", clear_on_submit=False):
        doc_id = st.text_input(
            "Document ID",
            value=st.session_state.get("edi_tracking_doc_id", ""),
            placeholder="e.g. DOC-000185",
            help="Enter the Document ID and click Submit.",
        )
        submitted = st.form_submit_button("Submit", use_container_width=True)

    if submitted:
        if not doc_id.strip():
            st.error("Please enter a Document ID before submitting.")
        else:
            st.session_state["edi_tracking_doc_id"] = doc_id.strip()
            with st.spinner("Calling n8n workflow..."):
                try:
                    st.session_state["edi_tracking_response"] = _fetch_tracking(doc_id.strip())
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Failed to fetch tracking data: {exc}")
                    return

    response = st.session_state.get("edi_tracking_response")
    if not response:
        st.info("Submit a Document ID to view results.")
        return

    response_data = _maybe_parse_json(response)
    merged = _merge_data_list(response_data)
    unwrapped = _unwrap_payload(response_data) or {}
    output = merged.get("output") or unwrapped.get("output") or _extract_key(response_data, "output")
    actual = merged.get("boomi") or unwrapped.get("boomi") or _extract_key(response_data, "boomi")
    mft = merged.get("mft") or unwrapped.get("mft") or _extract_key(response_data, "mft")

    st.subheader("Summary")
    if isinstance(output, str) and output.strip():
        st.write(output.strip())
    elif output is not None:
        st.json(output)
    else:
        st.write("NA")

    st.subheader("Boomi (SQL data)")
    rows = _normalize_actual(actual)
    _render_actual_table(rows)

    st.subheader("MFT (SQL data)")
    mft_rows = _normalize_actual(mft)
    _render_actual_table(mft_rows)

    with st.expander("Raw response (n8n)", expanded=False):
        st.json(response)
