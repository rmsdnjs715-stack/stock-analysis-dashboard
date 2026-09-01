"""Yahoo Finance 비공식 공개 API 클라이언트.

- get_chart(): 가격 히스토리 (차트/전고점 계산용). UA 헤더만으로 접근 가능.
- get_quote_summary(): 펀더멘털(EPS/ROE/현금/PER 등). crumb+cookie 세션 필요.

API 키 불필요. Yahoo가 비공식 엔드포인트를 언제든 바꿀 수 있으므로,
요청 실패 시 명확한 예외 메시지를 던져 원인을 바로 알 수 있게 한다.
"""
from __future__ import annotations

import http.cookiejar
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


class YahooClient:
    def __init__(self) -> None:
        self._cj = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._cj))
        self._crumb: str | None = None
        self._crumb_lock = threading.Lock()  # 병렬 조회(ThreadPoolExecutor) 시 crumb 중복발급 방지

    def _get(self, url: str, timeout: int = 15) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with self._opener.open(req, timeout=timeout) as resp:
            return resp.read()

    def _ensure_crumb(self) -> str:
        if self._crumb:
            return self._crumb
        with self._crumb_lock:
            if self._crumb:  # 락 대기 중 다른 스레드가 이미 발급했을 수 있음
                return self._crumb
            # 세션 쿠키 확보 (실패해도 무시 - crumb 발급에 필수는 아님)
            try:
                self._get("https://fc.yahoo.com")
            except urllib.error.HTTPError:
                pass
            raw = self._get("https://query2.finance.yahoo.com/v1/test/getcrumb")
            crumb = raw.decode("utf-8").strip()
            if not crumb or "<html" in crumb.lower():
                raise RuntimeError("Yahoo crumb 발급 실패 - Yahoo 세션 정책이 변경되었을 수 있음")
            self._crumb = crumb
            return crumb

    def get_chart(
        self,
        ticker: str,
        range_: str | None = "5y",
        interval: str = "1d",
        period1: int | None = None,
        period2: int | None = None,
    ) -> dict[str, Any]:
        """주가 히스토리.

        range_: 1d/5d/1mo/6mo/1y/5y 등. 주의: range_="max"는 Yahoo가 실제 상장 이후
        전체가 아니라 일부 구간만 반환하는 경우가 확인됨(관측: 168개 포인트만 반환).
        전체 히스토리(전고점 계산용)가 필요하면 range_ 대신 period1/period2(unix
        timestamp)를 명시적으로 지정할 것 - 이 경우가 신뢰할 수 있는 정확한 결과를 준다.
        """
        if period1 is not None and period2 is not None:
            query = f"period1={period1}&period2={period2}"
        else:
            query = f"range={range_}"
        # 티커를 그대로 경로에 넣으면(특히 커스텀 티커) '&'/'/' 같은 문자가 요청을
        # 깨뜨리거나 쿼리스트링을 오염시킬 수 있어 경로 세그먼트로 안전하게 인코딩한다.
        safe_ticker = urllib.parse.quote(ticker, safe="")
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{safe_ticker}"
            f"?{query}&interval={interval}&events=div,splits"
        )
        data = json.loads(self._get(url))
        chart = data.get("chart", {})
        if chart.get("error"):
            raise RuntimeError(f"{ticker} chart API 오류: {chart['error']}")
        result = chart.get("result")
        if not result:
            raise RuntimeError(f"{ticker} chart 데이터 없음")
        return result[0]

    def get_quote_summary(self, ticker: str, modules: list[str]) -> dict[str, Any]:
        crumb = self._ensure_crumb()
        mods = ",".join(modules)
        safe_ticker = urllib.parse.quote(ticker, safe="")
        url = (
            f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{safe_ticker}"
            f"?modules={mods}&crumb={urllib.parse.quote(crumb, safe='')}"
        )
        try:
            data = json.loads(self._get(url))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                # crumb 만료 - 1회 재발급 후 재시도
                self._crumb = None
                crumb = self._ensure_crumb()
                url = (
                    f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{safe_ticker}"
                    f"?modules={mods}&crumb={urllib.parse.quote(crumb, safe='')}"
                )
                data = json.loads(self._get(url))
            else:
                raise
        qs = data.get("quoteSummary", {})
        if qs.get("error"):
            raise RuntimeError(f"{ticker} quoteSummary 오류: {qs['error']}")
        result = qs.get("result")
        if not result:
            raise RuntimeError(f"{ticker} quoteSummary 데이터 없음")
        return result[0]


def raw(field: dict | None) -> Any:
    """Yahoo 응답의 {'raw': x, 'fmt': '...'} 구조에서 raw 값만 추출. None-safe."""
    if not field:
        return None
    return field.get("raw")


def with_retry(fn, *args, retries: int = 2, delay: float = 1.0, **kwargs):
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 - 재시도 후 최종적으로 원인 노출
            last_err = e
            if attempt < retries:
                time.sleep(delay)
    raise last_err  # type: ignore[misc]
