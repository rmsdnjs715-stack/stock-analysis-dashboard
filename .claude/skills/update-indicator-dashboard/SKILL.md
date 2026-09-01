---
name: update-indicator-dashboard
description: 지표 매뉴얼(주식 분석 자동화 설계도) Claude Artifact 대시보드의 수치·내용을 업데이트하고 재배포할 때 사용. "지표 매뉴얼 업데이트해줘", "대시보드 최신화", "지표 수치 갱신" 같은 요청에 사용.
---

# 지표 매뉴얼 대시보드 업데이트 스킬

## 대상

- **Artifact URL**: https://claude.ai/code/artifact/33c63ac0-b036-4057-90ab-b44667cedbe1
- **정본(source of truth) 파일**: `output/indicator-manual-dashboard.html` (이 프로젝트 루트 기준)
- **내용**: 미국 매크로/유동성/심리·수급/밸류에이션/기술적 지표 + 국내 반도체·코스피·코스닥 특화 지표 + "누가 보는가" 애널리스트 참고 + 자동화용 데이터소스 매핑. 9개 섹션(`s01`~`s09`), 43개 지표 행.
- **디자인 시스템**: insane-design 캐노니컬 리포트 스타일 (TOC 사이드바 + 히어로 + 섹션별 데이터 테이블). 토큰: `--brand-color:#A8792E`(골드/브론즈), 배경 `#faf8f4`(라이트)/`#15130f`(다크), 본문 Pretendard, 라벨·숫자 JetBrains Mono. 라이트/다크 테마 모두 지원.

## 절대 규칙: 항상 이 파일을 수정하라

**절대 처음부터 새로 만들지 말 것.** `output/indicator-manual-dashboard.html`을 Read → Edit로 필요한 `.ind-row`(지표 행) / `.ind-snap`(최근 동향) / 히어로 stats 값만 바꾼다. 이 파일은 Claude 세션의 임시 scratchpad가 아니라 **이 프로젝트 저장소에 영구 보관되는 정본**이다 — Artifact 배포에 쓰이는 scratchpad 디렉터리는 세션이 끝나면 사라지므로, 다음 세션이 내용을 읽으려면 반드시 이 파일이 있어야 한다.

## 업데이트 절차

1. `output/indicator-manual-dashboard.html`을 Read.
2. 바꿀 지표의 `.ind-row` 안 `.ind-snap`(최근 1년 동향) 또는 수치를 Edit로 정확히 교체. 새 지표를 추가할 땐 같은 섹션의 `.ind-row` 블록 구조(6칸: 지표/무엇을/왜/소스/주기/최근동향)를 그대로 복제.
3. 히어로의 `.hero__stats` 값(지표 개수, 스냅샷 날짜 등)도 지표 수가 바뀌면 같이 갱신.
4. `AS OF` 배지 문구(`2026년 8월 스냅샷`)도 실제 갱신 시점에 맞게 수정.
5. **폰트/디자인 CSS는 절대 건드리지 않는다** — `@font-face` data URI 블록(Pretendard, JetBrains Mono)과 캐노니컬 CSS는 이미 완성돼 있음. 콘텐츠(HTML 텍스트)만 수정.
6. `Artifact` 툴로 재배포:
   ```
   Artifact({
     file_path: "<repo>/output/indicator-manual-dashboard.html",
     url: "https://claude.ai/code/artifact/33c63ac0-b036-4057-90ab-b44667cedbe1",
     favicon: "📈",
     force: true   // 아래 "왜 force가 필요한가" 참고
   })
   ```
7. **필수: Share 패널에서 버전 핀 갱신.** 이 아티팩트는 "Anyone with the link"로 공개 공유돼 있는데, 공개 공유 중엔 최신 버전을 자동 추적하지 못하고 **재배포해도 공유 링크는 이전 버전에 고정된 채로 남는다** ("Can't switch to Latest while shared publicly" 에러). 그래서 재배포할 때마다:
   - claude-in-chrome으로 아티팩트 페이지 열기 → 우측 상단 **Share** 버튼 클릭 → **Shared version** 드롭다운에서 방금 만든 최신 버전(가장 위, 가장 최근 시각) 선택.
   - 이 단계를 빼먹으면 사용자와 공유받은 사람은 옛날 내용을 계속 보게 됨.

## 왜 `force: true`가 필요한가

Artifact 업데이트는 정상적으로 "먼저 WebFetch로 최신 버전을 읽고 나서 수정"하도록 요구하지만, 이 환경엔 WebFetch 툴이 없다(사용자 CLAUDE.md 규칙상 금지 + 툴 목록에도 없음). 대신 `output/indicator-manual-dashboard.html`(정본)을 직접 Read하는 것으로 "최신 버전 확인"을 대체하고, `force:true`로 버전 충돌 체크를 건너뛴다. 이건 안전한데, 이 파일 자체가 유일한 편집 소스이고 다른 세션이 아티팩트를 직접 편집할 경로가 없기 때문이다.

## 원본 콘텐츠를 다시 통째로 가져와야 할 때 (마이그레이션/복구 시 참고)

이 아티팩트는 원래 다른 세션에서 만들어진 것이라 로컬 소스가 없었고, claude.ai 아티팩트 iframe은 cross-origin sandbox라 JS/클립보드로 내용을 못 긁어온다(의도된 보안 제약 — 우회 시도하지 말 것). 유일하게 통한 방법: claude-in-chrome으로 열어서 표를 화면 스크롤 + 스크린샷으로 육안 전사(轉寫). 지금은 `output/indicator-manual-dashboard.html`이 정본이라 이 과정이 다시 필요할 일은 없어야 한다.

## 폰트 재내장이 필요한 경우 (CSS를 완전히 새로 짤 때만)

```bash
curl -sL -o Pretendard-Regular.woff2 "https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/web/static/woff2/Pretendard-Regular.woff2"
curl -sL -o Pretendard-SemiBold.woff2 "https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/web/static/woff2/Pretendard-SemiBold.woff2"
curl -sL -o JetBrainsMono-Regular.woff2 "https://cdn.jsdelivr.net/npm/@fontsource/jetbrains-mono@5.0.20/files/jetbrains-mono-latin-400-normal.woff2"
curl -sL -o JetBrainsMono-Medium.woff2 "https://cdn.jsdelivr.net/npm/@fontsource/jetbrains-mono@5.0.20/files/jetbrains-mono-latin-500-normal.woff2"
```
base64 인코딩 후 `@font-face { src: url(data:font/woff2;base64,...) }`로 삽입 (Artifact CSP가 외부 폰트 CDN `<link>`를 막기 때문에 반드시 data URI로 내장해야 함 — 안 그러면 조용히 시스템 폰트로 폴백됨).
