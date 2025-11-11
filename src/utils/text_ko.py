# src/utils/text_ko.py
import re, unicodedata

ALLOW_EN = {"love","baby","yeah","oh","feel","heart","light","dream","tonight","stay","you","me","we","my","your"}

HANGUL_KEEP = re.compile(r"[^가-힣0-9 .,!?()\n\-]")

def normalize_ko(text: str) -> str:
    t = unicodedata.normalize("NFC", str(text))
    t = HANGUL_KEEP.sub("", t)        # 한글/숫자/기본부호만 유지
    t = re.sub(r"[ \t]{2,}", " ", t)  # 공백 정리
    t = re.sub(r"\n{3,}", "\n\n", t)  # 과도한 빈줄 제거
    return t.strip()

def korean_ratio(text: str) -> float:
    if not text: return 0.0
    tot = len(text); ko = sum(1 for ch in text if "가" <= ch <= "힣")
    return ko / max(tot, 1)

def keep_whitelist_english(text: str) -> str:
    # 알파벳 단어만 찾고 화이트리스트 밖이면 제거
    def repl(m):
        w = m.group(0)
        return w if w.lower() in ALLOW_EN else ""
    return re.sub(r"[A-Za-z]+", repl, text)

def limit_english_ratio_by_section(text: str) -> str:
    """
    섹션 헤더(대략) 기준으로 영어 비율을 제한.
    규칙: Verse<=5%, Pre<=10%, Chorus<=35%, Bridge/Outro<=15%
    섹션 헤더가 없으면 전체를 Verse 규칙으로 간주.
    """
    rules = {
        "verse": 0.05, "pre-chorus": 0.10, "pre chorus": 0.10,
        "chorus": 0.35, "hook": 0.35, "bridge": 0.15, "outro": 0.15
    }
    lines = text.splitlines()
    out, cur_name, cur_buf = [], "verse", []

    def flush():
        if not cur_buf: return
        chunk = "\n".join(cur_buf)
        # 영어 단어 비율 계산
        letters = re.findall(r"[A-Za-z]", chunk)
        ratio = (len(letters) / max(len(chunk),1))
        maxr = rules.get(cur_name, 0.05)  # 기본 verse 규칙
        if ratio > maxr:
            # 영어 과다 시: 화이트리스트만 유지하고 나머지 영어 제거
            chunk = keep_whitelist_english(chunk)
        out.append(chunk)

    for ln in lines:
        low = ln.strip().lower()
        if any(k in low for k in rules.keys()):
            flush()
            cur_name = next((k for k in rules.keys() if k in low), "verse")
            cur_buf = [ln]
        else:
            cur_buf.append(ln)
    flush()
    return "\n".join(out)