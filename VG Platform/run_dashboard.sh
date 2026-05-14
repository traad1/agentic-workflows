#!/bin/bash
cd "$(dirname "$0")"
python3 -m streamlit run dashboard/app.py --server.port 8501
