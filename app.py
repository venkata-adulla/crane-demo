from __future__ import annotations

import streamlit as st

from ui.edi_tracking import render as render_edi_tracking


def main() -> None:
    st.set_page_config(page_title="EDI Document Tracking", layout="wide")
    st.title("EDI Document Tracking")
    render_edi_tracking()


if __name__ == "__main__":
    main()
