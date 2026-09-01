"""주식 분석 대시보드 - "주요 종목현황"이 메인인 Streamlit 앱.

실행: streamlit run app.py   (프로젝트 루트에서)

지표 수집 로직은 src/indicators.py · src/screener.py 한 곳에서만 관리한다
(엑셀 리포트용으로 따로 두던 report_builder.py/main.py는 제거함 - 이 앱이 그 자리를 대신함).
종목별 재무·기술적 지표(ROE/RSI/MACD 등)는 src/technical.py 계산 로직을 그대로 재사용한다.
"""
from __future__ import annotations

import html
from typing import Any

import streamlit as st

from src import config, indicators, screener

st.set_page_config(page_title="주식 분석 대시보드", page_icon="📈", layout="wide")

# 다크 + 굵은 타이포 + 레드 악센트 톤의 대시보드 테마.
# 색상은 이 프로젝트 전용으로 고른 값이며, 특정 브랜드의 색상표·로고·문구를 그대로
# 옮기지 않는다 - 참고한 건 "어두운 배경 + 굵은 수치 + 카드형 레이아웃"이라는 형식뿐이다.
_CSS = """
<style>
:root {
  --bg: #0e0e10;
  --surface: #18181b;
  --line: #2a2a2f;
  --ink: #f5f5f2;
  --ink-muted: #9a9a9f;
  --accent: #d63447;
}

[data-testid="stAppViewContainer"], [data-testid="stHeader"] {
  background-color: var(--bg);
}

h1, h2, h3 {
  font-weight: 800 !important;
  letter-spacing: -0.02em;
  color: var(--ink) !important;
}

[data-testid="stCaptionContainer"] { color: var(--ink-muted) !important; }

[data-testid="stMetric"] {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 18px 20px 14px;
}
[data-testid="stMetricLabel"] {
  color: var(--ink-muted) !important;
  text-transform: uppercase;
  font-size: 0.72rem;
  letter-spacing: 0.09em;
  font-weight: 600;
}
[data-testid="stMetricValue"] {
  font-weight: 800 !important;
  font-size: 1.85rem !important;
  letter-spacing: -0.02em;
  color: var(--ink) !important;
}

.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--line); }
.stTabs [data-baseweb="tab"] { color: var(--ink-muted); font-weight: 600; }
.stTabs [aria-selected="true"] { color: var(--accent) !important; }
.stTabs [data-baseweb="tab-highlight"] { background-color: var(--accent) !important; }

[data-testid="stDataFrame"], [data-testid="stExpander"] {
  border: 1px solid var(--line);
  border-radius: 10px;
}

.stButton > button {
  background-color: var(--accent);
  color: #fff;
  border: none;
  font-weight: 700;
  border-radius: 8px;
}
.stButton > button:hover { background-color: #b8283a; color: #fff; }

/* 클릭하면 원본 출처로 이동하는 지표 카드/표 행 (카드/행 전체가 <a> 링크) */
a.metric-card, a.metric-card:link, a.metric-card:visited, a.metric-card:hover {
  display: block;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 18px 20px 14px;
  text-decoration: none !important;
  color: inherit !important;
}
.metric-card.linkable:hover { border-color: var(--accent); }
.metric-card.linkable::after {
  content: "↗ 출처로 이동";
  display: block;
  font-size: 0.68rem;
  color: var(--ink-muted);
  margin-top: 8px;
  opacity: 0;
  transition: opacity 0.15s ease;
}
.metric-card.linkable:hover::after { opacity: 1; color: var(--accent); }
.metric-label {
  display: block;
  color: var(--ink-muted);
  text-transform: uppercase;
  font-size: 0.72rem;
  letter-spacing: 0.09em;
  font-weight: 600;
}
.metric-value {
  display: block;
  font-weight: 800;
  font-size: 1.85rem;
  letter-spacing: -0.02em;
  color: var(--ink);
  margin-top: 4px;
}

.ind-table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; }
table.ind-table { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
table.ind-table th {
  text-align: left;
  background: #1f1f23;
  color: var(--ink-muted);
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 10px 14px;
  border-bottom: 1px solid var(--line);
}
table.ind-table td { padding: 0; border-bottom: 1px solid var(--line); color: var(--ink); }
table.ind-table td > .cell-plain { display: block; padding: 10px 14px; }
a.cell-link, a.cell-link:link, a.cell-link:visited, a.cell-link:hover {
  display: block;
  padding: 10px 14px;
  color: inherit !important;
  text-decoration: none !important;
}
table.ind-table tr:last-child td { border-bottom: none; }
table.ind-table tr.linkable:hover td { background: #202024; }
table.ind-table tr.linkable:hover .cell-link { color: var(--accent); }
table.ind-table tr.linkable td:first-child > .cell-link::after { content: " ↗"; opacity: 0.6; }
table.ind-table td.fail-reason > .cell-plain { color: #f0a5ad; font-size: 0.85rem; }
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)

_STATUS_LABEL = {"ok": "정상", "manual": "수동 확인 필요", "error": "수집 실패"}


def _esc(v: Any) -> str:
    return html.escape(str(v)) if v is not None else ""


def _metric_card(label: str, value: str, url: str | None = None, tooltip: str | None = None) -> None:
    """클릭하면 원본 출처 홈페이지로 새 탭에서 이동하는 카드형 지표. url이 없으면 그냥 카드만 표시.

    주의: st.markdown(unsafe_allow_html=True)의 새니타이저가 ondblclick 같은 인라인 이벤트
    핸들러 속성을 제거하고(직접 확인함), <a> 안에 블록 레벨 <div>를 넣으면 <a> 태그 자체를
    쪼개버리는 것도 확인해서(마찬가지로 직접 확인함) - 그래서 더블클릭 JS 트리거 대신
    카드 전체를 <a href target="_blank"> 링크로 감싸고, 안쪽 라벨/값은 <div> 대신
    <span>(CSS로 block 처리)을 써서 새니타이저가 <a>를 쪼개지 않게 한다.
    """
    tag = "a" if url else "div"
    cls = "metric-card linkable" if url else "metric-card"
    href = f' href="{_esc(url)}" target="_blank" rel="noopener"' if url else ""
    title = _esc(tooltip) if tooltip else ("원본 데이터 출처로 이동" if url else "")
    st.markdown(
        f'<{tag} class="{cls}"{href} title="{title}">'
        f'<span class="metric-label">{_esc(label)}</span>'
        f'<span class="metric-value">{_esc(value)}</span>'
        f'</{tag}>',
        unsafe_allow_html=True,
    )

# 지표 설명 (주석/툴팁 + 하단 범례용) - "공식"과 "해석(높을수록/낮을수록 좋은지)"을 한 곳에서 관리
_METRIC_INFO: dict[str, dict[str, str]] = {
    "PER": {
        "공식": "현재가 ÷ EPS(주당순이익)",
        "해석": "낮을수록 이익 대비 저평가로 봄. 다만 업종 평균과 비교해야 의미가 있고, 성장주는 원래 높게 거래되는 편이라 절대 기준은 아님",
    },
    "EPS": {
        "공식": "당기순이익 ÷ 발행주식수",
        "해석": "높을수록 좋음 - 주식 1주가 벌어들이는 이익이 크다는 뜻",
    },
    "ROE": {
        "공식": "당기순이익 ÷ 자기자본 × 100",
        "해석": "높을수록 좋음 - 통상 15% 이상이면 자본을 효율적으로 굴리는 우량 기업으로 봄",
    },
    "시가총액": {
        "공식": "발행주식수 × 현재가 (원화 종목은 원/달러 환율로 USD 환산)",
        "해석": "기업 규모를 보여주는 지표 - 높낮이 자체가 좋고 나쁨을 뜻하진 않음",
    },
    "전고점대비": {
        "공식": "(현재가 − 상장 이후 역대 최고가) ÷ 최고가 × 100",
        "해석": "0에 가까울수록 전고점 근접. 많이 하락해 있으면 저가매수 기회일 수도, 추세가 꺾인 신호일 수도 있어 맥락 확인이 필요",
    },
    "RSI(14)": {
        "공식": "100 − 100 ÷ (1 + 평균상승폭÷평균하락폭), 14일 기준",
        "해석": "70 이상 과매수(단기 조정 가능성), 30 이하 과매도(반등 가능성) - 높낮이 자체가 좋고 나쁨은 아님",
    },
    "MACD": {
        "공식": "12일 EMA − 26일 EMA (그 값의 9일 EMA인 시그널선과 비교)",
        "해석": "MACD가 시그널선 위(히스토그램 양수)면 매수신호, 아래(음수)면 매도신호",
    },
    "이평배열": {
        "공식": "20일 이동평균선과 60일 이동평균선의 위치 관계",
        "해석": "정배열(20일선>60일선)=상승추세, 역배열=하락추세, 골든크로스=역배열→정배열 전환(매수신호), 데드크로스=반대(매도신호)",
    },
}


def _help(name: str) -> str:
    info = _METRIC_INFO[name]
    return f"공식: {info['공식']}\n해석: {info['해석']}"


# ---------------------------------------------------------------- 캐시된 조회 ----
@st.cache_data(ttl=300, show_spinner="코스피·코스닥 지표 조회 중...")
def _load_kr_index() -> list[dict[str, Any]]:
    return indicators.collect_kr_index()


@st.cache_data(ttl=300, show_spinner="반도체 지수(SOX)·환율 조회 중...")
def _load_semi() -> list[dict[str, Any]]:
    return indicators.collect_semi()


@st.cache_data(ttl=600, show_spinner="빅테크 Top20 스캔 중... (35개 종목 재무+기술적지표 조회라 1분 이상 걸릴 수 있습니다)")
def _load_top20() -> dict[str, Any]:
    return screener.run()


@st.cache_data(ttl=600, show_spinner="전략자산 목록 조회 중...")
def _load_strategic_assets() -> dict[str, Any]:
    return screener.fetch_watchlist([a["ticker"] for a in config.STRATEGIC_ASSETS])


@st.cache_data(ttl=600, show_spinner="전체 섹터별 Top3 스캔 중... (11개 섹터, 50여개 종목 조회)")
def _load_sector_leaders() -> dict[str, Any]:
    return screener.fetch_theme_leaders(config.SECTOR_CANDIDATES, config.SECTOR_TOP_N)


@st.cache_data(ttl=300, show_spinner="美 매크로 지표 조회 중...")
def _load_macro() -> list[dict[str, Any]]:
    return indicators.collect_macro()


@st.cache_data(ttl=300, show_spinner="글로벌 유동성 지표 조회 중...")
def _load_liquidity() -> list[dict[str, Any]]:
    return indicators.collect_liquidity()


@st.cache_data(ttl=300, show_spinner="시장 심리 지표 조회 중...")
def _load_sentiment() -> list[dict[str, Any]]:
    return indicators.collect_sentiment()


def _clear_all_cache() -> None:
    for fn in (_load_kr_index, _load_semi, _load_top20, _load_strategic_assets,
               _load_sector_leaders, _load_macro, _load_liquidity, _load_sentiment):
        fn.clear()


# --------------------------------------------------------------- 렌더 헬퍼 ----
def _find(rows: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((r for r in rows if r["name"] == name), None)


def _fmt(v: Any, nd: int = 2) -> str:
    return f"{v:,.{nd}f}" if isinstance(v, (int, float)) else "N/A"


def _render_indicator_table(rows: list[dict[str, Any]]) -> None:
    """지표 표. url이 있는 행은 클릭하면 실제 데이터 출처 홈페이지가 새 탭으로 열린다
    (표 셀 전체를 <a> 링크로 감쌈 - st.markdown이 ondblclick 같은 인라인 이벤트 핸들러를
    걸러내는 걸 확인해서 더블클릭 대신 클릭형 링크로 구현했다).
    실패한 행은 "진단" 칸에 코드 문제/네트워크 일시 장애/데이터 없음 여부를 구분해서 보여준다.
    """
    if not rows:
        st.info("표시할 지표가 없습니다.")
        return

    has_fail_reason = any(r.get("fail_reason") for r in rows)
    headers = ["지표", "값", "단위", "기준일", "상태", "비고"]
    if has_fail_reason:
        headers.append("진단")

    parts = ['<div class="ind-table-wrap"><table class="ind-table"><thead><tr>']
    parts += [f"<th>{h}</th>" for h in headers]
    parts.append("</tr></thead><tbody>")

    for r in rows:
        value = r.get("value")
        value_str = f"{value:,.4f}" if isinstance(value, (int, float)) else (value or "-")
        url = r.get("url")

        def cell(content: str) -> str:
            if url:
                return f'<td><a class="cell-link" href="{_esc(url)}" target="_blank" rel="noopener">{content}</a></td>'
            return f'<td><span class="cell-plain">{content}</span></td>'

        cells_html = (
            cell(_esc(r["name"])) + cell(_esc(value_str)) + cell(_esc(r.get("unit", "")))
            + cell(_esc(r.get("asof") or "-")) + cell(_esc(_STATUS_LABEL.get(r["status"], r["status"])))
            + cell(_esc(r.get("note") or ""))
        )
        row_html = f'<tr class="{"linkable" if url else ""}">' + cells_html
        if has_fail_reason:
            row_html += f'<td class="fail-reason"><span class="cell-plain">{_esc(r.get("fail_reason") or "")}</span></td>'
        row_html += "</tr>"
        parts.append(row_html)

    parts.append("</tbody></table></div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def _render_stock_card(entry: dict[str, Any] | None, name: str, ticker: str) -> None:
    st.markdown(f"**{name}** `{ticker}`")
    if entry is None:
        st.error("조회 실패 (Top20 스캔 결과에서 찾지 못함 - 새로고침 후 다시 확인해주세요)")
        return

    t = entry.get("technical") or {}
    st.metric("현재가", f"{_fmt(entry.get('price'), 0)} {entry.get('currency') or ''}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("PER", _fmt(entry.get("per")), help=_help("PER"))
    m2.metric("EPS", _fmt(entry.get("eps"), 0), help=_help("EPS"))
    m3.metric("ROE", f"{_fmt(entry.get('roe_pct'), 1)}%", help=_help("ROE"))
    m4.metric("시가총액", f"{_fmt(entry.get('market_cap_usd_bil'), 1)}억$", help=_help("시가총액"))

    m5, m6, m7 = st.columns(3)
    m5.metric("전고점대비", f"{_fmt(entry.get('drawdown_pct'), 1)}%", help=_help("전고점대비"))
    m6.metric("RSI(14)", f"{_fmt(t.get('rsi14'), 1)} ({t.get('rsi_regime', 'N/A')})", help=_help("RSI(14)"))
    m7.metric("MACD", t.get("macd_regime", "N/A"), help=_help("MACD"))

    st.caption(f"이평배열: {t.get('cross_20_60', 'N/A')} (MA20 {_fmt(t.get('ma20'))} / MA60 {_fmt(t.get('ma60'))} / "
               f"MA120 {_fmt(t.get('ma120'))} / MA200 {_fmt(t.get('ma200'))})")


# ------------------------------------------------------------------- 헤더 ----
col_title, col_refresh = st.columns([5, 1])
with col_title:
    st.title("📈 주식 분석 대시보드")
    st.caption("무료 API(FRED·Yahoo·KRX) 기반 자동 수집 · 5~10분 캐시")
with col_refresh:
    st.write("")
    if st.button("🔄 지금 새로고침", use_container_width=True):
        _clear_all_cache()
        st.rerun()

kr_index_rows = _load_kr_index()
semi_rows = _load_semi()

metric_specs = [
    _find(kr_index_rows, "코스피"),
    _find(kr_index_rows, "코스닥"),
    _find(semi_rows, "필라델피아 반도체지수(SOX)"),
    _find(semi_rows, "원/달러 환율"),
]
metric_cols = st.columns(4)
for col, m in zip(metric_cols, metric_specs):
    with col:
        if m is None:
            _metric_card("N/A", "-")
        elif m["status"] == "ok":
            _metric_card(m["name"], f"{m['value']:,.2f} {m['unit']}", url=m.get("url"),
                         tooltip=f"기준일 {m['asof']} · 더블클릭: 원본 출처로 이동")
        else:
            _metric_card(m["name"], "조회 실패", url=m.get("url"))
            st.caption(m.get("note") or "")

st.divider()

# -------------------------------------------------------------------- 탭 ----
tab_main, tab_macro, tab_liquidity, tab_sentiment, tab_manual = st.tabs(
    ["🏠 주요 종목현황", "🌎 매크로", "💧 유동성", "😨 심리·수급", "📋 수동 확인"]
)

with tab_main:
    scan = _load_top20()
    pinned = scan.get("pinned", {})

    with st.expander("📖 지표 설명 (공식·해석) — PER/EPS/ROE/RSI 등이 헷갈리면 여기를 펼쳐보세요"):
        st.dataframe(
            [{"지표": name, "공식": info["공식"], "해석": info["해석"]} for name, info in _METRIC_INFO.items()],
            use_container_width=True, hide_index=True,
        )

    st.subheader("삼성전자 · SK하이닉스")
    stock_cols = st.columns(len(config.SEMI_STOCKS) or 1)
    for col, stock in zip(stock_cols, config.SEMI_STOCKS):
        with col:
            _render_stock_card(pinned.get(stock["ticker"]), stock["name"], stock["ticker"])

    st.subheader(f"빅테크 Top{config.TOP_N} (USD 시가총액 기준)")
    krw_rate = scan.get("krw_per_usd")
    if krw_rate:
        st.caption(f"원/달러 환율(스캔 시점): {krw_rate:,.2f} — 005930.KS·000660.KS는 이 환율로 USD 환산 후 랭킹")
    else:
        st.warning("환율 조회 실패 - KRW 표시 종목(삼성전자·SK하이닉스)은 이번 랭킹에서 제외됨")

    ranked = scan.get("ranked", [])
    if ranked:
        table = []
        for i, r in enumerate(ranked, start=1):
            t = r.get("technical") or {}
            table.append({
                "순위": i, "티커": r["ticker"], "종목명": r.get("name", ""),
                "시가총액($B)": r.get("market_cap_usd_bil"), "현재가": r.get("price"),
                "통화": r.get("currency"), "PER": r.get("per"), "EPS": r.get("eps"),
                "ROE(%)": round(r["roe_pct"], 1) if r.get("roe_pct") is not None else None,
                "전고점대비(%)": round(r["drawdown_pct"], 1) if r.get("drawdown_pct") is not None else None,
                "이평배열": t.get("cross_20_60", "N/A"),
                "RSI(14)": round(t["rsi14"], 1) if t.get("rsi14") is not None else None,
                "RSI상태": t.get("rsi_regime", "N/A"),
                "MACD상태": t.get("macd_regime", "N/A"),
            })
        st.dataframe(
            table, use_container_width=True, hide_index=True,
            column_config={
                "PER": st.column_config.NumberColumn(help=_help("PER")),
                "EPS": st.column_config.NumberColumn(help=_help("EPS")),
                "ROE(%)": st.column_config.NumberColumn(help=_help("ROE")),
                "시가총액($B)": st.column_config.NumberColumn(help=_help("시가총액")),
                "전고점대비(%)": st.column_config.NumberColumn(help=_help("전고점대비")),
                "RSI(14)": st.column_config.NumberColumn(help=_help("RSI(14)")),
                "MACD상태": st.column_config.TextColumn(help=_help("MACD")),
                "이평배열": st.column_config.TextColumn(help=_help("이평배열")),
            },
        )
    else:
        st.info("Top20 스캔 결과가 없습니다.")

    failed = scan.get("failed", [])
    if failed:
        with st.expander(f"조회 실패 종목 {len(failed)}개"):
            for f in failed:
                st.write(f"- {f['ticker']}: {f.get('error', '')}")

    history_failed = scan.get("history_failed", [])
    if history_failed:
        with st.expander(f"⚠️ 기술적지표 조회 실패 {len(history_failed)}개 (전고점대비·RSI·MACD가 N/A로 표시됨)"):
            for hf in history_failed:
                st.write(f"- {hf['ticker']}: {hf['reason']}")

    st.subheader("전체 시장 섹터별 Top3 (핀비즈 히트맵 스타일)")
    st.caption("기술·헬스케어·금융 등 시장 전체 11개 섹터를 대표 대형주 후보군 기준으로 훑어봅니다. 아래 전략자산 List와 종목이 겹쳐도 상관없습니다.")
    sector_scan = _load_sector_leaders()
    by_sector = sector_scan.get("by_theme", {})
    sector_table = []
    for sector, entries in by_sector.items():
        for rank, r in enumerate(entries, start=1):
            t = r.get("technical") or {}
            sector_table.append({
                "섹터": sector, "순위": rank, "티커": r["ticker"], "종목명": r.get("name", ""),
                "시가총액($B)": r.get("market_cap_usd_bil"), "현재가": r.get("price"),
                "통화": r.get("currency"), "PER": r.get("per"), "EPS": r.get("eps"),
                "ROE(%)": round(r["roe_pct"], 1) if r.get("roe_pct") is not None else None,
                "전고점대비(%)": round(r["drawdown_pct"], 1) if r.get("drawdown_pct") is not None else None,
                "RSI(14)": round(t["rsi14"], 1) if t.get("rsi14") is not None else None,
                "RSI상태": t.get("rsi_regime", "N/A"),
                "MACD상태": t.get("macd_regime", "N/A"),
            })
    if sector_table:
        st.dataframe(
            sector_table, use_container_width=True, hide_index=True,
            column_config={
                "PER": st.column_config.NumberColumn(help=_help("PER")),
                "EPS": st.column_config.NumberColumn(help=_help("EPS")),
                "ROE(%)": st.column_config.NumberColumn(help=_help("ROE")),
                "시가총액($B)": st.column_config.NumberColumn(help=_help("시가총액")),
                "전고점대비(%)": st.column_config.NumberColumn(help=_help("전고점대비")),
                "RSI(14)": st.column_config.NumberColumn(help=_help("RSI(14)")),
                "MACD상태": st.column_config.TextColumn(help=_help("MACD")),
            },
        )
    else:
        st.info("섹터별 Top3 결과가 없습니다.")
    sector_failed = sector_scan.get("failed", [])
    if sector_failed:
        with st.expander(f"섹터 후보 조회 실패 {len(sector_failed)}개"):
            for f in sector_failed:
                st.write(f"- {f['ticker']}: {f.get('error', '')}")

    st.subheader("전략자산 (정부 지분투자 List)")
    st.caption("시가총액 랭킹이 아니라 정부 지분 참여 발표 순서 그대로 고정 표시합니다.")
    strat = _load_strategic_assets()
    strat_entries = strat.get("entries", {})
    strat_table = []
    for a in config.STRATEGIC_ASSETS:
        e = strat_entries.get(a["ticker"])
        t = (e.get("technical") if e else None) or {}
        strat_table.append({
            "티커": a["ticker"], "종목명": a["name"], "테마": a["theme"], "정부 지분": a["stake_note"],
            "현재가": e.get("price") if e else None,
            "통화": e.get("currency") if e else None,
            "시가총액($B)": round(e["market_cap"] / 1e9, 2) if e and e.get("market_cap") else None,
            "PER": e.get("per") if e else None,
            "EPS": e.get("eps") if e else None,
            "ROE(%)": round(e["roe_pct"], 1) if e and e.get("roe_pct") is not None else None,
            "전고점대비(%)": round(e["drawdown_pct"], 1) if e and e.get("drawdown_pct") is not None else None,
            "RSI(14)": round(t["rsi14"], 1) if t.get("rsi14") is not None else None,
            "RSI상태": t.get("rsi_regime", "N/A"),
            "MACD상태": t.get("macd_regime", "N/A"),
        })
    st.dataframe(
        strat_table, use_container_width=True, hide_index=True,
        column_config={
            "PER": st.column_config.NumberColumn(help=_help("PER")),
            "EPS": st.column_config.NumberColumn(help=_help("EPS")),
            "ROE(%)": st.column_config.NumberColumn(help=_help("ROE")),
            "전고점대비(%)": st.column_config.NumberColumn(help=_help("전고점대비")),
            "RSI(14)": st.column_config.NumberColumn(help=_help("RSI(14)")),
            "MACD상태": st.column_config.TextColumn(help=_help("MACD")),
        },
    )
    strat_failed = strat.get("failed", [])
    if strat_failed:
        with st.expander(f"전략자산 조회 실패 {len(strat_failed)}개"):
            for f in strat_failed:
                st.write(f"- {f['ticker']}: {f.get('error', '')}")

    st.subheader("코스피·코스닥 상세")
    st.caption("PBR·외국인 순매수는 KRX 무료 계정(KRX_ID/KRX_PW 환경변수) 설정 시에만 자동 수집됩니다.")
    _render_indicator_table(kr_index_rows)

with tab_macro:
    _render_indicator_table(_load_macro())

with tab_liquidity:
    _render_indicator_table(_load_liquidity())

with tab_sentiment:
    _render_indicator_table(_load_sentiment())

with tab_manual:
    st.caption("무료·안정적 API가 없어 자동 수집하지 않고 참고용으로만 표시하는 항목입니다.")
    _render_indicator_table(indicators.collect_manual())
