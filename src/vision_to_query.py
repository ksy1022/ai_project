# src/vision_to_query.py
import base64
from openai import OpenAI

def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def image_to_query(image_path, api_key, model="gpt-4o-mini"):  # 모델명은 예시 확실하지 않음
    client = OpenAI(api_key=api_key)
    b64 = encode_image(image_path)
    prompt = "사진을 한두 문장으로 묘사해줘 한국어 한 줄 요약 포함"
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role":"system","content":"간결 한국어 답변"},
            {"role":"user","content":[
                {"type":"text","text":prompt},
                {"type":"image_url","image_url":{"url":f"data:image/png;base64,{b64}" }}
            ]}
        ],
        temperature=0.2
    )
    text = resp.choices[0].message.content.strip()
    # 한 줄 요약만 추출
    return text.splitlines()[0]