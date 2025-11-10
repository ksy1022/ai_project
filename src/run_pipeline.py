# src/run_pipeline.py
import os
from dotenv import load_dotenv
from openai import OpenAI
from vision_to_query import image_to_query
from search_lyrics import LyricsSearcher
from agents import debate_and_merge
from compose_prompt import build_suno_prompt

def main(image_path):
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 없어서 진행 불가")

    # 1) 이미지 → 쿼리
    query = image_to_query(image_path, api_key)
    print("쿼리:", query)

    # 2) 벡터 검색
    searcher = LyricsSearcher(
        index_path="C:/ai/data/songs.index",
        meta_path="C:/ai/data/songs_meta.pkl",
        api_key=api_key
    )
    hits = searcher.search(query, k=5)
    print("후보 개수:", len(hits))

    # 3) MAS로 합의 가사
    client = OpenAI(api_key=api_key)
    merged = debate_and_merge(client, query, hits)
    print("\n[합의 가사]\n", merged)

    # 4) Suno 프롬프트
    suno_payload = build_suno_prompt(merged)
    print("\n[Suno 요청 페이로드]\n", suno_payload)

if __name__ == "__main__":
    # 예시 경로 수정 필요
    main("/Users/rlatj/OneDrive/바탕화~1-LAPTOP-KOED36DO-1262057/tree.jpeg")