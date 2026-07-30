# AI 파이프라인 — 무엇이 걸러지는가

MYiTH Worker의 AI 사용 흐름. **핵심은 "무엇이 폐기되고, AI 없이도 어떻게 완주하는가"다.**
LLM은 문구·근거 판정만 하고, 로드맵 구조(레벨·순서)는 결정론(공식)이 정한다(C-2).
각 노드의 구현 위치(`파일:줄`)는 판독성을 위해 그림에서 빼고 문서 하단 [근거 목록](#근거-파일줄)에 모았다.

## 그림 1 — 전체 흐름

3초 안에 읽히게 했다 — 주황(LLM)은 **판정만** 하고, 파랑(공식)이 **구조를 정한다.** 상세 분기는 그림 2·3에 있다.

```mermaid
flowchart TB
    IN["사용자 입력<br/>서술형 · GitHub · 포트폴리오 PDF"]:::input

    IN --> PARSE["입력 해석 3단<br/>텍스트 → OCR → Vision<br/>document.py"]:::mix
    PARSE --> SET[["닫힌 스킬 목록 고정 주입<br/>job_profile.skills"]]:::det
    SET --> LLM["LLM 역량 판정<br/>claude-sonnet-5<br/>analyzer.py:128"]:::llm

    LLM --> GUARD{"5중 가드<br/>닫힌집합 · 근거강제 · 신뢰도<br/>스키마 · 사실검증"}:::det
    GUARD -. "절반 폐기" .-> DROP(["근거 없는 판정<br/>버림"]):::drop
    GUARD -->|"근거 있는 것만"| MERGE["user_competency 저장<br/>자가진단과 병합"]:::det

    LLM -. "전면 실패" .-> FB["자가진단만으로 진행"]:::fb
    FB --> MERGE

    MERGE --> DET["결정론 조립 · LLM 관여 0<br/>D = 0.45·S + 0.30·(1−P) + 0.25·N<br/>위상정렬 → Lv 밴딩 → 우선순위"]:::det
    DET --> OUT["개인 로드맵 완성"]:::out
    DET -. "선택적" .-> L2["문구 개인화 층2<br/>실패 시 층1 템플릿"]:::llm
    L2 -.-> OUT

    classDef llm fill:#ffe0b2,stroke:#e65100,stroke-width:2px,color:#000
    classDef det fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000
    classDef mix fill:#f8bbd0,stroke:#880e4f,stroke-width:2px,color:#000
    classDef drop fill:#eeeeee,stroke:#9e9e9e,stroke-dasharray:5 5,color:#616161
    classDef fb fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef input fill:#fff,stroke:#333,color:#000
    classDef out fill:#a5d6a7,stroke:#1b5e20,stroke-width:3px,color:#000
```

## 색 규칙
- 🟧 **주황 = LLM 판정** — 역량 판정·문구·Vision. 여기만 AI가 관여한다.
- 🟦 **파랑 = 결정론** — 공식·규칙. **로드맵 구조(레벨·순서)엔 LLM이 없다(C-2)**
- 🌸 **분홍 = 입력 해석 3단** — 텍스트→OCR→Vision 혼합
- ⬜ **회색 점선 = 폐기 경로** — 가드가 걸러내는 것
- 🟩 **초록 = 폴백/완성** — AI가 죽어도 완주한다(C-3)

---

## 그림 2 — 가드 깔때기 (LLM을 믿지 않는다)

LLM 판정 12개가 가드를 통과하며 6개로 줄어든다. 숫자는 [guard-trace-sample.md](guard-trace-sample.md)
**§1 모의 실행값**(입력만 모의, 가드 로직은 실측)이며, 그림 안 첫 노드(LLM 판정)에도 표기했다 — 발표엔 §2 실측으로 교체한다.

```mermaid
flowchart TB
    L["LLM 판정 &nbsp;12개<br/><small>모의 입력 실행값 · 가드 로직은 실제 코드</small>"]:::llm
    L --> G1["가드 1 · 닫힌 집합<br/>목록 밖 스킬 제거"]:::det
    G1 -->|"남은 10"| G2["가드 2 · 근거 강제<br/>원문에 없는 판정 제거"]:::det
    G2 -->|"남은 6"| G3["가드 3 · 신뢰도 임계"]:::det
    G3 -->|"남은 6"| G45["가드 4·5 · 스키마 / 사실검증"]:::det
    G45 --> ACC["최종 반영 &nbsp;6개<br/>user_competency"]:::ok

    G1 -. "폐기 2" .-> X1(["kubernetes · kafka<br/>목록에 없음"]):::drop
    G2 -. "폐기 4" .-> X2(["aws · jpa · typescript · 중복<br/>근거가 원문에 없음"]):::drop

    classDef llm fill:#ffe0b2,stroke:#e65100,stroke-width:2px,color:#000
    classDef det fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000
    classDef drop fill:#eeeeee,stroke:#9e9e9e,stroke-dasharray:5 5,color:#616161
    classDef ok fill:#a5d6a7,stroke:#1b5e20,stroke-width:3px,color:#000
```

> **12개 중 6개 폐기.** 이 그림 하나가 "LLM 출력을 그대로 믿지 않는다"를 증명한다.
> STAR 보완(H-2)엔 별도 사실검증 가드가 하나 더 있다([star_enhance.py](../app/llm/star_enhance.py) `has_fabrication`).

---

## 그림 3 — 장애 주입: LLM이 전면 사망해도 서비스는 산다

선불 $5 소진(402)·401·429로 LLM이 죽으면 서킷브레이커가 열리고, **초록 경로만으로 로드맵이 완성**된다.

```mermaid
flowchart TB
    DEAD["LLM 전면 사망<br/>402 크레딧 소진 · 401 · 429"]:::dead
    DEAD --> BRK["AsyncCircuitBreaker OPEN<br/>직접 구현 · 실제 401로 검증"]:::fb

    BRK --> EX["역량 추출 → 빈 결과"]:::fb
    EX --> SELF["자가진단만으로 병합<br/>Core 정합성 스케줄러 60초"]:::fb
    SELF --> DET["사전 계산된 job_profile<br/>D 공식 · Lv 밴딩 (LLM 0)"]:::det
    DET --> DONE(["로드맵 생성 완주"]):::done

    BRK --> STAR["STAR 보완 → FAILED 발행"]:::fb
    STAR --> SDONE(["화면 스피너 안 멈춤"]):::done

    BRK --> G["문구 층2 → 층1 템플릿 폴백"]:::fb
    G --> GDONE(["규칙 기반 안내 문구 노출"]):::done

    classDef dead fill:#ffcdd2,stroke:#b71c1c,stroke-width:3px,color:#000
    classDef fb fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef det fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000
    classDef done fill:#a5d6a7,stroke:#1b5e20,stroke-width:3px,color:#000
```

> **AI가 죽어도 로드맵·퀘스트·문구가 전부 나온다.** 401 실호출로 세 경로(역량 []·STAR FAILED·문구 층1)
> 모두 완주 검증 완료(2026-07-29).

## 근거 (파일:줄)
- 3단 문서 파싱: [document.py:98](../app/competency/document.py#L98)
- OCR(비-LLM, 자격증명 없으면 스킵 — 데모 범위 밖): [ocr.py](../app/competency/ocr.py)
- Vision 키워드: [vision.py:41](../app/competency/vision.py#L41)
- GitHub 요약: [github.py](../app/competency/github.py)
- 역량 판정(닫힌 분류) + 가드 5중: [analyzer.py:128](../app/competency/analyzer.py#L128)
- D 공식(결정론): [scoring.py](../app/pipeline/scoring.py) · 값은 job_profile에 사전계산
- 층2 문구 개인화: [guidance.py:128](../app/pipeline/guidance.py#L128)
- STAR 보완: [star_enhance.py:124](../app/llm/star_enhance.py#L124)
- 공급자(서킷브레이커·구조화 출력·폴백): [provider.py](../app/llm/provider.py)

> **과장 금지:** F(직무 프로필 빌드) 오케스트레이터는 런타임 미실행 — D·레벨·선후관계는
> 시드 job_profile에 사전계산돼 있고 Core가 조립 시 읽는다. 위 "결정론 조립"은 그 사전계산
> 공식(scoring.py, 테스트됨)과 조립을 가리킨다.
