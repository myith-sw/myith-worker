# AI 파이프라인 — 무엇이 걸러지는가

MYiTH Worker의 AI 사용 흐름. **핵심은 "무엇이 폐기되고, AI 없이도 어떻게 완주하는가"다.**
LLM은 문구·근거 판정만 하고, 로드맵 구조(레벨·순서)는 결정론(공식)이 정한다(C-2).
각 노드의 `파일:줄`은 실제 구현 위치다 — 있는 것만 그렸다.

```mermaid
flowchart TD
    IN["사용자 입력<br/>서술형 · GitHub repoUrl · PDF/이미지 fileKey"]:::input

    %% ── 입력 해석 (G-4 3단 하이브리드, 페이지 단위) ──
    IN --> DOC{"충분한 텍스트?<br/>document.py:98"}:::det
    DOC -->|"1단계 텍스트 충분"| CONTENT
    DOC -->|"부족"| OCR{"OCR 신뢰도?<br/>ocr.py"}:::llm
    OCR -->|"자격증명 없음<br/>→ 스킵"| VIS
    OCR -->|"신뢰도 미달"| VIS
    OCR -->|"충분"| CONTENT
    VIS["Vision LLM<br/>키워드만 추출<br/>vision.py:41"]:::llm
    VIS -->|"성공"| CONTENT
    VIS -->|"실패"| DROPDOC(["문서 기여 없음"]):::drop
    GH["GitHub 요약<br/>언어·README·매니페스트<br/>github.py"]:::llm
    IN --> GH
    GH -->|"404·비공개·타임아웃"| DROPGH(["스킵"]):::drop
    GH --> CONTENT

    CONTENT["산출물 텍스트<br/>서술형 + GitHub + 문서<br/>roadmap_generation.py"]:::det

    %% ── LLM 근거 판정 (G-5, 닫힌 분류) ──
    CONTENT --> SKILLS[["닫힌 스킬 목록 주입<br/>job_profile.skills"]]:::det
    SKILLS --> LLM["LLM 역량 판정<br/>claude-sonnet-5<br/>analyzer.py:128"]:::llm

    %% ── 가드 5중 ──
    LLM --> G1{"목록 안?<br/>가드1"}:::det
    G1 -->|"목록 밖"| D1(["폐기"]):::drop
    G1 --> G2{"근거가 원문에 실재?<br/>가드2"}:::det
    G2 -->|"불일치"| D2(["폐기"]):::drop
    G2 --> G3{"신뢰도 ≥ 임계?<br/>가드3"}:::det
    G3 -->|"미달"| D3(["폐기"]):::drop
    G3 --> ACC["user_competency 저장<br/>+ CompetencyExtracted 발행"]:::det

    LLM -.->|"스키마 이탈<br/>가드4 재시도"| LLM
    LLM -.->|"전면 실패<br/>가드5"| FB["자가진단만으로 조립<br/>(빈 결과 발행)"]:::fallback

    %% ── 결정론 영역 (LLM 없음) ──
    ACC --> DET["결정론 영역 (LLM 0)<br/>D=0.45S+0.30(1−P)+0.25N<br/>위상정렬 → Lv 밴딩<br/>scoring.py · job_profile"]:::det
    FB --> DET
    DET --> QUEST["퀘스트 반영<br/>ALREADY_KNOWN · guidance(H-1)<br/>guidance.py"]:::det

    %% ── H-1 층2 / H-2 (선택적 LLM) ──
    QUEST -.->|"narrative 있을 때만"| L2["층2 문구 다듬기<br/>claude-sonnet-5<br/>실패→층1 폴백"]:::llm
    STAR["STAR 자소서 보완<br/>claude-haiku-4-5<br/>star_enhance.py:124"]:::llm
    STAR -.->|"실패"| SFAIL(["FAILED 발행<br/>화면 안 멈춤"]):::fallback

    classDef llm fill:#ffe0b2,stroke:#e65100,stroke-width:2px,color:#000;
    classDef det fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000;
    classDef drop fill:#eeeeee,stroke:#9e9e9e,stroke-dasharray:5 5,color:#616161;
    classDef fallback fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px,color:#000;
    classDef input fill:#fff,stroke:#333,stroke-width:1px,color:#000;
```

## 색 규칙
- 🟧 **주황 = LLM 노드** — 여기만 AI가 관여한다(근거 판정·문구·Vision·STAR)
- 🟦 **파랑 = 결정론 노드** — 공식·규칙. **로드맵 구조(레벨·순서)엔 LLM이 없다(C-2)**
- ⬜ **회색 점선 = 폐기 경로** — 가드가 걸러내는 것
- 🟩 **초록 = 폴백 경로** — AI가 죽어도 완주한다(C-3)

---

## 그림 2 — 가드 게이트 단면도 (LLM을 믿지 않는다)

LLM 판정이 게이트를 통과하며 줄어든다. 아래 숫자는 [guard-trace-sample.md](guard-trace-sample.md) **§1 모의
실행값**(입력만 모의, 가드 로직은 실측)이다 — 발표엔 §2 실측으로 교체한다. **폐기된 항목은 옆으로 빠진다.**

```mermaid
flowchart LR
    L["LLM 판정<br/>12개<br/>analyzer.py:151"]:::llm --> G1{"가드1<br/>닫힌 집합"}:::det
    G1 -->|"10"| G2{"가드2<br/>근거 강제"}:::det
    G1 -. "폐기 2" .-> X1([목록 밖<br/>kubernetes·kafka]):::drop
    G2 -->|"6"| G3{"가드3<br/>신뢰도 임계"}:::det
    G2 -. "폐기 4" .-> X2([근거 원문에 없음<br/>aws·jpa·ts·중복]):::drop
    G3 -->|"6"| G4{"가드4<br/>스키마·범위"}:::det
    G3 -. "폐기 0" .-> X3([·]):::drop
    G4 -->|"6"| ACC["✅ 최종 반영 6개<br/>user_competency"]:::det
    G4 -. "폐기 0" .-> X4([·]):::drop

    classDef llm fill:#ffe0b2,stroke:#e65100,stroke-width:2px,color:#000;
    classDef det fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000;
    classDef drop fill:#eeeeee,stroke:#9e9e9e,stroke-dasharray:5 5,color:#616161;
```

> **12개 중 6개 폐기.** 이 그림 하나가 "LLM 출력을 그대로 믿지 않는다"를 증명한다.
> STAR 보완(H-2)엔 별도 사실검증 가드가 하나 더 있다([star_enhance.py](../app/llm/star_enhance.py) `has_fabrication`).

---

## 그림 3 — 장애 주입: LLM이 전면 사망해도 서비스는 산다

선불 $5 소진(402)·401·429로 LLM이 죽으면 서킷브레이커가 열리고, **초록 경로만으로 로드맵이 완성**된다.

```mermaid
flowchart TD
    DEAD["✕ LLM 전면 사망<br/>402 크레딧소진 · 401 · 429"]:::dead --> BRK["서킷브레이커 OPEN<br/>breaker.py"]:::fb
    BRK --> EX["역량추출 → 빈 결과<br/>analyzer.py:170"]:::fb
    EX --> SELF["자가진단만으로 병합<br/>Core ConsistencyScheduler(60초)"]:::fb
    SELF --> DET["job_profile 사전계산<br/>D=0.45S+0.30(1−P)+0.25N · Lv 밴딩<br/>(LLM 0)"]:::det
    DET --> DONE(["✅ 로드맵 생성 완주"]):::done
    BRK --> STAR["STAR 보완 → status:FAILED 발행<br/>ai_enhancement.py"]:::fb
    STAR --> SDONE(["✅ 화면 스피너 안 멈춤"]):::done
    BRK --> G["층2 문구 → 층1 규칙 폴백<br/>guidance.py"]:::fb
    G --> GDONE(["✅ 규칙 기반 안내 문구"]):::done

    classDef dead fill:#ffcdd2,stroke:#b71c1c,stroke-width:3px,color:#000;
    classDef fb fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px,color:#000;
    classDef det fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000;
    classDef done fill:#a5d6a7,stroke:#1b5e20,stroke-width:3px,color:#000;
```

> **AI가 죽어도 로드맵·퀘스트·문구가 전부 나온다.** 401 실호출로 세 경로(역량 []·STAR FAILED·문구 층1)
> 모두 완주 검증 완료(2026-07-29).

## 근거 (파일:줄)
- 3단 문서 파싱: [document.py:98](../app/competency/document.py#L98)
- OCR(비-LLM, 자격증명 없으면 스킵): [ocr.py](../app/competency/ocr.py)
- Vision 키워드: [vision.py:41](../app/competency/vision.py#L41)
- GitHub 요약: [github.py](../app/competency/github.py)
- 역량 판정(닫힌 분류) + 가드 5중: [analyzer.py:128](../app/competency/analyzer.py#L128)
- D 공식(결정론): [scoring.py](../app/pipeline/scoring.py) · 값은 job_profile에 사전계산
- 층2 문구 개인화: [guidance.py:128](../app/pipeline/guidance.py#L128)
- STAR 보완: [star_enhance.py:124](../app/llm/star_enhance.py#L124)
- 공급자(서킷브레이커·구조화 출력·폴백): [provider.py](../app/llm/provider.py)

> **과장 금지:** F(직무 프로필 빌드) 오케스트레이터는 런타임 미실행 — D·레벨·선후관계는
> 시드 job_profile에 사전계산돼 있고 Core가 조립 시 읽는다. 위 "결정론 영역"은 그 사전계산
> 공식(scoring.py, 테스트됨)과 조립을 가리킨다.
