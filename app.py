"""
네이버 블로그 작업 보조 — Streamlit 웹앱

헤르메스 초안(.txt)을 업로드하면 제목/본문/태그/이미지 텍스트를
한 화면에서 확인하고 복사할 수 있다.

실행:
    streamlit run app.py

복사 버튼: Streamlit의 st.code() 우측 상단에 기본 복사 아이콘이 달린다.
별도 설치·자바스크립트 없이 동작하므로 가장 안정적이다.
"""

from __future__ import annotations

import streamlit as st

from parser import format_for_blog, grid_to_dataframe, parse_draft


# ---------------------------------------------------------------------------
# 페이지 기본 설정
# ---------------------------------------------------------------------------
st.set_page_config(page_title="네이버 블로그 작업 보조", page_icon="📝", layout="wide")

st.title("📝 네이버 블로그 작업 보조")
st.caption("헤르메스 초안(.txt)을 올리면 제목·본문·태그·이미지 텍스트를 정리해 드려요. "
           "각 박스 우측 상단의 📋 아이콘으로 복사하세요.")

# 복사 박스(st.code)가 긴 줄을 가로 스크롤 대신 박스 너비에 맞춰 줄바꿈하도록.
# 화면 표시만 접히고, 📋로 복사되는 텍스트의 실제 줄바꿈은 그대로 유지됨.
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


# ---------------------------------------------------------------------------
# 사용법 패널 (사이드바 — 항상 표시)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("📖 사용법")
    st.markdown(
        """
**설치 필요 없어요. 이 페이지에서 다 됩니다.**

1. 헤르메스 **초안 txt**를 오른쪽 업로드 칸에 올리기
2. **제목** 후보 중 하나 고르고 📋 복사 → 네이버 제목칸
3. **본문** 📋 복사 → 네이버에 붙여넣기
   - `@@소제목 강조` 붙은 줄 = 소제목 → 네이버에서 **글자 크기 키우기**
   - 키운 뒤 `@@소제목 강조` 글자는 **삭제** (Ctrl+F로 `@@` 검색)
4. **태그** 📋 전체 복사 → 태그칸
5. **이미지 텍스트 패키지**로 Canva에서 썸네일·카드 제작
   - 본문 속 `[이미지 삽입: …]` 자리에 이미지 넣기
6. 발행 ✅

---
💡 글자 크기·색은 복사로 안 옮겨가요 → 네이버에서 직접 지정
💡 한동안 안 쓰면 앱이 잠들어요 → 처음 열 때 30초쯤은 정상
        """
    )


# ---------------------------------------------------------------------------
# 파일 업로드 & 파싱
# ---------------------------------------------------------------------------
def read_upload(uploaded) -> str:
    """업로드된 파일을 텍스트로 디코딩. utf-8 우선, 실패 시 cp949(한글 윈도우) 시도."""
    raw = uploaded.getvalue()
    for enc in ("utf-8", "utf-8-sig", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    # 마지막 보루: 깨진 글자는 대체 문자로
    return raw.decode("utf-8", errors="replace")


uploaded = st.file_uploader("초안 txt 파일 업로드", type=["txt"])

if uploaded is None:
    st.info("좌측 상단에서 헤르메스 초안 .txt 파일을 올려 주세요.")
    st.stop()

text = read_upload(uploaded)

try:
    data = parse_draft(text)
except Exception as e:  # 파싱 실패해도 앱이 죽지 않게 안내
    st.error(f"파일을 해석하는 중 문제가 생겼어요: {e}")
    st.stop()

# 섹션을 하나도 못 찾았으면 형식 안내
if not data["sections"]:
    st.warning("구분자(====)로 나뉜 섹션을 찾지 못했어요. 헤르메스 초안 형식이 맞는지 확인해 주세요.")
    with st.expander("업로드한 파일 원문 보기"):
        st.text(text)
    st.stop()

st.success(f"파싱 완료 — 인식된 섹션: {', '.join(data['sections'].keys())}")
st.divider()


# ---------------------------------------------------------------------------
# 1) 제목 후보 선택
# ---------------------------------------------------------------------------
st.header("1. 제목 선택")

titles = data["titles"]
if titles:
    chosen = st.radio("후보 중 하나를 고르세요", titles, index=0)
    st.markdown("**선택한 제목 미리보기**")
    # 시각적으로 제목답게 크게 (앱 안에서만 보이는 미리보기)
    st.markdown(
        f"<div style='font-size:1.8rem; font-weight:700; line-height:1.3; "
        f"padding:0.4rem 0;'>{chosen}</div>",
        unsafe_allow_html=True,
    )
    st.caption("아래 박스의 📋 로 제목을 복사하세요. (글자 크기는 네이버에서 직접 지정 — 복사로는 안 옮겨갑니다)")
    st.code(chosen, language=None)
else:
    st.warning("제목 후보를 찾지 못했어요.")

st.divider()


# ---------------------------------------------------------------------------
# 2) 본문
# ---------------------------------------------------------------------------
st.header("2. 본문")

body = data["body"]
if body["clean"]:
    c1, c2 = st.columns([1, 1])
    with c1:
        blog_format = st.toggle("블로그용 줄바꿈 정리", value=True,
                                help="마침표 뒤 줄바꿈 + 긴 문장은 쉼표에서 줄바꿈해 읽기 쉽게 만듭니다.")
    with c2:
        show_raw = st.toggle("내부 메모까지 보기", value=False,
                             help="자막 근거·전문가 보강 메모를 함께 봅니다. 평소엔 끄세요.")

    # 메모 토글: 보여줄 원본만 선택(메모 포함/제외). 줄바꿈 토글과 독립적으로 동작.
    base_text = body["raw"] if show_raw else body["clean"]

    headings = []
    if blog_format:
        # 줄바꿈이 켜져 있으면 메모 보기와 무관하게 슬라이더·소제목 표시 항상 노출
        sc1, sc2 = st.columns([2, 1])
        with sc1:
            max_len = st.slider("한 줄 최대 길이(글자 수) — 짧을수록 줄바꿈이 잦아져요", 20, 50, 30)
        with sc2:
            mark_heading = st.toggle("본문에 소제목 표시", value=True,
                                     help="소제목 줄 끝에 '@@소제목 강조'를 붙여 네이버에서 바로 찾게 합니다. "
                                          "최종 복사 전엔 꺼서 깔끔하게 가져가세요.")
        result = format_for_blog(
            base_text, max_len=max_len,
            heading_mark="@@소제목 강조" if mark_heading else None,
        )
        body_text = result["text"]
        headings = result["headings"]
    else:
        body_text = base_text

    st.caption(f"글자 수: {len(body_text):,}자 · 박스 우측 상단 📋 로 본문 전체를 복사하세요.")
    if headings and "@@" in body_text:
        st.info("⚠️ 본문 속 **@@소제목 강조** 표시는 안내용이에요. 네이버에서 그 줄 크기를 키운 뒤 "
                "**표시는 지워주세요**(Ctrl+F로 `@@` 검색하면 빨라요). "
                "최종 복사 땐 위 '본문에 소제목 표시'를 꺼도 됩니다.")
    st.code(body_text, language=None)

    # 소제목 빠른 참고 목록(접힘) — 본문 표시가 주, 이건 보조
    if headings:
        with st.expander(f"🔠 소제목 {len(headings)}개 목록 (참고용)", expanded=False):
            for h in headings:
                st.markdown(f"- {h}")

    if body["image_markers"]:
        with st.expander(f"🖼️ 본문 속 이미지 삽입 위치 {len(body['image_markers'])}곳"):
            for i, mk in enumerate(body["image_markers"], 1):
                st.markdown(f"**{i}.** {mk}")
else:
    st.warning("본문을 찾지 못했어요.")

st.divider()


# ---------------------------------------------------------------------------
# 3) 태그
# ---------------------------------------------------------------------------
st.header("3. 태그")

tags = data["tags"]
if tags:
    st.caption(f"태그 {len(tags)}개 · 박스의 📋 로 전체 복사 → 네이버 태그칸에 붙여넣기")
    # 네이버 태그 입력은 쉼표 구분을 인식하므로 쉼표로 이어 복사
    st.code(", ".join(tags), language=None)
    st.markdown(" ".join(f"`#{t}`" for t in tags))
else:
    st.warning("태그를 찾지 못했어요.")

st.divider()


# ---------------------------------------------------------------------------
# 4) 이미지 텍스트 패키지 (Canva 작업 참고용)
# ---------------------------------------------------------------------------
st.header("4. 이미지 텍스트 패키지")
st.caption("Canva에서 이미지를 만들 때 참고할 텍스트입니다. 각 박스의 📋 로 복사하세요.")

pkg = data["image_package"]

# 썸네일
thumb = pkg["thumbnail"]
if thumb["main"] or thumb["sub"]:
    st.subheader("🎯 썸네일")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**메인 문구 후보**")
        for i, m in enumerate(thumb["main"], 1):
            st.markdown(f"{i}. {m}")
            st.code(m, language=None)
    with c2:
        st.markdown("**보조 부제 후보**")
        for i, s in enumerate(thumb["sub"], 1):
            st.markdown(f"{i}. {s}")
            st.code(s, language=None)

# 카드들
for card in pkg["cards"]:
    st.subheader(f"🃏 {card['header']}")
    if card["title"]:
        st.markdown(f"**카드 제목:** {card['title']}")

    if card["grid"]:
        df = grid_to_dataframe(card["grid"])
        if df is not None:
            st.table(df)
        else:
            st.text("\n".join("\t".join(r) for r in card["grid"]))
    elif card["lines"]:
        for line in card["lines"]:
            st.markdown(f"- {line}")

    if card["note"]:
        st.caption(f"한 줄 설명: {card['note']}")
    if card["footer"]:
        st.caption(f"하단: {card['footer']}")

    # 카드 전체 텍스트 한 번에 복사 (제목 + 내용 + 설명)
    parts = []
    if card["title"]:
        parts.append(card["title"])
    if card["grid"]:
        parts.extend("  ".join(r) for r in card["grid"])
    else:
        parts.extend(card["lines"])
    if card["note"]:
        parts.append(card["note"])
    if card["footer"]:
        parts.append(card["footer"])
    with st.expander("이 카드 텍스트 통째로 복사"):
        st.code("\n".join(parts), language=None)

    st.markdown("")  # 카드 사이 여백


# ---------------------------------------------------------------------------
# 5) 교차대조표 (검수 참고)
# ---------------------------------------------------------------------------
if data["crosscheck"]:
    st.divider()
    with st.expander("🔍 G2 자막 교차대조표 (검수 참고용)"):
        st.text(data["crosscheck"])
