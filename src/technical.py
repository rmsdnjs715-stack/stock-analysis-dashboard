"""가격 히스토리(종가 리스트)로 계산하는 기술적 지표 (MA/RSI/MACD).
외부 데이터 소스 불필요 - Yahoo chart API로 받은 종가만 있으면 계산 가능.

이름을 indicators.py가 아닌 technical.py로 둔 이유: 같은 프로젝트에서
동시에 진행 중인 다른 작업이 indicators.py를 매크로/유동성 등 "지표 수집
오케스트레이션" 모듈로 쓰고 있어(별도 목적), 이름 충돌을 피하기 위함.
"""
from __future__ import annotations


def sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def _ema_series(closes: list[float], period: int) -> list[float]:
    if len(closes) < period:
        return []
    k = 2 / (period + 1)
    ema = [sum(closes[:period]) / period]
    for price in closes[period:]:
        ema.append(price * k + ema[-1] * (1 - k))
    return ema


def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    # 최초 평균은 단순평균, 이후는 와일더(Wilder) 지수평활
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict | None:
    if len(closes) < slow + signal:
        return None
    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)
    # 두 EMA 시리즈 길이를 slow 기준으로 맞춤 (fast가 더 김)
    offset = len(ema_fast) - len(ema_slow)
    macd_line = [ema_fast[i + offset] - ema_slow[i] for i in range(len(ema_slow))]
    if len(macd_line) < signal:
        return None
    signal_line = _ema_series(macd_line, signal)
    macd_val = macd_line[-1]
    signal_val = signal_line[-1]
    return {
        "macd": macd_val,
        "signal": signal_val,
        "histogram": macd_val - signal_val,
    }


def golden_dead_cross(closes: list[float], short: int = 20, long: int = 60) -> str:
    """직전 봉 대비 단기/장기 이평선의 대소 관계 전환 여부로 골든/데드크로스 판정."""
    if len(closes) < long + 1:
        return "판정불가"
    short_now = sma(closes, short)
    long_now = sma(closes, long)
    short_prev = sma(closes[:-1], short)
    long_prev = sma(closes[:-1], long)
    if None in (short_now, long_now, short_prev, long_prev):
        return "판정불가"
    if short_prev <= long_prev and short_now > long_now:
        return "골든크로스"
    if short_prev >= long_prev and short_now < long_now:
        return "데드크로스"
    return "정배열" if short_now > long_now else "역배열"


def rsi_regime(value: float | None) -> str:
    if value is None:
        return "N/A"
    if value >= 70:
        return "과매수"
    if value <= 30:
        return "과매도"
    return "중립"


def macd_signal_text(m: dict | None) -> str:
    if m is None:
        return "N/A"
    return "매수신호" if m["histogram"] > 0 else "매도신호"


def technical_summary(closes: list[float]) -> dict:
    """종목 하나의 기술적 지표 요약. closes는 시간순 오름차순 종가 리스트."""
    ma20 = sma(closes, 20)
    ma60 = sma(closes, 60)
    ma120 = sma(closes, 120)
    ma200 = sma(closes, 200)
    r = rsi(closes, 14)
    m = macd(closes)
    return {
        "ma20": ma20,
        "ma60": ma60,
        "ma120": ma120,
        "ma200": ma200,
        "cross_20_60": golden_dead_cross(closes, 20, 60),
        "rsi14": r,
        "rsi_regime": rsi_regime(r),
        "macd": m["macd"] if m else None,
        "macd_signal": m["signal"] if m else None,
        "macd_regime": macd_signal_text(m),
    }
