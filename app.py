"""
콘텐츠 작업 보조 — 라우터(멀티페이지 진입점)

블로그 작업 보조 / 인스타 캐러셀 작업 보조 두 도구를
한 링크에서 사이드바 메뉴로 전환한다.

실행:  streamlit run app.py
"""

import streamlit as st

# 페이지 설정은 라우터에서 한 번만 호출 (각 페이지 파일은 호출하지 않음)
st.set_page_config(page_title="콘텐츠 작업 보조", page_icon="🧰", layout="wide")

blog = st.Page("blog_page.py", title="블로그 작업 보조", icon="📝", default=True)
carousel = st.Page("carousel_page.py", title="인스타 캐러셀 작업 보조", icon="🎠")

pg = st.navigation([blog, carousel])
pg.run()
