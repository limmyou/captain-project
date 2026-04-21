from pathlib import Path
import re
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Code Of Nature — 복원 예측 시뮬레이션",
    layout="wide",
    initial_sidebar_state="collapsed",
)

BASE_DIR = Path(__file__).parent

HTML_PATH = BASE_DIR / "templates" / "index.html"
CSS_PATH = BASE_DIR / "static" / "css" / "style.css"
JS_PATH = BASE_DIR / "static" / "js" / "script.js"

if not HTML_PATH.exists():
    st.error(f"HTML not found: {HTML_PATH}")
    st.stop()

if not CSS_PATH.exists():
    st.error(f"CSS not found: {CSS_PATH}")
    st.stop()

if not JS_PATH.exists():
    st.error(f"JS not found: {JS_PATH}")
    st.stop()

html = HTML_PATH.read_text(encoding="utf-8")
css = CSS_PATH.read_text(encoding="utf-8")
js = JS_PATH.read_text(encoding="utf-8")

html = re.sub(
    r'<link rel="stylesheet" href="/static/css/style\.css">\s*',
    "",
    html,
    flags=re.IGNORECASE,
)

match = re.search(r"<body[^>]*>(.*)</body>", html, flags=re.IGNORECASE | re.DOTALL)
body_content = match.group(1) if match else html

full_html = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Code Of Nature — 복원 예측 시뮬레이션</title>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=Syne:wght@700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      width: 100%;
      background: #f4f6f3;
    }}
    {css}
  </style>
</head>
<body>
  {body_content}
  <script>
    {js}
  </script>
</body>
</html>
"""

st.markdown(
    """
    <style>
      .block-container {
        padding: 0;
        max-width: 100%;
      }
      header[data-testid="stHeader"] {
        display: none;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

components.html(full_html, height=3500, scrolling=True)