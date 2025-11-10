# src/compose_prompt.py
def build_suno_prompt(merge_text):
    return {
        "style": "k-pop ballad modern city pop",
        "language": "ko",
        "prompt": "감성적 서정 도시적 세련 따뜻한 잔향",
        "lyrics": merge_text
    }