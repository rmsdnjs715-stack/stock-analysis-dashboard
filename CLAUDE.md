# 주식 분석 자동화 프로젝트

무료 API(FRED·Yahoo Finance·KRX)로 미국 매크로 지표 + 코스피/코스닥 + 삼성전자·SK하이닉스 +
빅테크 Top20 + 전략자산(정부 지분투자) + 섹터별 Top3를 자동 수집해서 보여주는 로컬 Streamlit
대시보드.

## 실행 방법

```bash
pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 http://localhost:8501 로 열림. (컴퓨터를 껐다 켰으면 매번 위 명령을 다시 실행해야
서버가 뜬다 — 백그라운드 상시 서비스가 아님)

## ⚠️ 이 프로젝트에는 소유자가 다른 두 개의 파이프라인이 있다

2026-08-09에 사용자가 다른 창(세션)에서 겹치는 요청을 동시에 진행해서, `src/` 안에 두 갈래
코드가 있다. **서로의 파일을 건드리지 않기로 합의된 상태이니, 각 파이프라인 작업 시 반대쪽
파일은 참고만 하고 수정하지 말 것.**

### A. 웹 대시보드 파이프라인 (현재 메인 — 이 문서를 관리하는 세션 소유)

| 파일 | 역할 |
|---|---|
| `app.py` | Streamlit 엔트리포인트. 실행하면 이게 뜬다 |
| `src/config.py` | 모든 지표·종목 설정 (`MACRO_INDICATORS`, `LIQUIDITY_INDICATORS`, `SENTIMENT_INDICATORS`, `SEMI_INDICATORS`, `SEMI_STOCKS`, `KR_INDEX_INDICATORS`, `KR_INDEX_DETAIL`, `TECH_UNIVERSE`, `STRATEGIC_ASSETS`, `SECTOR_CANDIDATES`, `MANUAL_INDICATORS`) |
| `src/fred_client.py` | FRED CSV 클라이언트 (무료, 키 불필요, 재시도 로직 포함) |
| `src/yahoo_client.py` | Yahoo Finance 비공식 API 클라이언트 (무료, 키 불필요, crumb 세션 스레드세이프 관리) |
| `src/krx_client.py` | 코스피/코스닥 PBR·외국인순매수 — **KRX 무료 계정 로그인 필요** (아래 참고) |
| `src/indicators.py` | 매크로/유동성/심리/코스피코스닥 지표 수집. 지표 단위 실패 격리, 출처 URL, 실패 원인 진단(`fail_reason`) 포함 |
| `src/screener.py` | 빅테크 Top20 스캔(`run()`) + 고정순서 워치리스트(`fetch_watchlist()`) + 테마/섹터별 Top N(`fetch_theme_leaders()`). ThreadPoolExecutor 병렬 조회, KRW→USD 환산 랭킹, ROE/RSI/MACD/전고점대비 포함 |
| `src/technical.py` | MA/RSI/MACD 계산 — **다른 세션(B)이 만든 파일이지만 여기서도 재사용 중** (중복 구현 금지) |
| `tests/test_indicators.py` | 단위테스트 (네트워크 호출 없이 순수 함수만 검증) |

### B. 엑셀 리포트 파이프라인 (다른 세션 소유 — 건드리지 않음)

`main.py`(루트), `src/fetch_macro.py`, `src/fetch_equities.py`, `src/fill_sections.py`,
`src/build_excel.py` → 산출물 `output/빅테크_매크로_분석리포트.xlsx`.
사용자가 "엑셀 리포트는 이제 안 하게" 이후로 A 파이프라인 쪽 엑셀 코드(`report_builder.py`,
내 쪽 `src/main.py`)는 삭제했지만, 이 B 파이프라인 파일들은 그대로 둔 상태.

## 알아둬야 할 것 (직접 겪고 확인한 이슈들)

1. **KRX는 2026년 기준 로그인이 있어야 응답한다.** 익명 요청은 `getJsonData.cmd`가
   `"LOGOUT"` 문자열만 반환하는 걸 curl·pykrx 양쪽으로 직접 확인했다. 코스피/코스닥
   PBR·외국인순매수를 자동 수집하려면:
   1. https://data.krx.co.kr 무료 회원가입
   2. `KRX_ID`/`KRX_PW` 환경변수 설정
   3. `pip install pykrx`
   설정 안 하면 해당 항목은 "수동 확인 필요"로만 표시된다(정상 동작, 에러 아님).

2. **FRED가 간헐적으로 타임아웃난다.** `fred.stlouisfed.org` 쪽 문제로, 이 세션에서
   직접 재현 확인함(코드 버그 아님). 매크로/유동성 탭이 느리게 뜨면 대부분 이것 때문 —
   "진단" 칸에 "네트워크 일시 장애"로 뜬다.

3. **KRW 표시 종목(005930.KS, 000660.KS)은 반드시 USD 환산 후 시가총액을 비교해야 한다.**
   그냥 raw 숫자로 비교하면 원화 자릿수 때문에 순위가 크게 왜곡된다(예: 삼성전자가 실제보다
   훨씬 위로 잘못 잡힘). `screener._market_cap_usd()`가 처리. 다른 세션의
   `fetch_equities.py`에도 같은 버그가 있어서 발견 즉시 1줄 패치해줬다.

4. **커스텀 티커는 형식 검증이 필요하다** (`config.add_custom_ticker`). 검증 없이 저장하면
   `yahoo_client`의 URL 조립부(`f".../{ticker}?..."`)에 그대로 들어가서 `&`/`/` 같은 문자가
   요청을 깨뜨리거나 쿼리스트링을 오염시킬 수 있다. 화이트리스트 정규식으로 이미 막아뒀다.

5. **Streamlit의 `st.markdown(unsafe_allow_html=True)`는 `ondblclick` 같은 인라인 이벤트
   핸들러를 새니타이저가 제거하고, `<a>` 태그 안에 블록 레벨 `<div>`를 넣으면 그 태그 자체를
   쪼개버린다** (둘 다 직접 겪고 확인함). 그래서 "카드/표 클릭 시 출처로 이동" 기능은
   `ondblclick` JS 트리거가 아니라 진짜 `<a href target="_blank">` 단일클릭 링크로
   구현했고, 내부 라벨/값은 `<div>` 대신 `<span>`(CSS로 block 처리)을 쓴다.

6. **클로드 아티팩트(claude.ai)와 이 로컬 대시보드는 성격이 다르다.** 아티팩트는 강한 CSP
   때문에 브라우저에서 외부 API(FRED/Yahoo/KRX)를 직접 호출할 수 없어서, "지표 매뉴얼"
   아티팩트는 정적 참고문서로만 쓴다 (https://claude.ai/code/artifact/33c63ac0-b036-4057-90ab-b44667cedbe1).
   실시간 데이터가 필요한 건 전부 이 로컬 대시보드 쪽으로 만든다.

7. **테마/섹터 Top N 후보군은 티커가 여러 표에 겹쳐도 된다** (사용자가 명시적으로 허용).
   `fetch_theme_leaders()`는 후보 티커를 한 번씩만 조회하고 여러 테마/섹터에서 재사용한다.

## 코드 스타일 원칙 (이 프로젝트에서 지켜온 것)

- **표준 라이브러리 우선.** `requests`/`pandas` 없이 `urllib`만 사용 (KRX 자동화용 `pykrx`만
  선택적 예외 — 설치 안 해도 나머지는 정상 동작).
- **지표/종목 단위 실패 격리.** 하나 실패해도 나머지 수집·렌더링은 계속 진행.
- **중복 없애기.** 같은 계산(기술적지표, 종목 조회)을 두 곳에 다시 구현하지 않고 기존 함수
  재사용 (`technical.py`, `screener._fetch_one`).
- **속도.** 종목 조회는 `ThreadPoolExecutor`로 병렬화 (Yahoo crumb는 스레드세이프 락으로 보호).

## 다음에 이어서 할 만한 것 (미완성/제안)

- DART Open API 키 발급 후 삼성전자·SK하이닉스 캐펙스·공시 원문 연동 (현재는 수동 확인 항목)
- CNN Fear&Greed, Shiller CAPE, AAII 등 스크래핑 기반 지표 추가 (현재는 수동 확인 항목)
- `indicators.py`의 FRED 호출도 `screener.py`처럼 병렬화하면 매크로/유동성 탭 속도 개선 가능
- 섹터별 Top3 후보군(`config.SECTOR_CANDIDATES`)을 산업 세분류까지 더 쪼갤 수 있음(예: 기술
  섹터를 반도체/소프트웨어로 분리) — 사용자가 원하면 후보 티커만 추가하면 됨
