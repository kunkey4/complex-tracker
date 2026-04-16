# graph_engine.py — Pyvis 지식 그래프 빌더

from pyvis.network import Network
from config import FACTOR_COLORS, FACTORS


# ─── 팩터 허브 노드 추가 ────────────────────────────────────────────────────────

def _add_factor_nodes(net: Network, active_factors: list[str]) -> None:
    for factor in active_factors:
        color = FACTOR_COLORS[factor]
        net.add_node(
            f"F::{factor}",
            label=factor,
            title=f"<b>[허브] {factor}</b>",
            color={"background": color, "border": "#FFFFFF"},
            size=45,
            shape="ellipse",
            font={"size": 16, "color": "#FFFFFF", "bold": True},
            borderWidth=3,
            group=factor,
        )


# ─── 메모 노드 추가 ─────────────────────────────────────────────────────────────

def _add_memo_nodes(net: Network, memos: list, visible_ids: set) -> None:
    for memo in memos:
        mid = memo["id"]
        if mid not in visible_ids:
            continue

        primary = memo["factors"][0] if memo["factors"] else "경제"
        color    = FACTOR_COLORS.get(primary, "#888888")
        intensity = memo.get("intensity", 5)
        size = 12 + intensity * 1.8

        factors_str  = ", ".join(memo["factors"])
        duration_str = memo.get("duration", "-")
        ts           = memo.get("timestamp", "")[:10]
        summary      = memo.get("summary", memo["content"][:40])
        bars_filled  = "■" * intensity + "□" * (10 - intensity)

        conflict_warn = ""
        if memo.get("conflicts"):
            conflict_warn = "<br>⚠️ <b style='color:#FF6B6B'>충돌 데이터 있음</b>"

        tooltip = f"""<div style='max-width:280px;font-family:sans-serif;font-size:13px'>
<b>{summary}</b>
<hr style='margin:4px 0'>
📌 팩터: {factors_str}<br>
⚡ 강도: {bars_filled} ({intensity}/10)<br>
⏱ 기간: {duration_str}<br>
📅 날짜: {ts}
{conflict_warn}
<hr style='margin:4px 0'>
<i style='font-size:11px'>{memo['content'][:120]}{"..." if len(memo["content"]) > 120 else ""}</i>
</div>"""

        border_color = "#FF4444" if memo.get("conflicts") else "#FFFFFF"

        net.add_node(
            mid,
            label=summary[:22],
            title=tooltip,
            color={"background": color, "border": border_color},
            size=size,
            shape="dot",
            font={"size": 10, "color": "#EEEEEE"},
            borderWidth=2 if memo.get("conflicts") else 1,
            group=primary,
        )


# ─── 팩터-메모 연결선 ────────────────────────────────────────────────────────────

def _add_factor_edges(net: Network, memos: list, visible_ids: set) -> None:
    for memo in memos:
        mid = memo["id"]
        if mid not in visible_ids:
            continue
        for factor in memo["factors"]:
            fnode = f"F::{factor}"
            net.add_edge(
                fnode, mid,
                color={"color": FACTOR_COLORS.get(factor, "#888"), "opacity": 0.25},
                width=1,
                dashes=[5, 5],
                arrows="",
                title=f"{factor} 팩터 소속",
            )


# ─── 메모 간 관계 연결선 ────────────────────────────────────────────────────────

def _add_link_edges(net: Network, memos: list, visible_ids: set) -> None:
    added_edges: set[tuple] = set()
    memo_map = {m["id"]: m for m in memos}

    for memo in memos:
        src = memo["id"]
        if src not in visible_ids:
            continue

        for link in memo.get("links", []):
            tgt = link.get("target_id", "")
            if tgt not in visible_ids or tgt not in memo_map:
                continue

            edge_key = tuple(sorted([src, tgt]))
            if edge_key in added_edges:
                continue
            added_edges.add(edge_key)

            is_causal   = link.get("relationship") == "인과관계"
            edge_color  = "#FF6B6B" if is_causal else "#4ECDC4"
            strength    = float(link.get("strength", 0.5))
            arrows_cfg  = "to" if is_causal else ""
            label_text  = "인과" if is_causal else "상관"

            net.add_edge(
                src, tgt,
                title=link.get("description", ""),
                color={"color": edge_color, "opacity": 0.8},
                width=1 + strength * 4,
                arrows=arrows_cfg,
                dashes=not is_causal,
                label=label_text,
                font={"size": 9, "color": edge_color},
            )


# ─── 공개 API ──────────────────────────────────────────────────────────────────

PHYSICS_OPTIONS = """{
  "nodes": {"borderWidth": 2, "shadow": {"enabled": true, "size": 6}},
  "edges": {
    "shadow": {"enabled": true},
    "smooth": {"type": "dynamic"}
  },
  "physics": {
    "barnesHut": {
      "gravitationalConstant": -28000,
      "centralGravity": 0.3,
      "springLength": 220,
      "springConstant": 0.04,
      "damping": 0.09
    },
    "maxVelocity": 50,
    "minVelocity": 0.75
  },
  "interaction": {
    "hover": true,
    "tooltipDelay": 150,
    "navigationButtons": true,
    "keyboard": true
  }
}"""


def build_graph_html(
    memos: list,
    filter_factors: list[str] | None = None,
    height_px: int = 620,
) -> str:
    """
    Pyvis HTML 문자열을 반환합니다.
    filter_factors=None 이면 전체 팩터를 표시합니다.
    """
    active_factors = filter_factors if filter_factors else FACTORS

    # 표시할 메모 ID 집합 결정
    visible_ids: set[str] = set()
    for memo in memos:
        if any(f in active_factors for f in memo.get("factors", [])):
            visible_ids.add(memo["id"])

    net = Network(
        height=f"{height_px}px",
        width="100%",
        bgcolor="#0E1117",
        font_color="#FFFFFF",
        directed=True,
    )
    net.set_options(PHYSICS_OPTIONS)

    _add_factor_nodes(net, active_factors)
    _add_memo_nodes(net, memos, visible_ids)
    _add_factor_edges(net, memos, visible_ids)
    _add_link_edges(net, memos, visible_ids)

    return net.generate_html(notebook=False)
