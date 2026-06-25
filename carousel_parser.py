"""
인스타그램 캐러셀 초안(.txt) 파서

헤르메스 'content-carousel' 산출물을 카드별 구조로 변환하고,
1080x1350 미리보기 HTML과 인스타 캡션 초안을 생성한다.

두 가지 헤더 형식을 모두 지원한다:
    형식 A:  [표지 / Card 1]      (카드마다 ---- 구분선)
    형식 B:  ---[표지]---,  ---[카드 2 — 상황 설정]---,  ---[CTA]---

본문에 섞인 검수용 메모(〔전문가 보강…〕, [검증: …])는 카드 표시에서 자동 제거한다.

사용:
    from carousel_parser import parse_carousel, build_caption, cards_preview_html
"""

from __future__ import annotations

import html
import re
from typing import Any


# ---------------------------------------------------------------------------
# 헤더/구분선 인식
# ---------------------------------------------------------------------------

# 순수 구분선: ---- 또는 ==== (내용 없이 기호만)
_PURE_DELIM_RE = re.compile(r"^[\-=]{3,}$")
# 디자인/검수 메모 헤더 (괄호 유무·꼬리표 무관: '[검수 메모 — G2/G3]' 도 인식)
_DESIGN_HDR_RE = re.compile(r"^\[?\s*디자인\s*메모\b.*$")
_REVIEW_HDR_RE = re.compile(r"^\[?\s*검수\s*메모\b.*$")
# 대시로 감싼 헤더:  ---[ ... ]---  (대시가 있으면 무조건 카드 헤더로 인정)
_HDR_DASHED_RE = re.compile(r"^-{2,}\[(?P<inner>.+?)\]-{2,}$")
# 대괄호 헤더:  [ ... ]
_HDR_BRACKET_RE = re.compile(r"^\[(?P<inner>.+?)\]$")

# 카드 역할을 가리키는 키워드 (대괄호 헤더 판정용 — 본문 속 [검증:…] 와 구분)
_CARD_KEYWORDS = ("표지", "커버", "cover", "본문", "내용", "마무리", "엔딩",
                  "클로징", "마지막", "cta", "카드", "card", "장면")
# 주석성 대괄호(헤더 아님) 접두어 — 느슨 모드에서 제외
_ANNOT_PREFIX = ("검증", "검색", "근거", "참고", "메모", "이미지", "자막", "note")

# 본문에서 제거할 검수용 메모
_ANNOTATION_RES = [
    re.compile(r"〔[^〕]*〕", re.DOTALL),
    re.compile(r"\[검증[^\]]*\]"),
    re.compile(r"\[검색[^\]]*\]"),
    re.compile(r"\[전문가\s*보강[^\]]*\]"),
]


def _looks_like_card_label(inner: str, loose: bool) -> bool:
    """대괄호 안쪽이 카드 헤더로 볼 만한지 판정.

    엄격 모드: 카드 역할 키워드를 포함해야 함.
    느슨 모드(폴백): 주석성 접두어(검증/메모/…)만 아니면 카드로 본다.
    """
    low = inner.lower().strip()
    if loose:
        return not any(low.startswith(p.lower()) for p in _ANNOT_PREFIX)
    return any(k in low for k in _CARD_KEYWORDS)


def _match_header(s: str, loose: bool = False) -> str | None:
    """카드 헤더면 안쪽 라벨 문자열을, 아니면 None을 반환."""
    m = _HDR_DASHED_RE.match(s)
    if m:
        return m.group("inner").strip()
    m = _HDR_BRACKET_RE.match(s)
    if m and _looks_like_card_label(m.group("inner"), loose):
        return m.group("inner").strip()
    return None


def _label_from_inner(inner: str) -> str:
    """헤더 안쪽 문자열에서 표시용 라벨 추출(카드 번호 토큰 제거).

    '표지 / Card 1' → '표지',  '본문 카드 2' → '본문',  '표지 — 카드 1' → '표지',
    '카드 2 — 상황 설정' → '상황 설정',  'CTA 카드 11' → 'CTA',  'CTA' → 'CTA'
    """
    s = inner.strip()
    # 'B형': 번호가 앞에 오고 뒤에 설명 → 설명을 라벨로
    m = re.match(r"^카드\s*\d+\s*[—\-–]\s*(.+)$", s)
    if m:
        return m.group(1).strip()
    # 끝/앞에 붙은 '카드 N' / 'Card N' 토큰과 주변 구분자 제거
    s = re.sub(r"\s*[—\-–/]?\s*(?:카드|Card)\s*\d+\s*$", "", s, flags=re.I)
    s = re.sub(r"^(?:카드|Card)\s*\d+\s*[—\-–/]?\s*", "", s, flags=re.I)
    return s.strip(" —-–/") or inner.strip()


def _clean_card_text(text: str) -> str:
    """카드 본문에서 검수용 메모를 제거하고 과도한 빈 줄을 정리."""
    for r in _ANNOTATION_RES:
        text = r.sub("", text)
    text = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", text)
    return text.strip("\n")


# ---------------------------------------------------------------------------
# 파싱
# ---------------------------------------------------------------------------

def _parse(text: str, loose: bool) -> dict[str, Any]:
    """헤더 구동 1패스 파싱. loose=True면 미지 형식까지 최대한 카드로 인식."""
    result: dict[str, Any] = {
        "title": "", "meta": {}, "cards": [],
        "design_notes": "", "review_notes": "",
    }
    meta = result["meta"]

    cards: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    design_lines: list[str] = []
    review_lines: list[str] = []
    section = "head"  # head → cards → design → review

    for raw in text.splitlines():
        line = raw.rstrip()
        s = line.strip()

        # 메모 섹션 헤더 전환
        if _DESIGN_HDR_RE.match(s):
            if cur:
                cards.append(cur)
                cur = None
            section = "design"
            continue
        if _REVIEW_HDR_RE.match(s):
            if cur:
                cards.append(cur)
                cur = None
            section = "review"
            continue

        if section == "design":
            design_lines.append(line)
            continue
        if section == "review":
            review_lines.append(line)
            continue

        # 순수 구분선은 건너뜀
        if _PURE_DELIM_RE.match(s):
            continue

        # 카드 헤더?
        inner = _match_header(s, loose=loose)
        if inner is not None:
            if cur:
                cards.append(cur)
            cur = {"label": _label_from_inner(inner), "lines": []}
            section = "cards"
            continue

        if section == "head":
            if s.startswith("==") and s.endswith("=="):
                result["title"] = s.strip("=").strip()
            elif ":" in s:
                for part in s.split("|"):
                    if ":" in part:
                        k, v = part.split(":", 1)
                        if k.strip():
                            meta[k.strip()] = v.strip()
            continue

        # 카드 본문
        if cur is not None:
            cur["lines"].append(line)

    if cur:
        cards.append(cur)

    # 번호 부여 + 본문 정리
    for i, c in enumerate(cards):
        c["num"] = i + 1
        c["text"] = _clean_card_text("\n".join(c["lines"]).strip("\n"))
        c["lines"] = c["text"].splitlines()
    result["cards"] = cards

    result["design_notes"] = "\n".join(design_lines).strip()
    result["review_notes"] = "\n".join(review_lines).strip()
    return result


def parse_carousel(text: str) -> dict[str, Any]:
    """캐러셀 초안 텍스트를 구조화 딕셔너리로 변환한다.

    먼저 엄격 모드로 파싱하고, 카드를 하나도 못 찾으면
    느슨 모드(미지 형식 폴백)로 자동 재시도한다.

    반환:
        title         : str
        meta          : dict (스킬/모드/포맷/톤/제목 유형/주제 ...)
        cards         : [{"num","label","text","lines"}, ...]  (등장 순서)
        design_notes  : str
        review_notes  : str
    """
    result = _parse(text, loose=False)
    if not result["cards"]:
        fallback = _parse(text, loose=True)
        if fallback["cards"]:
            return fallback
    return result


def parse_carousel_file(path: str, encoding: str = "utf-8") -> dict[str, Any]:
    with open(path, "r", encoding=encoding) as f:
        return parse_carousel(f.read())


# ---------------------------------------------------------------------------
# 인스타 캡션 초안 생성
# ---------------------------------------------------------------------------

_PARTICLES = ("에게", "에서", "으로", "에는", "이라는", "은", "는", "이", "가",
              "을", "를", "의", "에", "과", "와", "도", "로")


def _suggest_hashtags(meta: dict[str, str]) -> str:
    """주제에서 키워드를 뽑아 해시태그 초안을 만든다(예시 — 사용자가 다듬는 용도)."""
    words: list[str] = []
    for w in meta.get("주제", "").split():
        for p in _PARTICLES:
            if w.endswith(p) and len(w) > len(p) + 1:
                w = w[: -len(p)]
                break
        w = w.strip(" →·,.")
        if len(w) >= 2 and re.search(r"[가-힣A-Za-z]", w):
            words.append(w)

    seen = set()
    tags = []
    for w in words + ["육아", "공감", "소통"]:
        if w not in seen:
            seen.add(w)
            tags.append(w)
    return " ".join("#" + t for t in tags)


def build_caption(parsed: dict[str, Any]) -> str:
    """카드 내용으로 인스타 캡션 초안을 조립한다(편집 전제).

    구성: 표지 후킹 → 중간 카드 첫 줄 요약 → 마무리 → CTA → 해시태그
    """
    cards = parsed["cards"]
    if not cards:
        return ""

    cover = cards[0]
    closing = next((c for c in reversed(cards) if "마무리" in c["label"]), None)
    cta = next((c for c in reversed(cards) if "CTA" in c["label"].upper()), None)

    skip = {id(cover)}
    if closing:
        skip.add(id(closing))
    if cta:
        skip.add(id(cta))
    middle = [c for c in cards if id(c) not in skip]
    lead = [c["text"].splitlines()[0].strip() for c in middle if c["text"].strip()]

    parts: list[str] = [cover["text"].strip()]
    if lead:
        parts += ["", "\n".join(lead)]
    if closing:
        parts += ["", closing["text"].strip()]
    if cta:
        parts += ["", cta["text"].strip()]
    tags = _suggest_hashtags(parsed["meta"])
    if tags:
        parts += ["", tags]
    return "\n".join(parts).strip()


# ---------------------------------------------------------------------------
# 1080x1350 카드 미리보기 HTML
# ---------------------------------------------------------------------------

# 역할별 배경/글자색 (미리보기용 — 최종 색은 Canva에서)
_ROLE_STYLE = {
    "표지": ("linear-gradient(135deg,#3a2d6d,#5b3da8)", "#ffffff"),
    "마무리": ("linear-gradient(135deg,#6d3d8a,#a85b9a)", "#ffffff"),
    "CTA": ("linear-gradient(135deg,#1f6f8b,#2fa8a8)", "#ffffff"),
}
_DEFAULT_STYLE = ("linear-gradient(135deg,#f6f7ff,#e9ecff)", "#1f2340")


def _role_style(label: str):
    """라벨로 역할별 색을 고른다(부분 일치 — '마무리 착지'도 마무리로)."""
    if "표지" in label:
        return _ROLE_STYLE["표지"]
    if "CTA" in label.upper():
        return _ROLE_STYLE["CTA"]
    if "마무리" in label:
        return _ROLE_STYLE["마무리"]
    return _DEFAULT_STYLE


def cards_preview_html(cards: list[dict[str, Any]], font_size: int = 15,
                       columns: int = 4) -> str:
    """카드들을 1080:1350(4:5) 비율 고정으로 화면에 그리드 나열한 HTML을 만든다.

    카드 너비는 그리드 칸에 맞춰 자동(반응형), 비율은 4:5 고정.
    글자 크기(font_size)만 조절한다. 기본 4열.
    """
    items = []
    for c in cards:
        bg, fg = _role_style(c["label"])
        # 빈 줄로 나뉜 문단 단위로 렌더 — 문단 내 줄바꿈은 <br>,
        # 문단 사이는 gap(약 1줄 느낌)으로 제어해 여백이 과하지 않게.
        paras = [p for p in re.split(r"\n\s*\n", c["text"].strip()) if p.strip()]
        body = (
            '<div style="display:flex;flex-direction:column;gap:0.7em;">'
            + "".join("<div>" + html.escape(p).replace("\n", "<br>") + "</div>"
                      for p in paras)
            + "</div>"
        ) if paras else ""
        items.append(
            f'<div style="aspect-ratio:1080/1350;background:{bg};color:{fg};'
            f'border-radius:14px;padding:8% 7%;box-sizing:border-box;display:flex;'
            f'flex-direction:column;justify-content:center;align-items:center;'
            f'text-align:center;font-size:{font_size}px;line-height:1.4;'
            f'position:relative;box-shadow:0 2px 10px rgba(0,0,0,.15);overflow:hidden;">'
            f'<div style="position:absolute;top:8px;left:11px;font-size:10px;'
            f'opacity:.65;font-weight:600;">#{c["num"]} {html.escape(c["label"])}</div>'
            f'<div>{body}</div></div>'
        )
    grid = "".join(items)
    return (
        f'<div style="display:grid;grid-template-columns:repeat({columns},1fr);'
        f'gap:16px;padding:8px 0 18px;">' + grid + "</div>"
    )


# ---------------------------------------------------------------------------
# 셀프 테스트
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    path = sys.argv[1] if len(sys.argv) > 1 else "carousel.txt"
    d = parse_carousel_file(path)
    print("제목:", d["title"])
    print("메타:", d["meta"])
    print(f"\n카드 {len(d['cards'])}장:")
    for c in d["cards"]:
        head = c["text"].splitlines()[0] if c["text"].splitlines() else ""
        print(f"  #{c['num']} [{c['label']}] {head}")
    print("\n--- 캡션 초안 ---")
    print(build_caption(d))
    print(f"\n디자인 메모 {len(d['design_notes'])}자 / 검수 메모 {len(d['review_notes'])}자")
