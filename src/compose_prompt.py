# src/compose_prompt.py
import re

def _clean_text(s: str) -> str:
    s = s.replace("\r\n", "\n").strip()
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s

def build_suno_prompt(merge_text: str) -> dict:
    lyrics = _clean_text(merge_text)
    return {
        "customMode": True,
        "instrumental": False,
        "model": "V4_5",  # ← 필수: V3_5 | V4 | V4_5 | V4_5PLUS | V5
        "style": "K-pop ballad / warm female vocal / soft piano & strings / 85–92 BPM",
        "title": "MAS Demo Track",
        "prompt": lyrics     # 커스텀 모드에서는 prompt = 가사(노랫말)
    }

    # 간단한 스타일 요약 (원하면 MAS 출력에서 키워드/태그를 파싱해 더 정교화 가능)
    style = "K-pop ballad / warm female vocal / soft piano & strings / 85–92 BPM / intimate, modern city pop color"

    # 간단한 제목
    base_title = "MAS Demo Track"
    title = base_title if len(base_title) <= 80 else (base_title[:76] + "...")

    return {
        "customMode": True,
        "instrumental": False,
        "model": "V4_5",
        "style": style,
        "title": title,
        # ⚠️ 핵심: 커스텀 모드에서 prompt가 '가사'로 사용됨
        "prompt": lyrics
    }
