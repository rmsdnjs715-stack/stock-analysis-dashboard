"""매크로 지표 정의 및 빅테크 후보 유니버스 설정."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CUSTOM_TICKERS_PATH = ROOT_DIR / "custom_tickers.json"
OUTPUT_DIR = ROOT_DIR / "output"
QUOTES_FILE = ROOT_DIR / "주식매매격언_정리.xlsx"
REPORT_FILE = OUTPUT_DIR / "주식시장_분석리포트.xlsx"

# ---- 01 미국 매크로 지표 ----
# kind: "fred" (FRED series id) | "yahoo" (Yahoo ticker)
MACRO_INDICATORS: list[dict] = [
    {"name": "美 기준금리(Fed Funds)", "kind": "fred", "id": "FEDFUNDS", "unit": "%"},
    {"name": "美 장단기 금리차(10Y-2Y)", "kind": "fred", "id": "T10Y2Y", "unit": "%p"},
    {"name": "美 CPI(전년동월비, YoY)", "kind": "fred", "id": "CPIAUCSL", "unit": "%", "yoy": True},
    {"name": "美 근원 PCE(전년동월비, YoY)", "kind": "fred", "id": "PCEPILFE", "unit": "%", "yoy": True},
    {"name": "Sahm Rule(실업률 경기침체 신호)", "kind": "fred", "id": "SAHMREALTIME", "unit": "%p"},
    {"name": "나스닥종합지수", "kind": "yahoo", "id": "^IXIC", "unit": "pt"},
    {"name": "美 10년물 국채금리", "kind": "yahoo", "id": "^TNX", "unit": "%"},
    {"name": "美 3개월 국채금리(단기금리)", "kind": "yahoo", "id": "^IRX", "unit": "%"},
    {"name": "달러인덱스(DXY)", "kind": "yahoo", "id": "DX-Y.NYB", "unit": "pt"},
    {"name": "WTI 유가", "kind": "yahoo", "id": "CL=F", "unit": "$/배럴"},
]

# ---- 02 글로벌 유동성 지표 ----
LIQUIDITY_INDICATORS: list[dict] = [
    {"name": "연준 대차대조표(WALCL)", "kind": "fred", "id": "WALCL", "unit": "백만달러"},
    {"name": "역레포 잔고(RRP)", "kind": "fred", "id": "RRPONTSYD", "unit": "십억달러"},
    {"name": "재무부 일반계정(TGA)", "kind": "fred", "id": "WTREGEN", "unit": "백만달러"},
    {"name": "M2 통화량(미국)", "kind": "fred", "id": "M2SL", "unit": "십억달러"},
    {"name": "하이일드 스프레드(OAS)", "kind": "fred", "id": "BAMLH0A0HYM2", "unit": "%p"},
]

# ---- 03 시장 심리 지표 ----
SENTIMENT_INDICATORS: list[dict] = [
    {"name": "VIX(변동성지수)", "kind": "yahoo", "id": "^VIX", "unit": "pt"},
]

# ---- 06 반도체 특화 지표 (지수/환율) ----
SEMI_INDICATORS: list[dict] = [
    {"name": "필라델피아 반도체지수(SOX)", "kind": "yahoo", "id": "^SOX", "unit": "pt"},
    {"name": "원/달러 환율", "kind": "yahoo", "id": "KRW=X", "unit": "원"},
]

# 삼성전자·SK하이닉스 핵심 펀더멘털 (PER/시총/EPS) - yahoo quoteSummary 사용
SEMI_STOCKS: list[dict] = [
    {"name": "삼성전자", "ticker": "005930.KS"},
    {"name": "SK하이닉스", "ticker": "000660.KS"},
]

# ---- 07 코스피·코스닥 지수 레벨 (yahoo, 자유 조회) ----
KR_INDEX_INDICATORS: list[dict] = [
    {"name": "코스피", "kind": "yahoo", "id": "^KS11", "unit": "pt"},
    {"name": "코스닥", "kind": "yahoo", "id": "^KQ11", "unit": "pt"},
]

# 코스피·코스닥 상세 지표 (PBR·외국인 순매수).
# 2026년 기준 KRX 정보데이터시스템은 로그인 세션이 있어야 응답한다(익명 요청은 "LOGOUT"만 반환 -
# curl/pykrx로 직접 확인함). 무료 회원가입(data.krx.co.kr) 후 KRX_ID/KRX_PW 환경변수를 설정하면
# krx_client가 자동 수집하고, 없으면 indicators.py가 "수동 확인 필요"로 표시한다.
KR_INDEX_DETAIL: list[dict] = [
    {"name": "코스피 PBR", "market": "KOSPI", "field": "pbr"},
    {"name": "코스피 외국인 순매수(억원)", "market": "KOSPI", "field": "foreign_net_buy"},
    {"name": "코스닥 PBR", "market": "KOSDAQ", "field": "pbr"},
    {"name": "코스닥 외국인 순매수(억원)", "market": "KOSDAQ", "field": "foreign_net_buy"},
]

# ---- 빅테크 후보 유니버스 (시가총액 기준 Top20 선정 대상) ----
TECH_UNIVERSE: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AVGO", "ORCL",
    "CRM", "ADBE", "NFLX", "AMD", "INTC", "QCOM", "CSCO", "IBM", "TXN", "NOW",
    "INTU", "UBER", "PLTR", "SHOP", "ASML", "TSM", "SAP", "SONY",
    "005930.KS", "000660.KS", "BABA", "PDD", "SNOW", "PANW", "MU", "ARM", "DELL",
]

TOP_N = 20

# ---- 전략자산(미 행정부 지분투자) 감시 목록 - Top20 랭킹과 별개로 고정 표시 ----
# 사용자가 직접 정리한 목록(반도체 공급망·희토류·양자컴퓨팅 등 정부 지분 참여 종목)을
# 시가총액 랭킹 없이 원래 순서 그대로 보여준다. stake_note는 "지분율(발표일)" 형식.

# 전체 시장 섹터별 Top3 (핀비즈 히트맵의 11개 대분류 섹터 기준) - 정부 전략자산 테마와
# 별개로, 시장 전체를 훑어보고 싶다는 요청으로 추가. 각 섹터 후보는 시가총액 최상위권
# 대형주 위주로 구성했다(신생/소형주는 상장폐지·합병 리스크가 있어 검증이 필요하지만,
# 여기 있는 종목들은 전부 오랫동안 안정적으로 거래돼 온 대형주라 별도 검증 없이 사용).
SECTOR_CANDIDATES: dict[str, list[str]] = {
    "기술(Technology)": ["NVDA", "AAPL", "MSFT", "AVGO", "ORCL", "AMD", "INTC", "CSCO"],
    "커뮤니케이션서비스": ["GOOGL", "META", "NFLX", "DIS", "T", "VZ"],
    "임의소비재(Consumer Cyclical)": ["AMZN", "TSLA", "HD", "MCD", "NKE", "BKNG"],
    "헬스케어": ["LLY", "UNH", "JNJ", "ABBV", "MRK", "PFE"],
    "금융": ["BRK-B", "JPM", "V", "MA", "BAC", "GS"],
    "산업재": ["GE", "RTX", "BA", "CAT", "UNP", "HON"],
    "필수소비재(Consumer Defensive)": ["WMT", "PG", "KO", "PEP", "COST"],
    "에너지": ["XOM", "CVX", "COP", "SLB"],
    "유틸리티": ["NEE", "DUK", "SO", "AEP"],
    "리츠(Real Estate)": ["PLD", "AMT", "EQIX", "PSA"],
    "소재(Basic Materials)": ["LIN", "SHW", "FCX", "NEM"],
}
SECTOR_TOP_N = 3

STRATEGIC_ASSETS: list[dict] = [
    {"ticker": "INTC", "name": "인텔", "theme": "반도체 공급망", "stake_note": "지분 9.9%('26.8.25)"},
    {"ticker": "MP", "name": "MP머티리얼즈", "theme": "희토류 대장", "stake_note": "지분 15%('26.7.10)"},
    {"ticker": "LAC", "name": "리튬아메리카스", "theme": "리튬 공급망", "stake_note": "지분 5%('26.9.24)"},
    {"ticker": "TMQ", "name": "트릴로지메탈스", "theme": "알래스카 광산", "stake_note": "지분 10%+옵션 7.5%('26.10.7)"},
    {"ticker": "USAR", "name": "USA레어어스", "theme": "희토류(텍사스)", "stake_note": "지분 10%('26.1.24)"},
    {"ticker": "IBM", "name": "IBM", "theme": "양자컴퓨팅", "stake_note": "지분 1% 내외('26.5.22)"},
    {"ticker": "GFS", "name": "글로벌파운드리스", "theme": "양자(파운드리)", "stake_note": "지분 1% 내외('26.5.22)"},
    {"ticker": "QBTS", "name": "D웨이브퀀텀", "theme": "양자(어닐링)", "stake_note": "지분 1% 내외('26.5.22)"},
    {"ticker": "RGTI", "name": "리게티", "theme": "양자(초전도)", "stake_note": "지분 1% 내외('26.5.22)"},
    {"ticker": "INFQ", "name": "인플렉션", "theme": "양자(중성원자)", "stake_note": "지분 3~5% 내외('26.5.22)"},
]

# ---- 무료·안정적 API가 없어 자동화하지 않고 "수동 확인" 항목으로만 리포트에 표시 ----
MANUAL_INDICATORS: list[dict] = [
    {"name": "ISM 제조업·서비스업 PMI", "reason": "원자료는 유료(ISM), 무료 대체는 언론 요약뿐"},
    {"name": "Put/Call Ratio", "reason": "CBOE 무료 공식 API 없음"},
    {"name": "CNN Fear & Greed Index", "reason": "비공식 엔드포인트라 phase2에서 best-effort로만 시도"},
    {"name": "AAII 개인투자자 심리조사", "reason": "회원 전용 데이터"},
    {"name": "S&P500 Shiller CAPE / 버핏지수", "reason": "공식 API 없음, 스크래핑 필요 - phase2"},
    {"name": "D램·낸드 고정가/현물가", "reason": "TrendForce 등 유료 소스"},
    {"name": "코스피 선물 베이시스", "reason": "실시간 파생 데이터, 안정적 무료 소스 없음"},
    {"name": "삼성전자·SK하이닉스 캐펙스 가이던스", "reason": "DART Open API 키(무료 가입) 필요 - phase2"},
]


def load_custom_tickers() -> list[str]:
    if not CUSTOM_TICKERS_PATH.exists():
        return []
    data = json.loads(CUSTOM_TICKERS_PATH.read_text(encoding="utf-8"))
    return list(data.get("tickers", []))


_TICKER_PATTERN = re.compile(r"^[A-Z0-9.\-^=]{1,15}$")


def add_custom_ticker(ticker: str) -> None:
    """사용자가 '[기업] 추가해줘' 요청 시 커스텀 종목을 영속적으로 추가.

    형식을 검증하지 않고 저장하면, 이 값이 이후 yahoo_client의 URL 조립부에
    그대로 삽입되므로(예: .../chart/{ticker}?...) '&'나 '/' 같은 문자가 섞인
    티커가 요청을 깨뜨리거나 의도치 않은 쿼리스트링으로 이어질 수 있다.
    Yahoo Finance 티커는 영문 대문자·숫자·마침표·하이픈·캐럿(지수)·등호(환율) 조합이므로
    그 범위로 화이트리스트 검증한다.
    """
    ticker = ticker.strip().upper()
    if not _TICKER_PATTERN.fullmatch(ticker):
        raise ValueError(
            f"올바르지 않은 티커 형식입니다: {ticker!r} "
            "(영문 대문자·숫자·.·-·^·= 만 허용, 1~15자)"
        )
    tickers = load_custom_tickers()
    if ticker not in tickers:
        tickers.append(ticker)
    CUSTOM_TICKERS_PATH.write_text(
        json.dumps({"tickers": tickers}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
