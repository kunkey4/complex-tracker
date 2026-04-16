# app.py — Complex Systems Investment Tracker
# 실행: streamlit run app.py

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from config import (
    DEFAULT_DATA_PATH,
    FACTOR_COLORS,
    FACTOR_ICONS,
    FACTORS,
    INTENSITY_LABELS,
)

# ─── 페이지 기본 설정 ───────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Complex Systems Investment Tracker",
    page_icon="🕸️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── 글로벌 CSS ─────────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* 전체 배경 */
.stApp { background-color: #0E1117; }

/* 카드 스타일 */
.memo-card {
    background: #1C2333;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 10px;
    border-left: 4px solid;
}
.conflict-banner {
    background: #3D1A1A;
    border: 1px solid #FF4444;
    border-radius: 8px;
    padding: 10px 14px;
    margin-bottom: 8px;
}
.factor-badge {
    display: inline-block;
    border-radius: 12px;
    padding: 2px 10px;
    font-size: 12px;
    font-weight: 600;
    margin-right: 4px;
    color: #fff;
}
/* Streamlit 기본 요소 색상 오버라이드 */
.stTextArea textarea { background-color: #1C2333; color: #EEE; }
.stSelectbox > div { background-color: #1C2333; }
</style>
""", unsafe_allow_html=True)


# ─── 데이터 IO ──────────────────────────────────────────────────────────────────

DATA_PATH = Path(DEFAULT_DATA_PATH)


def load_memos() -> list[dict]:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_PATH.exists():
        DATA_PATH.write_text(json.dumps({"memos": []}, ensure_ascii=False, indent=2), encoding="utf-8")
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return raw.get("memos", [])


def save_memos(memos: list[dict]) -> None:
    DATA_PATH.write_text(
        json.dumps({"memos": memos}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def delete_memo(memos: list[dict], memo_id: str) -> list[dict]:
    """메모 삭제 + 해당 메모를 참조하는 링크/충돌도 정리."""
    filtered = [m for m in memos if m["id"] != memo_id]
    for m in filtered:
        m["links"]     = [l for l in m.get("links", [])     if l.get("target_id") != memo_id]
        m["conflicts"] = [c for c in m.get("conflicts", []) if c.get("target_id") != memo_id]
    return filtered


# ─── 세션 초기화 ────────────────────────────────────────────────────────────────

def init_session():
    if "memos" not in st.session_state:
        st.session_state.memos = load_memos()
    if "pending_analysis" not in st.session_state:
        st.session_state.pending_analysis = None   # LLM 분석 결과 임시 보관
    if "pending_content" not in st.session_state:
        st.session_state.pending_content = ""


init_session()

# ─── 사이드바 ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🕸️ Complex Tracker")
    st.caption("복잡계 투자 분석 시스템")
    st.divider()

    # LLM 설정
    st.subheader("⚙️ LLM 설정")
    provider = st.selectbox("프로바이더", ["Gemini", "OpenAI", "Anthropic"], key="provider")

    model_options = {
        "Gemini":    ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"],
        "OpenAI":    ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"],
        "Anthropic": ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5-20251001"],
    }
    model = st.selectbox("모델", model_options[provider], key="model")

    placeholder_map = {
        "Gemini":    "AIza...",
        "OpenAI":    "sk-...",
        "Anthropic": "sk-ant-...",
    }
    api_key = st.text_input(
        "API Key",
        type="password",
        placeholder=placeholder_map.get(provider, "API Key"),
        key="api_key",
    )
    if provider == "Gemini":
        st.caption("🆓 Gemini는 무료 티어 제공 — [키 발급](https://aistudio.google.com)")

    st.divider()

    # 통계
    memos = st.session_state.memos
    total = len(memos)
    conflict_count = sum(1 for m in memos if m.get("conflicts"))
    link_count = sum(len(m.get("links", [])) for m in memos)

    st.subheader("📊 현황")
    col1, col2, col3 = st.columns(3)
    col1.metric("메모", total)
    col2.metric("연결", link_count)
    col3.metric("충돌", conflict_count, delta=f"{'⚠️' if conflict_count else '✅'}")

    st.divider()

    # 팩터별 분포
    if memos:
        st.subheader("📌 팩터 분포")
        factor_counts: dict[str, int] = {f: 0 for f in FACTORS}
        for m in memos:
            for f in m.get("factors", []):
                factor_counts[f] = factor_counts.get(f, 0) + 1
        for f, cnt in sorted(factor_counts.items(), key=lambda x: -x[1]):
            if cnt > 0:
                icon = FACTOR_ICONS.get(f, "")
                color = FACTOR_COLORS[f]
                st.markdown(
                    f'<span style="color:{color};font-weight:600">{icon} {f}</span> — {cnt}건',
                    unsafe_allow_html=True,
                )


# ─── 메인 탭 ─────────────────────────────────────────────────────────────────────

tab_input, tab_graph, tab_list = st.tabs(
    ["✏️ 새 메모 입력", "🕸️ 지식 그래프", "📋 메모 목록 & 충돌"]
)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — 새 메모 입력
# ══════════════════════════════════════════════════════════════════════════════

with tab_input:
    st.header("새 메모 / 뉴스 입력")
    st.caption("텍스트를 입력하면 LLM이 자동으로 팩터 분류, 강도·기간 분석, 기존 메모와의 연결을 생성합니다.")

    content_input = st.text_area(
        "메모 / 뉴스 내용",
        height=160,
        placeholder=(
            "예) 트럼프 행정부가 중국산 제품에 추가 관세 60% 부과 행정명령에 서명. "
            "즉시 발효 예정이며 반도체·전기차 부품 포함."
        ),
        key="content_input",
    )

    col_btn1, col_btn2, col_spacer = st.columns([1.5, 1.5, 5])

    analyze_clicked = col_btn1.button(
        "🔍 LLM 분석",
        use_container_width=True,
        type="primary",
        disabled=not content_input.strip(),
    )

    # 분석 실행
    if analyze_clicked:
        if not api_key:
            st.error("사이드바에 API Key를 먼저 입력하세요.")
        else:
            with st.spinner("LLM이 분석 중입니다…"):
                try:
                    from llm_engine import analyze_memo

                    result = analyze_memo(
                        content=content_input,
                        existing_memos=st.session_state.memos,
                        api_key=api_key,
                        provider=provider,
                        model=model,
                    )
                    st.session_state.pending_analysis = result
                    st.session_state.pending_content  = content_input
                except Exception as e:
                    st.error(f"분석 실패: {e}")

    # 분석 결과 미리보기
    analysis = st.session_state.pending_analysis
    if analysis:
        st.divider()
        st.subheader("📊 분석 결과 미리보기")

        # 기본 정보
        r1, r2, r3 = st.columns(3)
        with r1:
            st.markdown("**분류 팩터**")
            for f in analysis["factors"]:
                color = FACTOR_COLORS.get(f, "#888")
                icon  = FACTOR_ICONS.get(f, "")
                st.markdown(
                    f'<span class="factor-badge" style="background:{color}">{icon} {f}</span>',
                    unsafe_allow_html=True,
                )
        with r2:
            st.metric("강도 (Intensity)", f"{analysis['intensity']} / 10")
        with r3:
            st.metric("영향 기간 (Duration)", analysis["duration"])

        st.markdown(f"**요약:** {analysis['summary']}")
        st.markdown(f"**키워드:** `{'` `'.join(analysis['keywords'])}`")

        # 연결 관계
        if analysis["links"]:
            st.markdown("---")
            st.markdown("**🔗 감지된 연결 관계**")
            memo_map = {m["id"]: m for m in st.session_state.memos}
            for link in analysis["links"]:
                tid    = link.get("target_id", "")
                target = memo_map.get(tid)
                if not target:
                    continue
                rel    = link.get("relationship", "상관관계")
                arrow  = "→" if rel == "인과관계" else "↔"
                desc   = link.get("description", "")
                strength_pct = int(link.get("strength", 0.5) * 100)
                color  = "#FF6B6B" if rel == "인과관계" else "#4ECDC4"
                st.markdown(
                    f'<div class="memo-card" style="border-color:{color}">'
                    f'<b style="color:{color}">[{rel}] {arrow}</b> '
                    f'{target.get("summary", tid)}'
                    f'<br><small>📎 {desc} &nbsp;|&nbsp; 연결 강도: {strength_pct}%</small>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("기존 메모와의 연결 관계가 감지되지 않았습니다.")

        # 충돌 경고
        if analysis["conflicts"]:
            st.markdown("---")
            st.warning("⚠️ **충돌 데이터 감지됨!** 아래 메모와 모순이 있습니다.")
            memo_map = {m["id"]: m for m in st.session_state.memos}
            for conflict in analysis["conflicts"]:
                tid    = conflict.get("target_id", "")
                target = memo_map.get(tid)
                desc   = conflict.get("description", "")
                label  = target.get("summary", tid) if target else tid
                st.markdown(
                    f'<div class="conflict-banner">'
                    f'🚨 <b>{label}</b><br><small>{desc}</small>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # 저장 버튼
        st.divider()
        save_col, cancel_col, _ = st.columns([1.5, 1.5, 5])
        save_clicked   = save_col.button("💾 저장 확정", type="primary", use_container_width=True)
        cancel_clicked = cancel_col.button("✕ 취소",      use_container_width=True)

        if save_clicked:
            new_memo = {
                "id":        f"memo_{uuid.uuid4().hex[:8]}",
                "timestamp": datetime.now().isoformat(),
                "content":   st.session_state.pending_content,
                **analysis,
            }
            st.session_state.memos.append(new_memo)
            save_memos(st.session_state.memos)
            st.session_state.pending_analysis = None
            st.session_state.pending_content  = ""
            st.success(f"✅ 메모 저장 완료! (ID: {new_memo['id']})")
            st.rerun()

        if cancel_clicked:
            st.session_state.pending_analysis = None
            st.session_state.pending_content  = ""
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — 지식 그래프
# ══════════════════════════════════════════════════════════════════════════════

with tab_graph:
    st.header("지식 그래프 (Knowledge Graph)")

    if not st.session_state.memos:
        st.info("저장된 메모가 없습니다. '새 메모 입력' 탭에서 메모를 추가하세요.")
    else:
        g_col1, g_col2 = st.columns([3, 1])

        with g_col2:
            st.subheader("필터")
            selected_factors = []
            for f in FACTORS:
                color = FACTOR_COLORS[f]
                icon  = FACTOR_ICONS.get(f, "")
                checked = st.checkbox(
                    f"{icon} {f}",
                    value=True,
                    key=f"filter_{f}",
                )
                if checked:
                    selected_factors.append(f)

            graph_height = st.slider("그래프 높이", 400, 900, 620, step=50, key="graph_height")

            st.divider()
            st.markdown("**범례**")
            st.markdown("🔴 **인과관계** (실선 화살표)")
            st.markdown("🟦 **상관관계** (점선)")
            st.markdown("⬜ **팩터 소속** (점선 옅게)")
            st.markdown("⚠️ 빨간 테두리 = 충돌")

        with g_col1:
            if not selected_factors:
                st.warning("팩터를 최소 1개 이상 선택하세요.")
            else:
                with st.spinner("그래프 생성 중…"):
                    from graph_engine import build_graph_html

                    html = build_graph_html(
                        memos=st.session_state.memos,
                        filter_factors=selected_factors if len(selected_factors) < len(FACTORS) else None,
                        height_px=graph_height,
                    )
                components.html(html, height=graph_height + 20, scrolling=False)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — 메모 목록 & 충돌 관리
# ══════════════════════════════════════════════════════════════════════════════

with tab_list:
    st.header("메모 목록 & 충돌 관리")

    memos = st.session_state.memos

    if not memos:
        st.info("저장된 메모가 없습니다.")
    else:
        # ── 충돌 알림 배너 ──────────────────────────────────────────────────
        conflicts_exist = [m for m in memos if m.get("conflicts")]
        if conflicts_exist:
            st.error(f"⚠️ 충돌 데이터가 {len(conflicts_exist)}건 감지되었습니다! 아래에서 확인하세요.")
            for m in conflicts_exist:
                memo_map = {x["id"]: x for x in memos}
                for c in m["conflicts"]:
                    tid    = c.get("target_id", "")
                    target = memo_map.get(tid)
                    t_label = target.get("summary", tid) if target else tid
                    st.markdown(
                        f'<div class="conflict-banner">'
                        f'🚨 <b>{m.get("summary", m["id"])}</b> ↔ <b>{t_label}</b>'
                        f'<br><small>{c.get("description","")}</small>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            st.divider()

        # ── 검색 & 정렬 ─────────────────────────────────────────────────────
        l_col1, l_col2, l_col3 = st.columns([3, 2, 2])
        search_query = l_col1.text_input("🔍 검색", placeholder="키워드, 요약, 내용...")
        filter_factor = l_col2.selectbox("팩터 필터", ["전체"] + FACTORS, key="list_filter")
        sort_by = l_col3.selectbox("정렬", ["최신순", "강도 높은순", "강도 낮은순"])

        # 필터 적용
        filtered = memos
        if search_query:
            q = search_query.lower()
            filtered = [
                m for m in filtered
                if q in m.get("content", "").lower()
                or q in m.get("summary", "").lower()
                or any(q in kw.lower() for kw in m.get("keywords", []))
            ]
        if filter_factor != "전체":
            filtered = [m for m in filtered if filter_factor in m.get("factors", [])]

        # 정렬 적용
        if sort_by == "최신순":
            filtered = sorted(filtered, key=lambda x: x.get("timestamp", ""), reverse=True)
        elif sort_by == "강도 높은순":
            filtered = sorted(filtered, key=lambda x: x.get("intensity", 0), reverse=True)
        else:
            filtered = sorted(filtered, key=lambda x: x.get("intensity", 0))

        st.caption(f"총 {len(memos)}건 중 {len(filtered)}건 표시")
        st.divider()

        # ── 메모 카드 목록 ───────────────────────────────────────────────────
        memo_map = {m["id"]: m for m in memos}

        for memo in filtered:
            mid       = memo["id"]
            primary   = memo["factors"][0] if memo["factors"] else "경제"
            color     = FACTOR_COLORS.get(primary, "#888")
            intensity = memo.get("intensity", 5)
            ts        = memo.get("timestamp", "")[:10]
            summary   = memo.get("summary", memo["content"][:50])
            has_conflict = bool(memo.get("conflicts"))

            # 카드 헤더
            border_color = "#FF4444" if has_conflict else color
            badges_html = "".join(
                f'<span class="factor-badge" style="background:{FACTOR_COLORS.get(f,"#888")}">'
                f'{FACTOR_ICONS.get(f,"")} {f}</span>'
                for f in memo["factors"]
            )

            st.markdown(
                f'<div class="memo-card" style="border-color:{border_color}">'
                f'{badges_html}'
                f'{"&nbsp; ⚠️ 충돌" if has_conflict else ""}'
                f'<br><b style="font-size:15px">{summary}</b>'
                f'<br><small style="color:#AAA">🆔 {mid} &nbsp;|&nbsp; ⚡ {intensity}/10'
                f' &nbsp;|&nbsp; ⏱ {memo.get("duration","-")}'
                f' &nbsp;|&nbsp; 📅 {ts}</small>'
                f'</div>',
                unsafe_allow_html=True,
            )

            with st.expander("상세 보기", expanded=False):
                st.markdown(f"**내용:**\n{memo['content']}")

                if memo.get("keywords"):
                    st.markdown(f"**키워드:** `{'` `'.join(memo['keywords'])}`")

                if memo.get("links"):
                    st.markdown("**연결 관계:**")
                    for link in memo["links"]:
                        t = memo_map.get(link.get("target_id",""), {})
                        rel   = link.get("relationship","")
                        desc  = link.get("description","")
                        arrow = "→" if rel == "인과관계" else "↔"
                        lcolor = "#FF6B6B" if rel == "인과관계" else "#4ECDC4"
                        t_label = t.get("summary", link.get("target_id","?"))
                        st.markdown(
                            f'<span style="color:{lcolor}"><b>[{rel}] {arrow}</b></span> '
                            f'{t_label}: <i>{desc}</i>',
                            unsafe_allow_html=True,
                        )

                if memo.get("conflicts"):
                    st.markdown("**⚠️ 충돌:**")
                    for c in memo["conflicts"]:
                        t = memo_map.get(c.get("target_id",""), {})
                        st.error(f"{t.get('summary', c.get('target_id','?'))}: {c.get('description','')}")

                # 삭제 버튼
                if st.button(f"🗑️ 삭제", key=f"del_{mid}", type="secondary"):
                    st.session_state.memos = delete_memo(st.session_state.memos, mid)
                    save_memos(st.session_state.memos)
                    st.success("삭제 완료!")
                    st.rerun()

        # ── JSON 내보내기 ────────────────────────────────────────────────────
        st.divider()
        st.download_button(
            label="⬇️ 전체 데이터 JSON 다운로드",
            data=json.dumps({"memos": memos}, ensure_ascii=False, indent=2),
            file_name=f"complex_tracker_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
        )
