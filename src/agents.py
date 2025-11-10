# src/agents.py
from openai import OpenAI

SYSTEM_CORE = "너는 작사 보조 시스템이다 한국어만 사용 간결하고 중복 회피"

def call_agent(client, role_name, instruction, context):
    msg = f"[역할]{role_name}\n[지시]{instruction}\n[콘텍스트]\n{context}\n[출력] 한 단락 제안과 핵심 키워드 5개"
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
    return r.choices[0].message.content.strip()