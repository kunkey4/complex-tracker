# llm_engine.py — LLM 분석 엔진 (OpenAI / Anthropic 양쪽 지원)
from __future__ import annotations

import json
from config import FACTORS, DURATION_DAYS


# ─── 프롬프트 생성 ──────────────────────────────────────────────────────────────

def _build_prompt(content: str, existing_memos: list) -> str:
    if existing_memos:
        memo_lines = []
        for m in existing_memos[-15:]:  # 최근 15개만 컨텍스트로 사용
            memo_lines.append(
                f'ID="{m["id"]}" | 요약="{m.get("summary","")}" | '
                f'팩터={m["factors"]} | 내용="{m["content"][:80]}"'
            )
        memo_context = "\n".join(memo_lines)
    else:
        memo_context = "없음 (첫 번째 메모)"

    return f"""당신은 복잡계 투자 분석 AI입니다.
아래 텍스트를 분석한 뒤, 반드시 유효한 JSON **만** 응답하세요. 그 외 텍스트는 절대 포함하지 마세요.

━━━ 6대 투자 팩터 정의 ━━━
• 정치   : 선거, 정책 변화, 규제, 지정학 리스크, 무역 전쟁
• 경제   : 금리, 인플레이션, GDP, 실업률, 환율, 무역수지
• 과학/기술: AI·반도체·바이오·에너지 혁신, 기술 트렌드
• 펀더멘털: 기업 실적·밸류에이션·공급망·시장 점유율
• 유동성  : 통화 정책, 자금 흐름, 채권, 크레딧, 레버리지
• 센티먼트: 투자자 심리, VIX, 공포/탐욕 지수, 미디어 논조

━━━ 분석 대상 텍스트 ━━━
{content}

━━━ 기존 저장된 메모 (연관성·충돌 분석용) ━━━
{memo_context}

━━━ 응답 JSON 형식 ━━━
{{
  "factors": ["팩터명"],          // 1~3개, 위 6가지 중에서만 선택
  "intensity": 7,                 // 1(미미)~10(매우 강함)
  "duration": "중기",             // "단기"(≤1개월) | "중기"(1~6개월) | "장기"(>6개월)
  "summary": "한 줄 핵심 요약",
  "keywords": ["키워드1", "키워드2", "키워드3"],
  "links": [
    {{
      "target_id": "연결 대상 메모의 ID (문자열)",
      "relationship": "인과관계",  // "인과관계" 또는 "상관관계"
      "description": "왜 연결되는지 한 줄 설명",
      "strength": 0.8             // 0.0~1.0
    }}
  ],
  "conflicts": [
    {{
      "target_id": "충돌 대상 메모의 ID",
      "description": "어떤 점이 모순되는지 설명"
    }}
  ]
}}

규칙:
- links / conflicts 는 근거가 명확할 때만 포함, 없으면 빈 배열 []
- 반드시 유효한 JSON만 출력"""


# ─── 결과 정규화 ────────────────────────────────────────────────────────────────

def _normalize(result: dict) -> dict:
    valid_factors = [f for f in result.get("factors", []) if f in FACTORS]
    if not valid_factors:
        valid_factors = ["경제"]

    intensity = max(1, min(10, int(result.get("intensity", 5))))

    duration = result.get("duration", "중기")
    if duration not in DURATION_DAYS:
        duration = "중기"

    return {
        "factors":   valid_factors,
        "intensity": intensity,
        "duration":  duration,
        "summary":   str(result.get("summary", ""))[:120],
        "keywords":  [str(k) for k in result.get("keywords", [])][:6],
        "links":     result.get("links", []),
        "conflicts": result.get("conflicts", []),
    }


# ─── OpenAI 호출 ────────────────────────────────────────────────────────────────

def _call_openai(prompt: str, api_key: str, model: str) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "복잡계 투자 분석 전문가. 유효한 JSON만 응답."},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


# ─── Anthropic 호출 ─────────────────────────────────────────────────────────────

def _call_anthropic(prompt: str, api_key: str, model: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text
    # JSON 블록 추출 (```json ... ``` 감싸진 경우도 처리)
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("응답에서 JSON을 찾을 수 없습니다.")
    return json.loads(text[start:end])


# ─── 공개 API ──────────────────────────────────────────────────────────────────

def analyze_memo(
    content: str,
    existing_memos: list,
    api_key: str,
    provider: str = "OpenAI",
    model: str | None = None,
) -> dict:
    """
    메모 텍스트를 LLM으로 분석하여 구조화된 dict 반환.

    Returns:
        {factors, intensity, duration, summary, keywords, links, conflicts}
    """
    if not api_key:
        raise ValueError("API 키가 없습니다. 사이드바에서 입력하세요.")

    prompt = _build_prompt(content, existing_memos)

    default_models = {
        "OpenAI":    "gpt-4o-mini",
        "Anthropic": "claude-sonnet-4-6",
    }
    model = model or default_models.get(provider, "gpt-4o-mini")

    try:
        if provider == "OpenAI":
            raw = _call_openai(prompt, api_key, model)
        elif provider == "Anthropic":
            raw = _call_anthropic(prompt, api_key, model)
        else:
            raise ValueError(f"지원하지 않는 프로바이더: {provider}")
    except Exception as e:
        raise RuntimeError(f"LLM 호출 실패 ({provider} / {model}): {e}") from e

    return _normalize(raw)
