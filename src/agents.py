# src/agents.py
from openai import OpenAI
from utils.text_ko import normalize_ko, korean_ratio, keep_whitelist_english, limit_english_ratio_by_section

MIX_GUIDE = """
[언어 혼합 규칙]
- Verse: 한국어 95% 이상(영어 ≤ 5%)
- Pre-Chorus: 한국어 90% 이상(영어 ≤ 10%)
- Chorus/Hook: 영어 20~35% 허용(짧은 키워드/후렴 위주)
- Bridge/Outro: 영어 ≤ 15%, 문장 남발 금지
[영어 허용 단어(화이트리스트)]
love, baby, yeah, oh, feel, heart, light, dream, tonight, stay, you, me, we, my, your
[금지]
- 로마자 한국어(예: saranghae)
- 의미 없는 음절 반복(la, na 등)
"""


SYSTEM_CORE = (
    "너는 작사 보조 시스템이다. 기본은 한국어이며, 위치에 따라 제한적으로 영어 단어를 섞는다. "
    "영어 문장 남발 금지, 로마자 한국어 금지, 의미 없는 음절 반복 금지(la, na 등)."
)

def call_agent(client, role_name, instruction, context):
    msg = (
        f"{MIX_GUIDE}\n"  # 👈 규칙을 가장 먼저 넣기
        f"[역할]{role_name}\n"
        f"[지시]{instruction}\n"
        f"[콘텍스트]\n{context}\n"
        "[출력 지시]\n"
        "- 섹션별 영어 비율 준수\n"
        "- 영어는 화이트리스트 단어만 사용\n"
        "- 로마자 한국어 금지, 의미 없는 음절 반복 금지\n"
        "- 결과는 한국어 문장 중심으로 작성"
    )
    resp = client.chat.completions.create(
        model="gpt-4o-mini",  # 예시 확실하지 않음
        messages=[
            {"role":"system","content":SYSTEM_CORE},
            {"role":"user","content":msg}
        ],
        temperature=0.7
    )
    return resp.choices[0].message.content.strip()

def debate_and_merge(client, query, hits):
    # 컨텍스트 생성
    snippets = []
    for h in hits:
        # 너무 길면 200자 제한
        lyric = h.get("text","")
        if len(lyric) > 200:
            lyric = lyric[:200] + "..."
        snippets.append(f"{h['title']} / {h['singer']} / {lyric}")
    ctx = f"쿼리: {query}\n후보:\n" + "\n".join(f"- {s}" for s in snippets)

    a1 = call_agent(client, "감성 에이전트", "정서 톤과 감정선 제안", ctx)
    a2 = call_agent(client, "기분 에이전트", "분위기 장르 템포 태그 제안", ctx)
    a3 = call_agent(client, "이성 에이전트", "서사 흐름 구간 제목 구조 제안", ctx)

    merge_prompt = f"""
다음 세 제안을 결합해 작사 가이드 한 버전으로 합의본을 만들어라
- 감성: {a1}
- 기분: {a2}
- 이성: {a3}
출력 형식
1) 핵심 키워드 8개
2) 분위기 태그 6개
3) 서사 구조 한 줄 목차
4) 8마디 분량 가사 초안 한국어
    """.strip()

    r = client.chat.completions.create(
        model="gpt-4o-mini",  # 예시 확실하지 않음
        messages=[
            {"role":"system","content":SYSTEM_CORE},
            {"role":"user","content":merge_prompt}
        ],
        temperature=0.6
    )

    out= r.choices[0].message.content.strip()
    out = normalize_ko(keep_whitelist_english(limit_english_ratio_by_section(out)))
    return out