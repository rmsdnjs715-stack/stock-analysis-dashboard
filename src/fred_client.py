"""FRED(연준 경제 데이터) CSV 클라이언트. API 키 불필요."""
from __future__ import annotations

import csv
import io
import urllib.request
from datetime import date
from typing import NamedTuple

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


class SeriesPoint(NamedTuple):
    date: date
    value: float | None


def get_series(series_id: str, timeout: int = 20, retries: int = 2) -> list[SeriesPoint]:
    """FRED 시계열 전체 히스토리를 가져온다. 결측치는 value=None.

    fred.stlouisfed.org는 네트워크 환경에 따라 간헐적으로 연결이 막히는 경우가
    있어(Akamai 엣지 타임아웃), 짧은 재시도를 둔다. 그래도 실패하면 예외를 그대로
    올려 호출부(fetch_macro)가 "자동 수집 실패"로 명확히 표시하게 한다.
    """
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    text: str | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8")
            break
        except Exception as e:  # noqa: BLE001
            if attempt == retries:
                raise RuntimeError(f"FRED {series_id} 접속 실패({retries + 1}회 시도): {e}") from e
    assert text is not None

    points: list[SeriesPoint] = []
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    if len(header) < 2:
        raise RuntimeError(f"FRED {series_id} CSV 형식 오류: {header}")
    for row in reader:
        if len(row) < 2:
            continue
        d = date.fromisoformat(row[0])
        raw_val = row[1].strip()
        val = None if raw_val in ("", ".") else float(raw_val)
        points.append(SeriesPoint(d, val))
    if not points:
        raise RuntimeError(f"FRED {series_id} 데이터 없음")
    return points


def latest(points: list[SeriesPoint]) -> SeriesPoint:
    for p in reversed(points):
        if p.value is not None:
            return p
    raise RuntimeError("유효한 데이터 포인트 없음")


def yoy_pct(points: list[SeriesPoint]) -> list[SeriesPoint]:
    """전년동월대비 변화율(%) 시계열로 변환 (월간 시리즈 기준, 12개월 lag)."""
    out: list[SeriesPoint] = []
    for i, p in enumerate(points):
        if i < 12 or p.value is None or points[i - 12].value in (None, 0):
            out.append(SeriesPoint(p.date, None))
            continue
        prev = points[i - 12].value
        out.append(SeriesPoint(p.date, (p.value - prev) / prev * 100))
    return out
