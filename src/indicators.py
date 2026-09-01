"""지표 수집 오케스트레이션.

각 collect_*() 함수는 정규화된 dict 리스트를 반환한다:

    {"name": str, "value": Any, "unit": str, "asof": str | None,
     "source": str, "url": str | None, "status": "ok" | "manual" | "error",
     "note": str | None, "fail_reason": str | None}

지표 하나가 실패해도(네트워크 오류, 응답 형식 변경 등) 나머지 지표 수집과
전체 파이프라인은 계속 진행되도록 지표 단위로 예외를 격리한다.

url: FRED/Yahoo kind+id로부터 만든 실제 데이터 출처 홈페이지 링크 - 웹앱에서
지표를 더블클릭하면 이 링크로 이동한다.
fail_reason: 실패했을 때 "코드/API 문제"인지 "일시적 네트워크 문제"인지 "데이터 자체가
없는 것"인지 구분하는 한글 라벨 - 100% 정확한 판별은 불가능하지만 예외 종류·메시지
패턴으로 상당히 잘 걸러낸다. 사용자가 "재시도하면 되는 건지, 코드를 고쳐야 하는 건지"를
비고(원문 예외 메시지)만 보고 판단하지 않아도 되게 하기 위함.
"""
from __future__ import annotations

import socket
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from typing import Any

from . import config, fred_client, krx_client, yahoo_client

_yahoo = yahoo_client.YahooClient()  # crumb/쿠키를 여러 조회에서 재사용

_NETWORK_MARKERS = (
    "timed out", "timeout", "Connection", "connection", "URLError",
    "Temporary failure", "reset by peer", "EOF occurred", "Network",
)


def _source_url(kind: str, ident: str) -> str | None:
    """지표의 kind/id로부터 실제 데이터 출처 홈페이지 URL을 만든다."""
    if kind == "fred":
        return f"https://fred.stlouisfed.org/series/{ident}"
    if kind == "yahoo":
        return f"https://finance.yahoo.com/quote/{urllib.parse.quote(ident, safe='')}"
    return None


def _classify_error(exc: Exception) -> str:
    """실패 사유가 코드 문제인지/일시적 네트워크 문제인지/데이터 자체가 없는 것인지 구분.

    휴리스틱이라 100% 정확하진 않지만, 이 프로젝트의 예외 메시지 패턴(fred_client·
    yahoo_client·krx_client가 던지는 RuntimeError 문구)과 파이썬 표준 네트워크
    예외 타입 기준으로 흔한 케이스는 잘 잡아낸다.
    """
    msg = str(exc)

    if isinstance(exc, (socket.timeout, TimeoutError, urllib.error.URLError, ConnectionError)) or any(
        m in msg for m in _NETWORK_MARKERS
    ):
        return "네트워크 일시 장애 - 재시도하면 해결될 가능성 높음"

    if any(m in msg for m in ("데이터 없음", "유효값 없음")):
        return "데이터 없음 - 소스에 값이 없거나 아직 발표 전"

    if isinstance(exc, (KeyError, IndexError, TypeError, AttributeError)) or "없음" in msg or "오류" in msg:
        return "API 응답 형식 문제 - API가 바뀌었을 수 있음(코드 점검 필요)"

    return "원인 불명 - 직접 확인 필요"


def _fred_point(spec: dict) -> tuple[str, float]:
    points = fred_client.get_series(spec["id"])
    if spec.get("yoy"):
        points = fred_client.yoy_pct(points)
    p = fred_client.latest(points)
    if p.value is None:
        raise RuntimeError(f"{spec['id']}: 유효값 없음")
    return p.date.isoformat(), round(p.value, 4)


def _yahoo_point(spec: dict) -> tuple[str | None, float]:
    chart = yahoo_client.with_retry(_yahoo.get_chart, spec["id"], "5d", "1d")
    meta = chart.get("meta", {})
    price = meta.get("regularMarketPrice")
    ts = meta.get("regularMarketTime")
    if price is None:
        raise RuntimeError(f"{spec['id']}: regularMarketPrice 없음")
    asof = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat() if ts else None
    return asof, round(float(price), 4)


def _new_row(name: str, unit: str, source: str, url: str | None = None) -> dict[str, Any]:
    return {"name": name, "unit": unit, "value": None, "asof": None, "source": source,
            "url": url, "status": "error", "note": None, "fail_reason": None}


def _collect(specs: list[dict], category: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in specs:
        source = f"FRED:{spec['id']}" if spec["kind"] == "fred" else f"Yahoo:{spec['id']}"
        row = _new_row(spec["name"], spec.get("unit", ""), source, _source_url(spec["kind"], spec["id"]))
        try:
            if spec["kind"] == "fred":
                asof, value = _fred_point(spec)
            elif spec["kind"] == "yahoo":
                asof, value = _yahoo_point(spec)
            else:
                raise ValueError(f"알 수 없는 kind: {spec['kind']} (category={category})")
            row["value"], row["asof"], row["status"] = value, asof, "ok"
        except Exception as e:  # noqa: BLE001 - 지표 하나 실패해도 나머지는 계속 수집
            row["note"] = str(e)
            row["fail_reason"] = _classify_error(e)
        out.append(row)
    return out


def collect_macro() -> list[dict[str, Any]]:
    return _collect(config.MACRO_INDICATORS, "macro")


def collect_liquidity() -> list[dict[str, Any]]:
    return _collect(config.LIQUIDITY_INDICATORS, "liquidity")


def collect_sentiment() -> list[dict[str, Any]]:
    return _collect(config.SENTIMENT_INDICATORS, "sentiment")


def collect_semi() -> list[dict[str, Any]]:
    """SEMI_INDICATORS(SOX·환율)만 반환.

    삼성전자·SK하이닉스 종목 상세(PER/EPS/ROE/기술적지표)는 여기서 따로 조회하지 않는다 -
    screener.run()이 TECH_UNIVERSE 전체를 스캔하면서 이미 그 두 종목도 함께 조회하므로,
    같은 데이터를 두 번 받아오지 않도록 웹앱에서는 screener.run()의 pinned 결과를 사용한다.
    """
    return _collect(config.SEMI_INDICATORS, "semi")


def collect_kr_index() -> list[dict[str, Any]]:
    rows = _collect(config.KR_INDEX_INDICATORS, "kr_index")
    for spec in config.KR_INDEX_DETAIL:
        row = _new_row(spec["name"], "", f"KRX:{spec['market']}", "https://data.krx.co.kr")
        try:
            asof, value = krx_client.get_detail_value(spec["market"], spec["field"])
            row["value"], row["asof"], row["status"] = round(value, 4), asof, "ok"
        except krx_client.KrxAuthError as e:
            row["status"], row["note"] = "manual", str(e)
        except Exception as e:  # noqa: BLE001
            row["note"] = str(e)
            row["fail_reason"] = _classify_error(e)
        rows.append(row)
    return rows


def collect_manual() -> list[dict[str, Any]]:
    """자동화 대상이 아닌 지표 - 리포트에 "수동 확인 필요"로만 표시."""
    return [
        {"name": item["name"], "unit": "", "value": None, "asof": None, "source": "manual",
         "url": None, "status": "manual", "note": item["reason"], "fail_reason": None}
        for item in config.MANUAL_INDICATORS
    ]
