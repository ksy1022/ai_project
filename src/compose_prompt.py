# src/compose_prompt.py
import re

def _clean_text(s: str) -> str:
    s = s.replace("\r\n", "\n").strip()
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s

def build_suno_prompt(merge_text: str) -> dict:
    # merge_text에서 가사 부분만 추출
    # 형식: "### 4) 8마디 분량 가사 초안\n가사 내용..."
    lyrics = _clean_text(merge_text)
    
    # "### 4) 8마디 분량 가사 초안" 또는 "4) 8마디 분량 가사 초안" 이후의 내용만 추출
    # 여러 패턴 시도
    extracted_lyrics = None
    
    # 패턴 1: "### 4) 8마디 분량 가사 초안" 이후의 모든 내용
    match = re.search(r"###\s*4\)\s*8마디\s*분량\s*가사\s*초안\s*\n(.*)", lyrics, re.DOTALL | re.IGNORECASE)
    if match:
        extracted_lyrics = match.group(1).strip()
    else:
        # 패턴 2: "4) 8마디 분량 가사 초안" 이후의 모든 내용
        match = re.search(r"4\)\s*8마디\s*분량\s*가사\s*초안\s*\n(.*)", lyrics, re.DOTALL | re.IGNORECASE)
        if match:
            extracted_lyrics = match.group(1).strip()
        else:
            # 패턴 3: "가사 초안" 이후의 모든 내용
            match = re.search(r"가사\s*초안[:\-]?\s*\n(.*)", lyrics, re.DOTALL | re.IGNORECASE)
            if match:
                extracted_lyrics = match.group(1).strip()
            else:
                # 패턴 4: "### 4)" 이후의 모든 내용
                parts = re.split(r"###\s*4\)", lyrics, flags=re.IGNORECASE)
                if len(parts) > 1:
                    extracted_lyrics = parts[-1].strip()
                    # "8마디 분량 가사 초안" 같은 헤더 제거
                    extracted_lyrics = re.sub(r"^.*?8마디\s*분량\s*가사\s*초안[:\-]?\s*\n?", "", extracted_lyrics, flags=re.IGNORECASE)
                    extracted_lyrics = re.sub(r"^.*?가사\s*초안[:\-]?\s*\n?", "", extracted_lyrics, flags=re.IGNORECASE)
    
    # 가사를 찾지 못한 경우, "### 1)", "### 2)", "### 3)" 섹션을 모두 제거
    if not extracted_lyrics or len(extracted_lyrics) < 10:
        # 모든 "### 숫자)" 섹션 제거
        lines = lyrics.split('\n')
        in_lyrics_section = False
        lyrics_lines = []
        
        for line in lines:
            # "### 4)" 또는 "4) 8마디" 또는 "가사 초안"이 나오면 그 이후부터 가사로 간주
            if re.search(r"###\s*4\)|4\)\s*8마디|가사\s*초안", line, re.IGNORECASE):
                in_lyrics_section = True
                # 헤더 라인은 제외하고 다음 줄부터
                continue
            elif re.search(r"###\s*[123]\)", line):
                # 1, 2, 3번 섹션은 건너뛰기
                in_lyrics_section = False
                continue
            elif in_lyrics_section:
                lyrics_lines.append(line)
        
        if lyrics_lines:
            extracted_lyrics = '\n'.join(lyrics_lines).strip()
        else:
            # 최후의 수단: 전체에서 "### 숫자)" 섹션만 제거
            extracted_lyrics = re.sub(r"###\s*\d+\)[^\n]*\n.*?(?=###|\Z)", "", lyrics, flags=re.DOTALL)
            extracted_lyrics = extracted_lyrics.strip()
    
    # 최종 정리: 빈 줄 제거, 연속된 공백 정리, 앞뒤 공백 제거
    if extracted_lyrics:
        lines = [line.strip() for line in extracted_lyrics.split('\n') if line.strip()]
        extracted_lyrics = '\n'.join(lines)
    else:
        extracted_lyrics = lyrics  # 최후의 수단
    
    # 한국어 가사임을 명시적으로 표시하는 스타일 설정
    # Suno API가 한국어를 인식하도록 "Korean language", "Korean lyrics" 명시
    style = "K-pop ballad / Korean language / Korean lyrics / warm female vocal / soft piano & strings / 85–92 BPM / intimate, modern city pop color"
    
    # 간단한 제목
    base_title = "MAS Demo Track"
    title = base_title if len(base_title) <= 80 else (base_title[:76] + "...")

    return {
        "customMode": True,
        "instrumental": False,
        "model": "V4_5",  # ← 필수: V3_5 | V4 | V4_5 | V4_5PLUS | V5
        "style": style,
        "title": title,
        # ⚠️ 핵심: 커스텀 모드에서 prompt가 '가사'로 사용됨 (한국어 가사만)
        "prompt": extracted_lyrics
    }
