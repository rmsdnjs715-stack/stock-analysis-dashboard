"""빅테크 Top20(+커스텀) 종목의 펀더멘털·주가이력·기술적지표 수집."""
from __future__ import annotations

import time
from datetime import date, datetime, timezone
from typing import Any

from config import TECH_UNIVERSE, TOP_N, load_custom_tickers
from technical import technical_summary
from yahoo_client import YahooClient, raw, with_retry

_QS_MODULES = ["price", "financialData", "defaultKeyStatistics", "summaryDetail"]


def _fetch_one(yc: YahooClient, ticker: str) -> dict[str, Any]:
    qs = with_retry(yc.get_quote_summary, ticker, _QS_MODULES, retries=2, delay=1.5)
    price_mod = qs.get("price", {})
    fd = qs.get("financialData", {})
    dks = qs.get("defaultKeyStatistics", {})
    sd = qs.get("summaryDetail", {})

    name = price_mod.get("longName") or price_mod.get("shortName") or ticker
    market_cap = raw(price_mod.get("marketCap"))
    currency = price_mod.get("currency")
    current_price = raw(price_mod.get("regularMarketPrice"))
    eps = raw(dks.get("trailingEps"))
    roe = raw(fd.get("returnOnEquity"))
    cash = raw(fd.get("totalCash"))
    per = raw(sd.get("trailingPE"))

    # 전고점 계산은 상장 이후 전체 히스토리가 필요하다 (INTC/CSCO처럼 2000년 닷컴버블
    # 고점을 5년 데이터로는 못 잡는 종목이 있음). range_="max"는 Yahoo가 일부 구간만
    # 반환하는 버그성 동작이 확인되어(168개 포인트만 반환), period1/period2로 명시 요청한다.
    # timezone-aware로 계산해야 한다: naive datetime.timestamp()는 로컬 타임존 기준으로
    # mktime을 거치는데, UTC+ 시간대에서 1970-01-01 근처 날짜는 음수 유닉스타임이 되어
    # Windows CRT에서 OSError(Errno 22)가 발생한다.
    period1 = int(datetime(1980, 1, 1, tzinfo=timezone.utc).timestamp())
    period2 = int(datetime.now(timezone.utc).timestamp())
    chart = with_retry(
        yc.get_chart, ticker, interval="1d", period1=period1, period2=period2, retries=2, delay=1.5
    )
    ts = chart["timestamp"]
    closes_raw = chart["indicators"]["quote"][0]["close"]
    hist: list[tuple[date, float]] = []
    for t, c in zip(ts, closes_raw):
        if c is None:
            continue
        try:
            hist.append((date.fromtimestamp(t), c))
        except (OSError, ValueError, OverflowError):
            continue  # 일부 플랫폼(Windows)에서 극단적인 타임스탬프 변환 실패 방어
    closes = [c for _, c in hist]

    ath = max(closes) if closes else None
    drawdown_pct = None
    if ath and current_price:
        drawdown_pct = (current_price - ath) / ath * 100

    # 기술적지표(MA200 등)는 최근 구간이면 충분 - 전체 히스토리 대신 꼬리만 사용
    tech = technical_summary(closes[-400:]) if closes else {}

    return {
        "ticker": ticker,
        "name": name,
        "market_cap": market_cap,
        "currency": currency,
        "current_price": current_price,
        "eps": eps,
        "roe_pct": roe * 100 if roe is not None else None,
        "cash": cash,
        "per": per,
        "ath": ath,
        "drawdown_pct": drawdown_pct,
        "price_history": _monthly_resample(hist),
        "technical": tech,
        "error": None,
    }


def _krw_per_usd(yc: YahooClient) -> float | None:
    try:
        chart = with_retry(yc.get_chart, "KRW=X", interval="1d")
        return float(chart["meta"]["regularMarketPrice"])
    except Exception:  # noqa: BLE001 - 실패하면 KRW 종목만 랭킹에서 배제(잘못된 비교 방지)
        return None


def _monthly_resample(hist: list[tuple[date, float]]) -> list[tuple[date, float]]:
    """엑셀 차트용으로 각 (연,월)의 마지막 종가만 남겨 데이터량을 줄인다."""
    by_month: dict[tuple[int, int], tuple[date, float]] = {}
    for d, c in hist:
        by_month[(d.year, d.month)] = (d, c)  # 같은 달은 뒤에 나온 값(월말에 가까움)으로 덮어씀
    return [by_month[k] for k in sorted(by_month.keys())]


def fetch_top_bigtech() -> list[dict[str, Any]]:
    """TECH_UNIVERSE를 시가총액 기준으로 랭킹해 Top20 + 커스텀 추가 종목을 반환.
    종목 단위로 독립 실패 처리 - 일부 티커가 실패해도 나머지는 정상 수집.
    """
    yc = YahooClient()
    custom = load_custom_tickers()
    all_tickers = list(dict.fromkeys(TECH_UNIVERSE + custom))  # 순서 유지, 중복 제거

    collected: list[dict[str, Any]] = []
    failed: list[tuple[str, str]] = []
    for i, ticker in enumerate(all_tickers):
        try:
            collected.append(_fetch_one(yc, ticker))
        except Exception as e:  # noqa: BLE001 - 종목 단위 독립 실패
            failed.append((ticker, str(e)))
        if i < len(all_tickers) - 1:
            time.sleep(0.4)  # Yahoo rate limit 완화

    # KRW 표시 종목(005930.KS, 000660.KS 등)을 원화 그대로 비교하면 원/달러 환율
    # 배수만큼 시총이 부풀려져 랭킹이 왜곡된다 - USD 환산 후 정렬한다.
    krw_per_usd = _krw_per_usd(yc)

    def usd_cap(entry: dict[str, Any]) -> float:
        cap = entry.get("market_cap") or 0
        if entry.get("currency") == "KRW" and krw_per_usd:
            return cap / krw_per_usd
        return cap

    collected.sort(key=usd_cap, reverse=True)
    top = collected[:TOP_N]
    top_tickers = {c["ticker"] for c in top}

    # 커스텀 종목은 Top20에 없어도 항상 포함 ("[기업] 추가해줘" 요청 반영)
    extra = [c for c in collected if c["ticker"] in custom and c["ticker"] not in top_tickers]

    for t, err in failed:
        print(f"[실패] {t}: {err}")

    return top + extra


if __name__ == "__main__":
    data = fetch_top_bigtech()
    print(f"수집 성공: {len(data)}종목\n")
    for d in data:
        mc = f"{d['market_cap']/1e9:.1f}B" if d["market_cap"] else "N/A"
        eps = f"{d['eps']:.2f}" if d["eps"] is not None else "N/A"
        roe = f"{d['roe_pct']:.1f}%" if d["roe_pct"] is not None else "N/A"
        per = f"{d['per']:.1f}" if d["per"] is not None else "N/A"
        dd = f"{d['drawdown_pct']:.1f}%" if d["drawdown_pct"] is not None else "N/A"
        print(f"{d['ticker']:10s} {d['name']:30s} 시총:{mc:>10s} EPS:{eps:>8s} ROE:{roe:>8s} PER:{per:>8s} 전고점대비:{dd:>8s}")
