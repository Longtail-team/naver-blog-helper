"""
인스타그램 캐러셀 초안(.txt) 파서

헤르메스 'content-carousel' 산출물을 카드별 구조로 변환하고,
1080x1350 미리보기 HTML과 인스타 캡션 초안을 생성한다.

파일 구조:
    == 제목 ==
    스킬: ... | 모드: ... | 포맷: ... | 톤: ...
    제목 유형: ... | 주제: ...
    --------------------------------------------------
    [표지 / Card 1]
    (카드 텍스트)
    --------------------------------------------------
    [본문 / Card 2]
    ...
    --------------------------------------------------
    [디자인 메모] ... [검수 메모] ...

사용:
    from carousel_parser import parse_carousel, build_caption, cards_preview_html
"""

from __future__ import annotations

import html
import re
from typing import Any

# 카드/블록 구분선 (--- 3개 이상)
_SEP_RE = re.compile(r"^-{3,}\s*$", re.MULTILINE)
# 카드 헤더: [표지 / Card 1] , [본문 / Card 2] 등
_CARD_HDR_RE = re.compile(r"^\[(?P<label>[^/\]]+?)\s*/\s*Card\s*(?P<num>\d+)\s*\]\s*$")


# ---------------------------------------------------------------------------
# 파싱
# ---------------------------------------------------------------------------

def _parse_header(block: str, result: dict[str, Any]) -> None:
    """제목(== ... ==)과 메타(key: value | key: value)를 추출."""
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("==") and line.endswith("=="):
            result["title"] = line.strip("=").strip()
        elif ":" in line:
            for part in line.split("|"):
                if ":" in part:
                    k, v = part.split(":", 1)
                    if k.strip():
                        result["meta"][k.strip()] = v.strip()


def _parse_notes(chunk: str, result: dict[str, Any]) -> None:
    """[디자인 메모] / [검수 메모] 블록을 텍스트로 보관."""
    if "[검수 메모]" in chunk:
        idx = chunk.index("[검수 메모]")
        design_part, review_part = chunk[:idx], chunk[idx:]
    else:
        design_part, review_part = chunk, ""
    if "[디자인 메모]" in design_part:
        result["design_notes"] = design_part.replace("[디자인 메모]", "").strip()
    if review_part:
        result["review_notes"] = review_part.replace("[검수 메모]", "").strip()


def parse_carousel(text: str) -> dict[str, Any]:
    """캐러셀 초안 텍스트를 구조화 딕셔너리로 변환한다.

    반환:
        title         : str
        meta          : dict (스킬/모드/포맷/톤/제목 유형/주제 ...)
        cards         : [{"num","label","text","lines"}, ...]  (num 오름차순)
        design_notes  : str
        review_notes  : str
    """
    result: dict[str, Any] = {
        "title": "", "meta": {}, "cards": [],
        "design_notes": "", "review_notes": "",
    }

    chunks = [c.strip("\n") for c in _SEP_RE.split(text)]
    if not chunks:
        return result

    _parse_header(chunks[0], result)

    for chunk in chunks[1:]:
        if not chunk.strip():
            continue
        lines = chunk.strip("\n").splitlines()
        first = lines[0].strip() if lines else ""
        m = _CARD_HDR_RE.match(first)
        if m:
            body = "\n".join(lines[1:]).strip("\n")
            result["cards"].append({
                "num": int(m.group("num")),
                "label": m.group("label").strip(),
                "text": body,
                "lines": body.splitlines(),
            })
        elif "[디자인 메모]" in chunk or "[검수 메모]" in chunk:
            _parse_notes(chunk, result)

    result["cards"].sort(key=lambda c: c["num"])
    return result


def parse_carousel_file(path: str, encoding: str = "utf-8") -> dict[str, Any]:
    with open(path, "r", encoding=encoding) as f:
        return parse_carousel(f.read())


# ---------------------------------------------------------------------------
# 인스타 캡션 초안 생성
# ---------------------------------------------------------------------------

# 해시태그 추출 시 떼어낼 흔한 조사
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
        w = w.strip()
        if len(w) >= 2:
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

    구성: 표지 후킹 → 단계 요약 → 마무리 한마디 → CTA → 해시태그
    """
    cards = parsed["cards"]
    if not cards:
        return ""

    def find(label: str):
        return next((c for c in cards if c["label"] == label), None)

    cover = cards[0]
    closing = find("마무리")
    cta = next((c for c in reversed(cards) if c["label"].upper() == "CTA"), None)
    body_cards = [c for c in cards if c["label"] == "본문"]
    steps = [c["text"].splitlines()[0].strip() for c in body_cards if c["text"].strip()]

    parts: list[str] = [cover["text"].strip()]
    if steps:
        parts += ["", "\n".join(steps)]
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


def cards_preview_html(cards: list[dict[str, Any]], font_size: int = 15,
                       columns: int = 4) -> str:
    """카드들을 1080:1350(4:5) 비율 고정으로 화면에 그리드 나열한 HTML을 만든다.

    카드 너비는 그리드 칸에 맞춰 자동(반응형), 비율은 4:5 고정.
    글자 크기(font_size)만 조절한다. 기본 3열.
    """
    items = []
    for c in cards:
        bg, fg = _ROLE_STYLE.get(c["label"], _DEFAULT_STYLE)
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
