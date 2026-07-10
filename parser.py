"""
네이버 블로그 자동화 — 헤르메스 초안(.txt) 파서

헤르메스 에이전트가 생성한 초안 txt 파일을 섹션별 구조화 딕셔너리로 변환한다.

파일 구조 (구분자 `====` + `[헤더]` + `====` 로 섹션이 나뉨):
    [제목 후보 3개]
    [본문]
    [네이버 태그 10개]
    [이미지 텍스트 패키지]   ← 썸네일 + 카드1~3 텍스트
    [G2 자막 교차대조표]

사용:
    from parser import parse_draft
    data = parse_draft(text)        # 문자열 입력
    data = parse_draft_file(path)   # 파일 경로 입력
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# 섹션 분리
# ---------------------------------------------------------------------------

# `====...` 줄 + `[헤더]` 줄 + `====...` 줄 패턴을 잡아 섹션 헤더로 인식
_SECTION_RE = re.compile(
    r"^=+\s*\n\s*\[(?P<header>.+?)\]\s*\n^=+\s*$",
    re.MULTILINE,
)

# 본문 내부 주석 (네이버 발행에는 들어가면 안 되는 메모)
_SUBTITLE_NOTE_RE = re.compile(r"\[자막\s*근거:.*?\]", re.DOTALL)      # 출처 자막
_EXPERT_NOTE_RE = re.compile(r"〔.*?〕", re.DOTALL)                    # 전문가 보강 제안
_IMAGE_MARK_RE = re.compile(r"\[이미지\s*삽입:\s*(?P<desc>.*?)\]", re.DOTALL)  # 이미지 위치


def split_sections(text: str) -> dict[str, str]:
    """원본 텍스트를 {헤더: 본문} 딕셔너리로 분리한다.

    헤더는 대괄호 안 문자열(예: "제목 후보 3개"), 본문은 다음 섹션 직전까지의 텍스트.
    """
    sections: dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        header = m.group("header").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[header] = text[start:end].strip("\n")
    return sections


def _find_section(sections: dict[str, str], *keywords: str) -> str:
    """헤더에 키워드가 포함된 첫 섹션 본문을 반환 (없으면 빈 문자열).

    헤더 문구가 조금씩 달라져도("제목 후보 3개" vs "제목 후보") 견디도록 부분 일치 사용.
    """
    for header, body in sections.items():
        if all(k in header for k in keywords):
            return body
    return ""


# ---------------------------------------------------------------------------
# 개별 섹션 파서
# ---------------------------------------------------------------------------

_TITLE_PREFIX_RE = re.compile(r"^\s*후보\s*\d+\s*[.)]\s*")


def parse_titles(body: str) -> list[str]:
    """제목 후보 목록. "후보 1. " 접두어를 제거한다."""
    titles: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        titles.append(_TITLE_PREFIX_RE.sub("", line).strip())
    return titles


def parse_tags(body: str) -> list[str]:
    """태그 목록. 쉼표(또는 줄바꿈)로 구분된 태그를 정리한다.

    선두의 '#'은 제거 — 네이버 태그 입력창은 # 없이 받는다.
    """
    raw = body.replace("\n", ",")
    tags: list[str] = []
    for chunk in raw.split(","):
        tag = chunk.strip().lstrip("#").strip()
        if tag:
            tags.append(tag)
    return tags


def parse_body(body: str) -> dict[str, Any]:
    """본문을 발행용 깨끗한 텍스트와 내부 메모로 분리한다.

    반환:
        raw           : 원본 본문 전체
        clean         : 자막 근거·전문가 보강 메모를 제거한 발행용 본문
                        (이미지 삽입 위치는 [이미지 삽입: ...] 마커로 유지)
        image_markers : 본문에 등장한 이미지 삽입 지시 텍스트 목록(등장 순서)
    """
    image_markers = [m.group("desc").strip() for m in _IMAGE_MARK_RE.finditer(body)]

    clean = _SUBTITLE_NOTE_RE.sub("", body)
    clean = _EXPERT_NOTE_RE.sub("", clean)
    # 메모 제거로 생긴 3줄 이상 연속 공백 줄을 2줄로 압축
    clean = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", clean).strip("\n")

    return {"raw": body, "clean": clean, "image_markers": image_markers}


# ---------------------------------------------------------------------------
# 이미지 텍스트 패키지 파서
# ---------------------------------------------------------------------------

# 패키지 내부의 하위 블록 헤더: 한 줄에 `[...]` 형태로 단독 등장
_SUBBLOCK_RE = re.compile(r"^\s*\[(?P<header>[^\]]+)\]\s*$", re.MULTILINE)

# "1. 문구" / "2) 문구" 형태의 번호 목록
_NUM_ITEM_RE = re.compile(r"^\s*\d+\s*[.)]\s*(?P<text>.+?)\s*$")


def _split_subblocks(body: str) -> list[tuple[str, str]]:
    """이미지 패키지 본문을 [(하위헤더, 내용), ...] 으로 분리."""
    blocks: list[tuple[str, str]] = []
    matches = list(_SUBBLOCK_RE.finditer(body))
    for i, m in enumerate(matches):
        header = m.group("header").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        blocks.append((header, body[start:end].strip("\n")))
    return blocks


def _numbered_items(text: str) -> list[str]:
    """'1. ...' 형태의 번호 목록만 추출."""
    items = []
    for line in text.splitlines():
        m = _NUM_ITEM_RE.match(line)
        if m:
            items.append(m.group("text").strip())
    return items


def _parse_grid(text: str) -> list[list[str]]:
    """공백 2칸 이상으로 구분된 격자 표를 2차원 리스트로 변환.

    카드3 예시:
                초등 졸업    중등 졸업    고등 졸업
        이해력  700L        1,000L      1,300L
    → [["", "초등 졸업", "중등 졸업", "고등 졸업"],
       ["이해력", "700L", "1,000L", "1,300L"], ...]

    헤더 행은 좌상단이 비어 있으므로 데이터 행보다 칸이 하나 적다 → 빈 칸으로 보정.
    """
    rows: list[list[str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        cells = [c.strip() for c in re.split(r"\s{2,}", line.strip()) if c.strip()]
        if cells:
            rows.append(cells)
    if not rows:
        return rows
    width = max(len(r) for r in rows)
    # 칸 수가 부족한 행(주로 헤더)은 앞쪽을 빈 칸으로 채워 정렬
    for r in rows:
        while len(r) < width:
            r.insert(0, "")
    return rows


def _parse_card(header: str, body: str) -> dict[str, Any]:
    """카드 한 장을 파싱. 표가 있으면 grid, 없으면 lines 로 담는다.

    카드 본문 관용 구조:
        카드 제목: ...
        (본문 라인들)
        한 줄 설명: ...
        하단: ...
    """
    card: dict[str, Any] = {"header": header.strip(), "title": "", "lines": [],
                            "grid": [], "note": "", "footer": ""}
    content_lines: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("카드 제목:"):
            card["title"] = s.split(":", 1)[1].strip()
        elif s.startswith("한 줄 설명:"):
            card["note"] = s.split(":", 1)[1].strip()
        elif s.startswith("하단:"):
            card["footer"] = s.split(":", 1)[1].strip()
        else:
            content_lines.append(line)

    content = "\n".join(content_lines).strip("\n")
    grid = _parse_grid(content)
    # 표로 볼 수 있는 조건: 2행 이상 + 다열(여러 칸) 구조
    if len(grid) >= 2 and max((len(r) for r in grid), default=0) >= 2:
        card["grid"] = grid
    card["lines"] = [l.strip() for l in content_lines]
    return card


def parse_image_package(body: str) -> dict[str, Any]:
    """이미지 텍스트 패키지를 썸네일 + 카드 목록으로 구조화한다.

    반환:
        thumbnail : {"main": [...3개], "sub": [...2개]}
        cards     : [{"header","title","lines","grid","note","footer"}, ...]
    """
    result: dict[str, Any] = {"thumbnail": {"main": [], "sub": []}, "cards": []}

    for header, content in _split_subblocks(body):
        if "썸네일" in header:
            # "메인 문구 후보" / "보조 부제 후보" 두 묶음을 다시 나눔
            parts = re.split(r"(보조\s*부제\s*후보[^\n]*)", content)
            main_chunk = parts[0]
            sub_chunk = "".join(parts[1:]) if len(parts) > 1 else ""
            result["thumbnail"]["main"] = _numbered_items(main_chunk)
            result["thumbnail"]["sub"] = _numbered_items(sub_chunk)
        elif "카드" in header:
            result["cards"].append(_parse_card(header, content))

    return result


# ---------------------------------------------------------------------------
# 블로그용 본문 포매팅 (가독성 줄바꿈 + 소제목 추출)
# ---------------------------------------------------------------------------

# 문장 끝(. ? ! … 。) + 공백 기준 분리
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?…。])\s+")
# 쉼표 + '공백' 기준 분리 → "3,000" "1,300L" 처럼 공백 없는 숫자 쉼표는 안 끊김
_CLAUSE_SPLIT_RE = re.compile(r"(?<=,)\s+")
_SENT_END_CHARS = ".!?…。"


def _is_heading(line: str) -> bool:
    """소제목 여부 판정.

    소제목 특징: 마침표 없이 끝나는 비교적 짧은 단독 줄.
    제외 대상:
      · 이미지 마커('['로 시작)
      · 콜론 포함 데이터 라벨('이해력: ...')
      · 숫자가 들어간 줄('어휘력 6,000 단어' 같은 수치 데이터)
      · 따옴표를 벗겨도 문장부호로 끝나는 줄(인용문·질문 hook)
      · 너무 길거나 너무 짧은 줄
    """
    s = line.strip()
    if not s or s.startswith("[") or ":" in s:
        return False
    if any(ch.isdigit() for ch in s):  # 수치 데이터 줄 제외
        return False
    # 감싼 따옴표를 벗겨 실제 끝 문자로 판단
    core = s.strip("\"'“”‘’")
    if not core or core[-1] in _SENT_END_CHARS:
        return False
    return 6 <= len(core) <= 40


def _wrap_sentence(sentence: str, max_len: int) -> list[str]:
    """긴 문장을 쉼표(+공백) 단위로 적당히 모아 여러 줄로 나눈다.

    max_len 이하면 그대로 한 줄. 쉼표가 없으면 길어도 통째로 한 줄(억지로 안 끊음).
    """
    s = sentence.strip()
    if len(s) <= max_len:
        return [s]

    clauses = [c.strip() for c in _CLAUSE_SPLIT_RE.split(s) if c.strip()]
    if len(clauses) <= 1:
        return [s]  # 끊을 쉼표가 없음

    lines: list[str] = []
    cur = ""
    for c in clauses:
        if cur and len(cur) + len(c) + 1 > max_len:
            lines.append(cur)
            cur = c
        else:
            cur = f"{cur} {c}".strip() if cur else c
    if cur:
        lines.append(cur)
    return lines


def format_for_blog(text: str, max_len: int = 30,
                    heading_mark: str | None = None) -> dict[str, Any]:
    """본문을 블로그 가독성에 맞게 줄바꿈하고 소제목을 추출한다.

    규칙:
      · 마침표(. ? !) 뒤에서 줄바꿈 → 문장마다 한 줄
      · 한 줄이 max_len(기본 30자)을 넘으면 쉼표(+공백)에서 추가 줄바꿈
      · 숫자 속 쉼표(3,000 / 1,300L)는 끊지 않음
      · 소제목·이미지 표시줄은 원형 보존
      · 문단 사이 빈 줄은 유지

    heading_mark 가 주어지면 소제목 줄 끝에 그 표시를 덧붙인다
    (예: "@@소제목 강조" → 네이버에서 어느 줄을 키울지 본문 안에서 바로 확인).

    반환:
        text     : 포맷된 본문
        headings : 감지된 소제목 목록(네이버에서 글자 크기를 키울 후보)
    """
    headings: list[str] = []
    out: list[str] = []

    for line in text.splitlines():
        s = line.strip()
        if not s:
            out.append("")  # 문단 구분용 빈 줄 보존
            continue
        if s.startswith("["):  # 이미지 삽입 마커 등은 그대로
            out.append(s)
            continue
        if _is_heading(s):
            headings.append(s)
            out.append(f"{s}  {heading_mark}" if heading_mark else s)
            continue
        for sent in _SENT_SPLIT_RE.split(s):
            sent = sent.strip()
            if sent:
                out.extend(_wrap_sentence(sent, max_len))

    result = "\n".join(out)
    result = re.sub(r"\n{3,}", "\n\n", result).strip("\n")
    return {"text": result, "headings": headings}


# ---------------------------------------------------------------------------
# 표시용 변환 (앱에서 격자 카드를 표로 렌더링할 때 사용)
# ---------------------------------------------------------------------------

def grid_to_dataframe(grid: list[list[str]]):
    """파싱된 격자(2차원 리스트)를 표시용 pandas DataFrame으로 변환.

    두 가지 카드 형태를 구분한다:
      · 카드3형(진짜 격자표): 좌상단이 빈 칸 → 첫 행=열 머리글, 첫 열=행 이름
        예) ['', '초등 졸업', '중등 졸업', '고등 졸업'] / ['이해력','700L',...]
      · 카드2형(키-값 목록): 좌상단이 채워짐 → 머리글 없이 첫 열을 행 이름으로
        예) ['이해력','렉사일 1,300L'] (첫 항목이 머리글로 먹히지 않게)

    pandas 미설치/형태 불일치 등 실패 시 None 반환(호출부에서 텍스트로 대체).
    """
    try:
        import pandas as pd

        rows = [list(r) for r in grid if r]
        if not rows:
            return None

        has_header = rows[0][0] == ""
        if has_header:
            col_names = rows[0][1:]
            data_rows = rows[1:]
        else:
            col_names = None
            data_rows = rows

        index = [r[0] for r in data_rows]
        values = [r[1:] for r in data_rows]
        width = max((len(v) for v in values), default=0)
        for v in values:
            v += [""] * (width - len(v))  # 칸 수 보정

        if col_names is None or len(col_names) != width:
            # 머리글이 없거나 칸 수가 안 맞으면 머리글 없이(데이터 보존 우선)
            col_names = [""] * width

        return pd.DataFrame(values, index=index, columns=col_names)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 최상위 진입점
# ---------------------------------------------------------------------------

def parse_draft(text: str) -> dict[str, Any]:
    """헤르메스 초안 텍스트를 구조화 딕셔너리로 변환한다.

    반환 키:
        titles        : list[str]                — 제목 후보
        body          : {"raw","clean","image_markers"}
        tags          : list[str]                — 네이버 태그
        image_package : {"thumbnail","cards"}    — 이미지 텍스트 패키지
        cafe_note     : str                      — 카페 공유용 덧붙임 글(원문 그대로)
        crosscheck    : str                      — G2 자막 교차대조표(원문 그대로)
        sections      : dict[str, str]           — 인식된 모든 섹션 원문(디버그용)
    """
    sections = split_sections(text)

    return {
        "titles": parse_titles(_find_section(sections, "제목")),
        "body": parse_body(_find_section(sections, "본문")),
        "tags": parse_tags(_find_section(sections, "태그")),
        "image_package": parse_image_package(_find_section(sections, "이미지", "패키지")),
        "cafe_note": _find_section(sections, "덧붙임"),
        "crosscheck": _find_section(sections, "교차대조표"),
        "sections": sections,
    }


def parse_draft_file(path: str, encoding: str = "utf-8") -> dict[str, Any]:
    """파일 경로로부터 초안을 읽어 파싱한다."""
    with open(path, "r", encoding=encoding) as f:
        return parse_draft(f.read())


# ---------------------------------------------------------------------------
# 셀프 테스트: 샘플 파일을 파싱해 결과 요약 출력
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # Windows 콘솔(cp949)에서도 한글·특수문자(— 등)가 깨지지 않도록 UTF-8 강제
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    sample = sys.argv[1] if len(sys.argv) > 1 else "blog-ep2-draft.txt"
    data = parse_draft_file(sample)

    print(f"=== 인식된 섹션: {list(data['sections'].keys())}\n")

    print(f"제목 후보 {len(data['titles'])}개:")
    for t in data["titles"]:
        print(f"  - {t}")

    print(f"\n태그 {len(data['tags'])}개: {', '.join(data['tags'])}")

    print(f"\n본문(clean) 글자수: {len(data['body']['clean'])}")
    print(f"본문 내 이미지 삽입 마커 {len(data['body']['image_markers'])}개:")
    for mk in data["body"]["image_markers"]:
        print(f"  - {mk[:50]}...")

    pkg = data["image_package"]
    print(f"\n썸네일 메인 문구 {len(pkg['thumbnail']['main'])}개: {pkg['thumbnail']['main']}")
    print(f"썸네일 보조 부제 {len(pkg['thumbnail']['sub'])}개: {pkg['thumbnail']['sub']}")
    print(f"\n카드 {len(pkg['cards'])}장:")
    for c in pkg["cards"]:
        kind = f"표 {len(c['grid'])}행" if c["grid"] else f"텍스트 {len(c['lines'])}줄"
        print(f"  - [{c['header']}] 제목='{c['title']}' ({kind})")
        if c["grid"]:
            for row in c["grid"]:
                print("      " + " | ".join(row))

    print(f"\n교차대조표 글자수: {len(data['crosscheck'])}")
