"""빅테크 후보 유니버스 시가총액 스캔 → Top N 선정 + 재무/기술적 지표.

주의(통화 정규화): TECH_UNIVERSE 대부분은 USD 표시 종목이지만 005930.KS·000660.KS는
KRW 표시라서, 원/달러 환율로 변환하지 않고 raw market_cap 숫자만 비교하면 원화 표기
자릿수 때문에 순위가 왜곡된다(예: 삼성전자가 실제보다 훨씬 위로 잘못 잡힘).
그래서 랭킹은 항상 USD 환산 시가총액(market_cap_usd) 기준으로 정렬한다.

기술적지표(MA/RSI/MACD) 계산은 src/technical.py를 그대로 재사용한다 - 같은 계산을
이 파일에 다시 구현하지 않는다("중복 없애기").

속도: 종목당 API 호출 2번(펀더멘털+가격히스토리) × 35개 종목을 순차로 하면 1분 이상
걸리므로 ThreadPoolExecutor로 종목을 병렬 조회한다. Yahoo crumb는 YahooClient 내부
락으로 한 번만 발급되도록 보호되어 있어 여러 스레드가 같은 클라이언트를 공유해도 안전하다.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from typing import Any

from . import config, technical, yahoo_client

_yahoo = yahoo_client.YahooClient()
_QS_MODULES = ["price", "summaryDetail", "defaultKeyStatistics", "financialData"]
_MAX_WORKERS = 8  # 너무 크면 Yahoo가 순간적으로 429(rate limit)를 줄 수 있어 적당히 제한


def _price_history(ticker: str) -> list[tuple[date, float]]:
    """상장 이후 전체 일봉 종가 (전고점 계산용). range_="max"는 일부만 반환하는 경우가
    있어 period1/period2로 명시 요청한다."""
    period1 = int(datetime(1980, 1, 1, tzinfo=timezone.utc).timestamp())
    period2 = int(datetime.now(timezone.utc).timestamp())
    chart = yahoo_client.with_retry(
        _yahoo.get_chart, ticker, interval="1d", period1=period1, period2=period2
    )
    ts = chart.get("timestamp") or []
    closes_raw = chart["indicators"]["quote"][0]["close"]
    hist: list[tuple[date, float]] = []
    for t, c in zip(ts, closes_raw):
        if c is None:
            continue
        try:
            hist.append((date.fromtimestamp(t), c))
        except (OSError, ValueError, OverflowError):
            continue  # 일부 플랫폼(Windows)에서 극단적인 타임스탬프 변환 실패 방어
    return hist


def _fetch_one(ticker: str) -> dict[str, Any]:
    try:
        data = yahoo_client.with_retry(_yahoo.get_quote_summary, ticker, _QS_MODULES)
    except Exception as e:  # noqa: BLE001
        return {"ticker": ticker, "error": str(e)}

    price_mod = data.get("price", {})
    summary = data.get("summaryDetail", {})
    keystats = data.get("defaultKeyStatistics", {})
    fin = data.get("financialData", {})
    market_cap = yahoo_client.raw(price_mod.get("marketCap"))
    if market_cap is None:
        return {"ticker": ticker, "error": "marketCap 없음"}

    current_price = yahoo_client.raw(price_mod.get("regularMarketPrice"))
    roe = yahoo_client.raw(fin.get("returnOnEquity"))
    cash = yahoo_client.raw(fin.get("totalCash"))

    try:
        hist = _price_history(ticker)
        history_error = None
    except Exception as e:  # noqa: BLE001 - 히스토리 실패해도 기본 지표(시총·PER 등)는 살린다
        hist = []
        history_error = str(e)
    closes = [c for _, c in hist]
    ath = max(closes) if closes else None
    drawdown_pct = (current_price - ath) / ath * 100 if ath and current_price else None
    tech = technical.technical_summary(closes[-400:]) if closes else {}

    return {
        "ticker": ticker,
        "name": price_mod.get("shortName") or price_mod.get("longName") or ticker,
        "market_cap": market_cap,
        "currency": price_mod.get("currency"),
        "price": current_price,
        "per": yahoo_client.raw(summary.get("trailingPE")),
        "eps": yahoo_client.raw(keystats.get("trailingEps")),
        "roe_pct": roe * 100 if roe is not None else None,
        "cash": cash,
        "ath": ath,
        "drawdown_pct": drawdown_pct,
        "technical": tech,
        # history_error: 가격 히스토리(전고점/기술적지표)만 조회 실패한 경우의 사유.
        # 종목 자체는 정상 조회됐으니 error=None으로 두고 이 필드로만 구분한다 -
        # 그래야 run()/화면에서 "왜 RSI가 N/A인지"를 조용히 숨기지 않고 보여줄 수 있다.
        "history_error": history_error,
        "error": None,
    }


def _krw_per_usd() -> float | None:
    try:
        chart = yahoo_client.with_retry(_yahoo.get_chart, "KRW=X", "5d", "1d")
        return float(chart.get("meta", {}).get("regularMarketPrice"))
    except Exception:  # noqa: BLE001 - 실패해도 스캔 자체는 계속 (KRW 종목만 정규화 제외)
        return None


def _market_cap_usd(entry: dict[str, Any], krw_per_usd: float | None) -> float | None:
    cap = entry.get("market_cap")
    if cap is None:
        return None
    if entry.get("currency") == "KRW":
        if not krw_per_usd:
            return None  # 환율 조회 실패 시 정규화 불가 - 랭킹에서 제외(잘못된 비교 방지)
        return cap / krw_per_usd
    return cap  # USD 표시 종목(ADR 포함)은 그대로


def run(
    universe: list[str] | None = None,
    top_n: int | None = None,
    pinned_tickers: list[str] | None = None,
) -> dict[str, Any]:
    """유니버스 종목의 USD 환산 시가총액을 조회해 Top N을 선정.

    pinned_tickers로 지정한 종목(기본값: 삼성전자·SK하이닉스)은 Top N 밖으로 밀려도
    "주요 종목현황" 카드에서 항상 보여줄 수 있도록 별도 조회 없이 결과에서 찾아 반환한다.

    반환: {"ranked": [...상위 top_n...], "pinned": {ticker: entry, ...},
           "failed": [...조회/환산 실패 종목...], "krw_per_usd": float | None,
           "history_failed": [{"ticker": ..., "reason": ...}, ...] - 종목 자체는 조회됐지만
           가격 히스토리(전고점·RSI·MACD 등)만 실패해 해당 필드가 N/A로 표시된 종목}
    """
    tickers = list(universe if universe is not None else config.TECH_UNIVERSE)
    tickers += [t for t in config.load_custom_tickers() if t not in tickers]
    n = top_n if top_n is not None else config.TOP_N
    pins = set(pinned_tickers or [s["ticker"] for s in config.SEMI_STOCKS])

    krw_per_usd = _krw_per_usd()
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(_fetch_one, t): t for t in tickers}
        for future in as_completed(futures):
            results.append(future.result())

    ranked_candidates: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for r in results:
        if r.get("error"):
            failed.append(r)
            continue
        cap_usd = _market_cap_usd(r, krw_per_usd)
        if cap_usd is None:
            failed.append({**r, "error": "USD 환산 실패(환율 조회 안 됨)"})
            continue
        r["market_cap_usd_bil"] = round(cap_usd / 1e9, 2)
        ranked_candidates.append(r)

    ranked_candidates.sort(key=lambda r: r["market_cap_usd_bil"], reverse=True)
    ranked = ranked_candidates[:n]

    all_ok = {r["ticker"]: r for r in ranked_candidates}
    pinned = {t: all_ok[t] for t in pins if t in all_ok}
    history_failed = [
        {"ticker": r["ticker"], "reason": r["history_error"]}
        for r in ranked_candidates if r.get("history_error")
    ]

    return {
        "ranked": ranked, "pinned": pinned, "failed": failed,
        "krw_per_usd": krw_per_usd, "history_failed": history_failed,
    }


def fetch_watchlist(tickers: list[str]) -> dict[str, Any]:
    """랭킹 없이 고정 순서로 보여주는 감시목록 조회 (예: 전략자산 List).

    run()과 달리 시가총액 정렬을 하지 않는다 - 사용자가 정한 순서(예: 정부 지분 참여 발표일
    순) 그대로 보여줘야 하는 목록이라서. _fetch_one은 그대로 재사용해 종목 조회 로직이
    중복되지 않게 한다.

    반환: {"entries": {ticker: entry, ...}, "failed": [...조회 실패 종목...]}
    """
    entries: dict[str, Any] = {}
    failed: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(_fetch_one, t): t for t in tickers}
        for future in as_completed(futures):
            r = future.result()
            if r.get("error"):
                failed.append(r)
            else:
                entries[r["ticker"]] = r
    return {"entries": entries, "failed": failed}


def fetch_theme_leaders(theme_candidates: dict[str, list[str]], top_n: int = 3) -> dict[str, Any]:
    """테마별 후보군에서 USD 환산 시가총액 상위 top_n개를 뽑는다(핀비즈 그룹뷰 느낌).

    같은 티커가 여러 테마의 후보로 겹쳐도(또는 전략자산 List와 겹쳐도) 한 번만 조회하고,
    테마별 순위 산출에는 중복 사용한다 - 사용자 요청대로 표 사이의 중복은 허용한다.

    반환: {"by_theme": {테마: [상위 entry, ...]}, "failed": [...조회/환산 실패 종목...]}
    """
    all_tickers = sorted({t for tickers in theme_candidates.values() for t in tickers})
    krw_per_usd = _krw_per_usd()

    fetched: dict[str, Any] = {}
    failed: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(_fetch_one, t): t for t in all_tickers}
        for future in as_completed(futures):
            r = future.result()
            if r.get("error"):
                failed.append(r)
                continue
            cap_usd = _market_cap_usd(r, krw_per_usd)
            if cap_usd is None:
                failed.append({**r, "error": "USD 환산 실패(환율 조회 안 됨)"})
                continue
            r["market_cap_usd_bil"] = round(cap_usd / 1e9, 2)
            fetched[r["ticker"]] = r

    by_theme: dict[str, list[dict[str, Any]]] = {}
    for theme, tickers in theme_candidates.items():
        entries = [fetched[t] for t in tickers if t in fetched]
        entries.sort(key=lambda r: r["market_cap_usd_bil"], reverse=True)
        by_theme[theme] = entries[:top_n]

    return {"by_theme": by_theme, "failed": failed}
