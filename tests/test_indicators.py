"""순수 함수 단위 테스트 (네트워크 호출 없음)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config, fred_client
from src.indicators import _classify_error, _source_url
from src.screener import _market_cap_usd


class TestFredYoy(unittest.TestCase):
    def test_yoy_pct_basic(self):
        points = (
            [fred_client.SeriesPoint(date(2024, m, 1), 100.0 + m) for m in range(1, 13)]
            + [fred_client.SeriesPoint(date(2025, 1, 1), 111.0)]
        )
        result = fred_client.yoy_pct(points)
        self.assertIsNone(result[0].value)  # 12개월 미만은 계산 불가
        self.assertAlmostEqual(result[-1].value, (111.0 - 101.0) / 101.0 * 100, places=4)

    def test_yoy_pct_handles_missing(self):
        points = [fred_client.SeriesPoint(date(2024, 1, 1), None)] * 13
        result = fred_client.yoy_pct(points)
        self.assertTrue(all(p.value is None for p in result))

    def test_latest_skips_none(self):
        points = [
            fred_client.SeriesPoint(date(2024, 1, 1), 1.0),
            fred_client.SeriesPoint(date(2024, 2, 1), None),
        ]
        self.assertEqual(fred_client.latest(points).date, date(2024, 1, 1))


class TestScreenerCurrencyNormalization(unittest.TestCase):
    """KRW 표기 종목을 USD로 환산하지 않으면 시총 랭킹이 왜곡되는 것을 막는 로직 검증."""

    def test_krw_entry_converted_to_usd(self):
        entry = {"market_cap": 400_000_000_000_000, "currency": "KRW"}
        usd = _market_cap_usd(entry, krw_per_usd=1400.0)
        self.assertAlmostEqual(usd, 400_000_000_000_000 / 1400.0)

    def test_usd_entry_unchanged(self):
        entry = {"market_cap": 3_000_000_000_000, "currency": "USD"}
        self.assertEqual(_market_cap_usd(entry, krw_per_usd=1400.0), 3_000_000_000_000)

    def test_krw_entry_without_fx_rate_is_excluded(self):
        """환율 조회 실패 시 None을 반환해 랭킹에서 제외되게 한다 (잘못된 비교 방지)."""
        entry = {"market_cap": 400_000_000_000_000, "currency": "KRW"}
        self.assertIsNone(_market_cap_usd(entry, krw_per_usd=None))


class TestCustomTickerValidation(unittest.TestCase):
    """add_custom_ticker가 잘못된 형식을 걸러내는지 검증 (yahoo_client URL 조립부로
    검증 없이 흘러들어가면 요청이 깨지거나 쿼리스트링이 오염될 수 있어 추가한 가드)."""

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._orig_path = config.CUSTOM_TICKERS_PATH
        config.CUSTOM_TICKERS_PATH = Path(self._tmp_dir.name) / "custom_tickers.json"

    def tearDown(self):
        config.CUSTOM_TICKERS_PATH = self._orig_path
        self._tmp_dir.cleanup()

    def test_valid_ticker_is_saved_uppercased(self):
        config.add_custom_ticker("nvda")
        self.assertIn("NVDA", config.load_custom_tickers())

    def test_index_ticker_with_caret_is_accepted(self):
        config.add_custom_ticker("^gspc")
        self.assertIn("^GSPC", config.load_custom_tickers())

    def test_ticker_with_special_chars_is_rejected(self):
        with self.assertRaises(ValueError):
            config.add_custom_ticker("NVDA&evil=1")

    def test_ticker_with_slash_is_rejected(self):
        with self.assertRaises(ValueError):
            config.add_custom_ticker("../etc/passwd")


class TestSourceUrl(unittest.TestCase):
    """더블클릭시 이동할 원본 출처 URL이 kind/id로부터 올바르게 만들어지는지 검증."""

    def test_fred_url(self):
        self.assertEqual(_source_url("fred", "FEDFUNDS"), "https://fred.stlouisfed.org/series/FEDFUNDS")

    def test_yahoo_url_plain_ticker(self):
        self.assertEqual(_source_url("yahoo", "AAPL"), "https://finance.yahoo.com/quote/AAPL")

    def test_yahoo_url_encodes_special_chars(self):
        # ^KS11(코스피), KRW=X(환율)처럼 URL에서 특별한 의미를 갖는 문자는 인코딩돼야 한다.
        self.assertEqual(_source_url("yahoo", "^KS11"), "https://finance.yahoo.com/quote/%5EKS11")
        self.assertEqual(_source_url("yahoo", "KRW=X"), "https://finance.yahoo.com/quote/KRW%3DX")

    def test_unknown_kind_returns_none(self):
        self.assertIsNone(_source_url("krx", "KOSPI"))


class TestClassifyError(unittest.TestCase):
    """실패 사유를 "네트워크 일시 장애/데이터 없음/API 형식 문제"로 구분하는 로직 검증 -
    사용자가 비고(원문 예외 메시지)만 보고 코드 문제인지 판단하지 않아도 되게 하기 위함."""

    def test_timeout_message_classified_as_network(self):
        reason = _classify_error(RuntimeError("FRED FEDFUNDS 접속 실패(3회 시도): The read operation timed out"))
        self.assertIn("네트워크", reason)

    def test_connection_error_type_classified_as_network(self):
        reason = _classify_error(ConnectionError("connection reset"))
        self.assertIn("네트워크", reason)

    def test_no_data_message_classified_as_missing_data(self):
        reason = _classify_error(RuntimeError("SAHMREALTIME: 유효값 없음"))
        self.assertIn("데이터 없음", reason)

    def test_missing_field_classified_as_api_format_issue(self):
        reason = _classify_error(RuntimeError("^VIX: regularMarketPrice 없음"))
        self.assertIn("API 응답 형식", reason)

    def test_key_error_classified_as_api_format_issue(self):
        reason = _classify_error(KeyError("close"))
        self.assertIn("API 응답 형식", reason)


if __name__ == "__main__":
    unittest.main()
