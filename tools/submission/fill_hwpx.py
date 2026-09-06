"""HWPX 양식의 안내문 문단을 실제 내용으로 치환한다.

HWPX 는 ZIP + XML 이다. 본문은 Contents/section0.xml 의 <hp:p> 문단 목록이고,
각 문단은 <hp:run><hp:t>텍스트</hp:t></hp:run> 구조다.

치환 전략: 안내문을 담은 문단 하나를 찾아, 같은 서식(paraPrIDRef/charPrIDRef)을
쓰는 문단 여러 개로 바꾼다. <hp:linesegarray> 는 줄바꿈 위치 캐시라 그대로 복제하면
줄 수가 안 맞으므로 넣지 않는다 — 한글이 파일을 열 때 다시 계산한다.
"""

from __future__ import annotations

import re
import shutil
import sys
import zipfile
from pathlib import Path

XML_ESC = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}


def esc(t: str) -> str:
    for a, b in XML_ESC.items():
        t = t.replace(a, b)
    return t


def find_paragraph(xml: str, needle: str) -> tuple[int, int, str, str] | None:
    """안내문을 담은 <hp:p> 블록의 (시작, 끝, paraPrIDRef, charPrIDRef)."""
    i = xml.find(f">{needle}<")
    if i < 0:
        i = xml.find(needle)
        if i < 0:
            return None
    start = xml.rfind("<hp:p ", 0, i)
    end = xml.find("</hp:p>", i) + len("</hp:p>")
    block = xml[start:end]
    para = re.search(r'paraPrIDRef="(\d+)"', block)
    char = re.search(r'charPrIDRef="(\d+)"', block)
    return start, end, (para.group(1) if para else "0"), (char.group(1) if char else "0")


def build_paragraphs(lines: list[str], para_id: str, char_id: str) -> str:
    out = []
    for ln in lines:
        body = (
            f'<hp:run charPrIDRef="{char_id}"><hp:t>{esc(ln)}</hp:t></hp:run>'
            if ln
            else f'<hp:run charPrIDRef="{char_id}"/>'
        )
        out.append(
            f'<hp:p id="2147483648" paraPrIDRef="{para_id}" styleIDRef="0" '
            f'pageBreak="0" columnBreak="0" merged="0">{body}</hp:p>'
        )
    return "".join(out)


def fill(src: Path, dst: Path, mapping: dict[str, list[str]]) -> None:
    shutil.copy(src, dst)
    with zipfile.ZipFile(src) as z:
        names = z.namelist()
        blobs = {n: z.read(n) for n in names}

    xml = blobs["Contents/section0.xml"].decode("utf-8")
    filled, missed = 0, []
    for needle, lines in mapping.items():
        found = find_paragraph(xml, needle)
        if not found:
            missed.append(needle)
            continue
        s, e, para_id, char_id = found
        xml = xml[:s] + build_paragraphs(lines, para_id, char_id) + xml[e:]
        filled += 1
    blobs["Contents/section0.xml"] = xml.encode("utf-8")

    # mimetype 은 ZIP 첫 항목·무압축이어야 한다(OCF 규약).
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        if "mimetype" in blobs:
            z.writestr(zipfile.ZipInfo("mimetype"), blobs["mimetype"], zipfile.ZIP_STORED)
        for n in names:
            if n != "mimetype":
                z.writestr(n, blobs[n])
    print(f"  {dst.name}: {filled}개 채움" + (f", 미발견 {len(missed)}개" if missed else ""))
    for m in missed:
        print(f"    [미발견] {m[:70]}")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    import plan_content as P
    import spec_content as S

    # 대회가 배포한 빈 양식 HWPX 가 있는 디렉터리.
    # 기본값은 이 스크립트 옆의 forms/ 이며, 첫 인자 다음에 경로를 주면 바꿀 수 있다.
    dl = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / "forms"
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)

    fill(
        dl / "(첨부1) 2026 금융 AI Challenge 공모전 기획서.hwpx",
        out / "2026 금융 AI Challenge 기획서 - 채무회복 내비게이터.hwpx",
        {**P.TEAM, **P.PLAN},
    )
    fill(
        dl / "(첨부2) 2026 금융 AI Challenge 기능명세서.hwpx",
        out / "2026 금융 AI Challenge 기능명세서 - 채무회복 내비게이터.hwpx",
        {**S.TEAM, **S.SPEC},
    )
