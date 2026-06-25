"""
인스타그램 캐러셀 작업 보조 — Streamlit 웹앱

헤르메스 캐러셀 초안(.txt)을 올리면:
  · 카드를 1080x1350(4:5) 비율로 미리보기
  · 카드별 텍스트 복사 (Canva 작업용)
  · 인스타 캡션 초안 생성(편집 가능)

실행:  streamlit run carousel_app.py
"""

from __future__ import annotations

import streamlit as st

from carousel_parser import (
    build_caption,
    cards_preview_html,
    parse_carousel,
)

# 페이지 설정(set_page_config)은 라우터 app.py에서 한 번만 호출한다.

st.title("🎠 인스타그램 캐러셀 작업 보조")
st.caption("헤르메스 캐러셀 초안(.txt)을 올리면 카드 미리보기 · 카드별 텍스트 · 캡션 초안을 만들어 드려요. "
           "최종 카드 디자인은 Canva에서(1080×1350).")

# 복사 박스(st.code) 긴 줄 줄바꿈
st.markdown(
    """
    <style>
    [data-testid="stCode"] pre, [data-testid="stCode"] code,
    .stCode pre, .stCode code {
        white-space: pre-wrap !important;
        word-break: break-word !important;
        overflow-wrap: anywhere !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("📖 사용법")
    st.markdown(
        """
**설치 필요 없어요. 이 페이지에서 다 됩니다.**

1. 헤르메스 **캐러셀 초안 txt**를 오른쪽에 업로드
2. **카드 미리보기**로 장수·줄바꿈·흐름 확인
3. **카드별 텍스트**를 📋 복사 → Canva 카드(1080×1350)에 얹기
4. **캡션 초안**을 다듬어 📋 복사 → 인스타 게시글에 붙여넣기
5. 발행 ✅

---
💡 카드 디자인 색·폰트는 Canva에서 (이 미리보기는 배치 확인용)
💡 해시태그는 예시예요 → 주제에 맞게 다듬어 쓰세요
        """
    )


def read_upload(uploaded) -> str:
    raw = uploaded.getvalue()
    for enc in ("utf-8", "utf-8-sig", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


uploaded = st.file_uploader("캐러셀 초안 txt 파일 업로드", type=["txt"])

if uploaded is None:
    st.info("헤르메스 캐러셀 초안 .txt 파일을 올려 주세요.")
    st.stop()

try:
    data = parse_carousel(read_upload(uploaded))
except Exception as e:
    st.error(f"파일을 해석하는 중 문제가 생겼어요: {e}")
    st.stop()

if not data["cards"]:
    st.warning("카드를 찾지 못했어요. '[표지 / Card 1]' 같은 카드 형식이 맞는지 확인해 주세요.")
    st.stop()

# 메타 요약
meta = data["meta"]
if data["title"]:
    st.success(f"**{data['title']}** — 카드 {len(data['cards'])}장")
if meta:
    chips = " · ".join(f"{k}: {v}" for k, v in meta.items())
    st.caption(chips)

st.divider()

# ---------------------------------------------------------------------------
# 1) 카드 미리보기 (1080x1350)
# ---------------------------------------------------------------------------
st.header("1. 카드 미리보기 (1080×1350)")
size = st.slider("미리보기 카드 너비(px) — 화면에 맞게 조절", 160, 340, 230)
st.caption("← → 가로로 스크롤하면 캐러셀처럼 넘겨볼 수 있어요. (색·폰트는 Canva에서 입힙니다)")
st.markdown(cards_preview_html(data["cards"], card_w=size), unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------------------
# 2) 카드별 텍스트 (Canva 작업용)
# ---------------------------------------------------------------------------
st.header("2. 카드별 텍스트")
st.caption("각 박스 우측 상단 📋 로 복사해서 Canva 카드에 붙여넣으세요.")
cols = st.columns(2)
for i, c in enumerate(data["cards"]):
    with cols[i % 2]:
        st.markdown(f"**#{c['num']} · {c['label']}**")
        st.code(c["text"], language=None)

st.divider()

# ---------------------------------------------------------------------------
# 3) 인스타 캡션 초안
# ---------------------------------------------------------------------------
st.header("3. 인스타 캡션 초안")
st.caption("카드 내용으로 만든 초안이에요. 자유롭게 고친 뒤 아래 박스 📋 로 복사하세요.")
default_caption = build_caption(data)
edited = st.text_area("캡션 (수정 가능)", default_caption, height=320)
st.markdown("**복사용 (📋)**")
st.code(edited, language=None)

# ---------------------------------------------------------------------------
# 4) 메모 (참고용)
# ---------------------------------------------------------------------------
if data["design_notes"] or data["review_notes"]:
    st.divider()
    if data["design_notes"]:
        with st.expander("🎨 디자인 메모"):
            st.text(data["design_notes"])
    if data["review_notes"]:
        with st.expander("✅ 검수 메모"):
            st.text(data["review_notes"])
