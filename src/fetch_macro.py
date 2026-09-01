"""매크로 지표 8종 수집. 지표별로 독립 실패하도록 설계 —
하나의 소스(FRED 등)가 막혀도 나머지 지표는 정상 반환한다.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fred_client import get_series, latest, yoy_pct
from yahoo_client import YahooClient

# 이 리포트(1번 시트)가 요구하는 8개 지표를 직접 정의한다 (config.py의
# MACRO_INDICATORS를 참조하지 않음 - 그쪽은 이 프로젝트에서 동시에 진행 중인
# 다른 작업이 매크로/유동성/심리 등 더 세분화된 용도로 계속 바꾸고 있어,
# 여기서 가져다 쓰면 사용자가 원래 요청한 8개 지표 구성이 예고 없이 깨질 수 있다).
MACRO_INDICATORS: list[dict] = [
    {"name": "M2 통화량(미국)", "kind": "fred", "id": "M2SL", "unit": "십억달러"},
    {"name": "나스닥종합지수", "kind": "yahoo", "id": "^IXIC", "unit": "pt"},
    {"name": "코스피", "kind": "yahoo", "id": "^KS11", "unit": "pt"},
    {"name": "코스닥", "kind": "yahoo", "id": "^KQ11", "unit": "pt"},
    {"name": "VIX(변동성지수)", "kind": "yahoo", "id": "^VIX", "unit": "pt"},
    {"name": "달러인덱스(DXY)", "kind": "yahoo", "id": "DX-Y.NYB", "unit": "pt"},
    {"name": "美 10년물 국채금리", "kind": "yahoo", "id": "^TNX", "unit": "%"},
    {"name": "美 3개월 국채금리(단기금리)", "kind": "yahoo", "id": "^IRX", "unit": "%"},
    {"name": "美 CPI(전년동월비, YoY)", "kind": "fred", "id": "CPIAUCSL", "unit": "%", "yoy": True},
    {"name": "WTI 유가", "kind": "yahoo", "id": "CL=F", "unit": "$/배럴"},
]


def _yahoo_series(yc: YahooClient, ticker: str) -> tuple[list[tuple[date, float]], float, date]:
    chart = yc.get_chart(ticker, range_="5y", interval="1wk")
    ts = chart["timestamp"]
    closes = chart["indicators"]["quote"][0]["close"]
    hist = [
        (date.fromtimestamp(t), c) for t, c in zip(ts, closes) if c is not None
    ]
    if not hist:
        raise RuntimeError(f"{ticker} 히스토리 없음")
    last_date, last_val = hist[-1]
    return hist, last_val, last_date


def fetch_all_macro() -> list[dict[str, Any]]:
    """MACRO_INDICATORS 각각에 대해 {name, unit, latest_value, latest_date,
    history: [(date, value), ...], error: str|None} 딕셔너리 리스트 반환.
    """
    yc = YahooClient()
    results: list[dict[str, Any]] = []

    for ind in MACRO_INDICATORS:
        entry: dict[str, Any] = {"name": ind["name"], "unit": ind["unit"], "error": None}
        try:
            if ind["kind"] == "yahoo":
                hist, val, d = _yahoo_series(yc, ind["id"])
                entry["latest_value"] = val
                entry["latest_date"] = d
                entry["history"] = hist
            elif ind["kind"] == "fred":
                pts = get_series(ind["id"])
                if ind.get("yoy"):
                    pts = yoy_pct(pts)
                lp = latest(pts)
                entry["latest_value"] = lp.value
                entry["latest_date"] = lp.date
                # 최근 5년치만 (월간 데이터 기준 60개)
                entry["history"] = [(p.date, p.value) for p in pts if p.value is not None][-60:]
            else:
                raise ValueError(f"알 수 없는 kind: {ind['kind']}")
        except Exception as e:  # noqa: BLE001 - 지표 단위 독립 실패, 전체 파이프라인은 계속
            entry["error"] = str(e)
            entry["latest_value"] = None
            entry["latest_date"] = None
            entry["history"] = []
        results.append(entry)

    return results


if __name__ == "__main__":
    data = fetch_all_macro()
    for d in data:
        if d["error"]:
            print(f"[실패] {d['name']}: {d['error']}")
        else:
            print(f"{d['name']}: {d['latest_value']:.2f}{d['unit']} ({d['latest_date']}) - 히스토리 {len(d['history'])}개")
