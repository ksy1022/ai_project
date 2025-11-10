# src/run_pipeline.py
import os
import time
import json
import pathlib
import requests
import urllib.parse
from typing import Dict, Any, List, Union, Optional, Tuple

from dotenv import load_dotenv
from openai import OpenAI
from vision_to_query import image_to_query
from search_lyrics import LyricsSearcher
from agents import debate_and_merge
from compose_prompt import build_suno_prompt


def _pull_webhook_site_latest(token: str) -> dict | None:
    """
    webhook.site 토큰으로 최근 콜백 1건을 가져와 JSON 반환.
    webhook.site UI에서 'Copy token' 값 사용.
    """
    try:
        url = f"https://webhook.site/token/{token}/requests?sorting=newest"
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        j = r.json()
        data = j.get("data") or []
        if not data:
            return None
        # 본문은 text로 저장됨. JSON이면 그대로 파싱
        content = data[0].get("content") or ""
        # JSON일 확률이 높음
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None
    except Exception:
        return None


# ----------------------------
# 유틸
# ----------------------------
def _get_env(key: str, required: bool = False, default: str = "") -> str:
    v = os.getenv(key, default)
    if required and not v:
        raise RuntimeError(f"{key} 없어서 진행 불가")
    return v

def _ensure_outputs_dir() -> pathlib.Path:
    out = pathlib.Path(__file__).resolve().parent.parent / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    return out


# --- build_suno_prompt 아래에서 suno_generate_and_wait 호출하기 직전 ---

def _normalize_suno_payload(p):
    # 문자열(가사만) 오면 감싸기
    if isinstance(p, str):
        p = {
            "customMode": True,
            "instrumental": False,  # ← 반드시 불리언
            "model": "V4_5",
            "style": "K-pop ballad / warm female vocal / soft piano & strings / 85–92 BPM",
            "title": "MAS Demo Track",
            "prompt": p,  # 커스텀 모드에서 prompt=가사
        }
        return p

    # dict일 때 기본값/규격 보정
    p.setdefault("customMode", True)

    # 'lyrics'만 있고 'prompt'가 없으면 옮기기
    if "lyrics" in p and "prompt" not in p:
        p["prompt"] = p.pop("lyrics")

    # instrumental 보정: None/string → 불리언
    inst = p.get("instrumental", False)
    if isinstance(inst, str):
        inst = inst.strip().lower() in {"true", "1", "yes", "y"}
    p["instrumental"] = bool(inst)  # ← 핵심: 항상 불리언

    # 필수 필드 채우기
    p["model"] = p.get("model") or "V4_5"
    p["style"] = p.get("style") or "K-pop ballad / warm female vocal / soft piano & strings / 85–92 BPM"
    p["title"] = p.get("title") or "MAS Demo Track"

    # prompt(=가사) 확인
    if not p.get("prompt"):
        raise RuntimeError("Suno payload 오류: prompt(가사)가 비어 있습니다.")

    # None 값 제거(일부 제공자에서 null 싫어함)
    for k in list(p.keys()):
        if p[k] is None:
            del p[k]
    return p




# ----------------------------
# Suno API 연동
# ----------------------------
def suno_generate_and_wait(
    payload: Dict[str, Any],
    api_key: str,
    base_url: str = "https://api.sunoapi.org/api/v1",
    timeout_sec: int = 600,              # ← 10분로 상향
    poll_interval: float = 2.5,
    verbose: bool = True,                # ← 디버그 로그 on
) -> Dict[str, Any]:
    if not api_key:
        raise RuntimeError("SUNO_API_KEY 없어서 음악 생성 불가")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "ai-project-main/1.0 (+requests)",
        "Connection": "close",
    }

    # 1) 생성 요청
    url_generate = f"{base_url}/generate"
    if verbose:
        print(f"[Suno] POST {url_generate}")
        # 너무 길면 일부만
        try:
            print("[Suno] Payload:", json.dumps(payload, ensure_ascii=False)[:1000])
        except Exception:
            pass

    r = requests.post(url_generate, headers=headers, json=payload, timeout=(10, 45))
    try:
        r.raise_for_status()
    except Exception:
        raise RuntimeError(f"Suno generate 실패: HTTP {r.status_code}\n본문: {r.text[:1000]}")

    try:
        data = r.json()
    except ValueError:
        raise RuntimeError(f"Suno generate 응답이 JSON 아님\n본문: {r.text[:1000]}")

    if verbose:
        print("[Suno] generate 응답:", json.dumps(data, ensure_ascii=False)[:1000])

    # 공통 에러 코드 처리
    if isinstance(data, dict) and data.get("code") and data["code"] != 200:
        raise RuntimeError(
            f"Suno generate 에러 code={data.get('code')}, "
            f"msg={data.get('msg') or data.get('message') or data}"
        )

    # 다양한 스키마에서 식별자 추출
    task_id = (
        data.get("data", {}).get("taskId")
        or data.get("data", {}).get("task_id")
        or data.get("data", {}).get("workId")
        or data.get("taskId")
        or data.get("task_id")
        or data.get("workId")
    )
    if not task_id:
        raise RuntimeError(f"Suno generate 응답에서 작업 ID(taskId/workId)를 찾지 못함: {data}")
    
     # 2) 상태 폴링: GET 우선 → 실패 시 POST 폴백
    url_record = f"{base_url}/generate/record-info"
    start = time.time()
    attempt = 0
    last_status = None

    def parse_items(st: dict) -> Tuple[Optional[str], Optional[List[dict]]]:
        """
        상태 문자열과 결과 아이템 리스트를 다양한 스키마에서 추출.
        Suno 변형 스키마(response.sunoData 등)까지 처리.
        """
        data_field = st.get("data") or {}

        # 상태 문자열 후보
        status = (
            data_field.get("status")
            or st.get("status")
            or data_field.get("taskStatus")
            or st.get("taskStatus")
        )

        # 결과 blob
        resp = data_field.get("response")  # dict 또는 None
        raw = None
        if isinstance(resp, dict):
            # ✅ 여기서 sunoData를 우선적으로 본다
            raw = resp.get("sunoData") or resp.get("data") or resp.get("songs")
        if raw is None:
            # 혹시 상위에 바로 들어오는 케이스
            raw = data_field.get("sunoData") or data_field.get("data") or st.get("result")

        # raw 정규화: list로
        if isinstance(raw, dict):
            raw = [raw]
        if raw is not None and not isinstance(raw, list):
            raw = None

        # 아이템 정규화: 공통 키로 맞춤
        items = None
        if raw:
            items = []
            for it in raw:
                if not isinstance(it, dict):
                    continue
                items.append({
                    "id": it.get("id") or it.get("musicId") or it.get("songId"),
                    "title": it.get("title") or data_field.get("title") or "MAS Demo Track",
                    # 오디오 URL 후보들 (우선순위: 직접 다운로드 가능한 것 → CDN → 스트림)
                    "audioUrl": it.get("audioUrl") or it.get("sourceAudioUrl") or it.get("streamAudioUrl"),
                    "imageUrl": it.get("imageUrl") or it.get("coverUrl"),
                    # 필요 시 다른 필드도 보존
                    "raw": it,
                })
            if not items:
                items = None

        return status, items

    while time.time() - start < timeout_sec:
        attempt += 1
        if attempt > 1:
            # 점진적 백오프(최대 8초)
            time.sleep(min(poll_interval * (1 + attempt * 0.25), 8.0))

        # --- GET 시도 ---
        try:
            s = requests.get(
                url_record,
                headers=headers,
                params={"taskId": task_id, "task_id": task_id, "workId": task_id},
                timeout=(10, 45),
            )
            if s.status_code == 200:
                try:
                    st = s.json()
                except ValueError:
                    st = None
                if st:
                    if verbose and (attempt % 3 == 1):
                        print("[Suno][GET] 응답:", json.dumps(st, ensure_ascii=False)[:800])
                    if st.get("code") and st["code"] != 200:
                        raise RuntimeError(f"Suno record-info 에러 GET code={st.get('code')}, msg={st.get('msg') or st.get('message') or st}")
                    status, items = parse_items(st)
                    if status and status != last_status:
                        last_status = status
                        if verbose:
                            print(f"[Suno] status={status} (attempt {attempt})")
                    if status in {"SUCCESS", "DONE", "COMPLETED"}:
                        if items:
                            return {"task_id": task_id, "tracks": items}
                        # 성공 표시는 떴는데 아직 리스트가 비어있으면 한 번 더 기다림
                        continue
                    if status in {"FAILED", "ERROR"}:
                        raise RuntimeError(f"Suno 생성 실패 상태 수신(GET): {st}")
                    # PENDING/PROCESSING/CREATING/QUEUED 등 → 계속 대기
                    continue
        except requests.exceptions.RequestException:
            # GET 실패 → POST 폴백
            pass

        # --- POST 폴백 ---
        try:
            s = requests.post(
                url_record,
                headers=headers,
                json={"taskId": task_id, "task_id": task_id, "workId": task_id},
                timeout=(10, 45),
            )
            if s.status_code == 200:
                try:
                    st = s.json()
                except ValueError:
                    st = None
                if st:
                    if verbose and (attempt % 3 == 1):
                        print("[Suno][POST] 응답:", json.dumps(st, ensure_ascii=False)[:800])
                    if st.get("code") and st["code"] != 200:
                        raise RuntimeError(f"Suno record-info 에러 POST code={st.get('code')}, msg={st.get('msg') or st.get('message') or st}")
                    status, items = parse_items(st)
                    if status and status != last_status:
                        last_status = status
                        if verbose:
                            print(f"[Suno] status={status} (attempt {attempt})")
                    if status in {"SUCCESS", "DONE", "COMPLETED"}:
                        if items:
                            return {"task_id": task_id, "tracks": items}
                        continue
                    if status in {"FAILED", "ERROR"}:
                        raise RuntimeError(f"Suno 생성 실패 상태 수신(POST): {st}")
                    continue
        except requests.exceptions.RequestException:
            continue

    # 타임아웃 시 마지막 상태라도 알리기
    raise TimeoutError(f"Suno 생성 대기 시간 초과 (마지막 status={last_status}, task_id={task_id})")
def download_audio(url: str, save_dir: pathlib.Path, filename: str = None) -> pathlib.Path:
    if filename is None:
        filename = url.split("/")[-1].split("?")[0] or "suno_audio.mp3"
        if not filename.endswith(".mp3"):
            filename += ".mp3"
    path = save_dir / filename
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
    return path

# ----------------------------
# 메인 파이프라인
# ----------------------------
def main(image_path):
    load_dotenv()

    # 키 로드
    api_key = _get_env("OPENAI_API_KEY", required=True)
    suno_key = _get_env("SUNO_API_KEY", required=True)
    suno_base = _get_env("SUNO_BASE_URL", default="https://api.sunoapi.org/api/v1")
    webhook_token = os.getenv("WEBHOOK_SITE_TOKEN")  # 토큰만 (URL 말고 token)

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

    # 4) Suno 프롬프트 (커스텀 모드용)
    suno_payload: Union[str, Dict[str, Any]] = build_suno_prompt(merged)
    suno_payload = _normalize_suno_payload(suno_payload)
    callback_url = _get_env("SUNO_CALLBACK_URL", default="https://httpbin.org/post")
    suno_payload.setdefault("callBackUrl", callback_url)
    suno_payload.setdefault("callbackUrl", callback_url)
    if isinstance(suno_payload, str):
        # 혹시 문자열만 올 경우 대비(가사만 온 경우)
        suno_payload = {
            "customMode": True,
            "instrumental": False,
            "model": "V4_5",
            "style": "K-pop ballad / warm female vocal / soft piano & strings / 85–92 BPM",
            "title": "MAS Demo Track",
            "prompt": suno_payload
        }

    print("\n[Suno 요청 페이로드]\n", json.dumps(suno_payload, ensure_ascii=False, indent=2))

    dry_run = os.getenv("DRY_RUN", "0") == "1"
    if dry_run:
        print("\n[DRY RUN] Suno 호출을 생략합니다. (크레딧 사용 없음)")
        print("[DRY RUN] 파이프라인은 정상이며, 여기서 Suno API만 빠졌습니다.")
        return

    # 5) Suno 생성
    print("\n🎵 Suno 음악 생성 중...")
    result = suno_generate_and_wait(suno_payload, api_key=suno_key, base_url=suno_base)
    tracks: List[Dict[str, Any]] = result.get("tracks", [])

    # 6) 결과 출력 + 저장
    outdir = _ensure_outputs_dir()
    print(f"\n생성 완료! (task_id={result['task_id']})  저장 경로: {outdir}")
    for i, t in enumerate(tracks, 1):
        title = t.get("title") or f"track_{i}"
        duration = t.get("duration")
        # URL 우선순위 강화
        audio_url = (
            t.get("sourceAudioUrl") or
            t.get("audioUrl") or
            t.get("streamAudioUrl") or
            t.get("audio_url")
        )
        print(f"[트랙 {i}] {title} — {duration}s")
        print("URL:", audio_url)
        if not audio_url:
            print("⚠ 오디오 URL이 비었습니다. 다음 트랙으로 넘어갑니다.")
            continue

        if audio_url:
            safe = "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in title)
            p = download_audio(audio_url, outdir, filename=f"{i:02d}_{safe}.mp3")
            print("저장:", p)

if __name__ == "__main__":
    # 예시 경로 수정 필요
    main("/Users/rlatj/OneDrive/바탕화~1-LAPTOP-KOED36DO-1262057/tree.jpeg")
