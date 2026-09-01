"""코스피·코스닥 상세 지표(PBR, 외국인 순매수) 클라이언트.

주의: FRED/Yahoo와 달리 이 지표는 "완전 무료·키 불필요"가 아니다.
2026년 기준 KRX 정보데이터시스템(data.krx.co.kr)은 로그인 세션이 있어야
getJsonData.cmd 응답을 준다 - 익명 요청은 실제로 "LOGOUT" 문자열만 돌려준다는 것을
curl과 pykrx 양쪽으로 직접 확인했다. 계정 자체는 무료 가입이지만,
DART API 키와 마찬가지로 사전 회원가입이 필요하므로 이 모듈은 선택 사항으로 둔다.

사용 방법:
    1) https://data.krx.co.kr 에서 무료 회원가입
    2) 환경변수 KRX_ID / KRX_PW 를 로그인 계정으로 설정
    3) pip install pykrx (이미 설치돼 있지 않다면)

환경변수가 없거나 pykrx가 없으면 KrxAuthError를 던지고, indicators.py는 이를 잡아
해당 항목을 "수동 확인 필요"로 리포트에 남긴다.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

_MARKET_INDEX_CODE = {"KOSPI": "1001", "KOSDAQ": "2001"}


class KrxAuthError(RuntimeError):
    """pykrx 미설치 또는 KRX_ID/KRX_PW 환경변수 부재."""


def _require_pykrx() -> Any:
    try:
        from pykrx import stock  # type: ignore
    except ImportError as e:
        raise KrxAuthError("pykrx가 설치되어 있지 않습니다. `pip install pykrx` 필요") from e
    if not (os.environ.get("KRX_ID") and os.environ.get("KRX_PW")):
        raise KrxAuthError(
            "KRX_ID / KRX_PW 환경변수가 없습니다. "
            "https://data.krx.co.kr 무료 회원가입 후 환경변수로 설정하세요."
        )
    return stock


def get_pbr(market: str, max_lookback: int = 10) -> tuple[str, float]:
    """코스피/코스닥 PBR. 반환: (기준일 YYYYMMDD, PBR).

    주말·공휴일에는 당일 데이터가 비어 있으므로 최근 영업일을 찾을 때까지 며칠 거슬러 올라간다.
    """
    stock = _require_pykrx()
    idx_code = _MARKET_INDEX_CODE[market]
    d = date.today()
    for _ in range(max_lookback):
        d_str = d.strftime("%Y%m%d")
        df = stock.get_index_fundamental_by_date(d_str, d_str, idx_code)
        if df is not None and not df.empty and "PBR" in df.columns:
            return d_str, float(df["PBR"].iloc[-1])
        d -= timedelta(days=1)
    raise RuntimeError(f"{market} PBR: 최근 {max_lookback}일 내 데이터 없음")


def get_foreign_net_buy(market: str, max_lookback: int = 10) -> tuple[str, float]:
    """코스피/코스닥 외국인 순매수 대금(억원). 반환: (기준일 YYYYMMDD, 순매수액)."""
    stock = _require_pykrx()
    d = date.today()
    for _ in range(max_lookback):
        d_str = d.strftime("%Y%m%d")
        df = stock.get_market_trading_value_by_investor(d_str, d_str, market)
        if df is not None and not df.empty and "외국인합계" in df.columns:
            won = float(df["외국인합계"].iloc[-1])
            return d_str, won / 1e8  # 원 -> 억원
        d -= timedelta(days=1)
    raise RuntimeError(f"{market} 외국인 순매수: 최근 {max_lookback}일 내 데이터 없음")


def get_detail_value(market: str, field: str) -> tuple[str, float]:
    """config.KR_INDEX_DETAIL 의 field 값("pbr" | "foreign_net_buy")에 맞춰 조회."""
    if field == "pbr":
        return get_pbr(market)
    if field == "foreign_net_buy":
        return get_foreign_net_buy(market)
    raise ValueError(f"알 수 없는 field: {field}")
