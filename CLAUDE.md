# AI-ADES CLAUDE.md
## AI Autonomous Data Evaluation System — Claude Code 작업 지침서

> 이 파일은 Claude Code CLI가 자동으로 읽는 프로젝트 헌법입니다.
> 모든 작업은 이 지침을 우선 따릅니다.
> 세부 내용은 `docs/`로 분리되어 있으니 필요할 때만 열어보세요 (토큰 절약).
> 수정이 필요하면 claude.ai 채팅에서 요청하세요.

---

## 1. 프로젝트 개요

### 무엇을 만드는가
CO₂ 레이저로 Glass + Film 적층 소재를 절단할 때,
AI가 최적 레이저 조건을 자동으로 찾아주는 시스템.

### 핵심 목표
- 수동으로 30~50번 필요했던 실험을 **5~7번으로 단축**
- OK 판정 달성: **0μm < Depth ≤ 25μm**
- 운영자는 [승인] 버튼만 누르면 됨 (Human-in-the-Loop)

### 3단계 배포 계획
```
1단계: Surface Laptop Studio 1 (개발·테스트, 지금)
2단계: 고객사 워크스테이션 2대 (설치 테스트)
3단계: 고객사 CO₂ 레이저 설비 연동 (실운영)
```

---

## 2. 서비스 구성 (요약)

| 서비스 | 포트 | 용도 |
|---|---|---|
| data-prep-agent | 8010 | FastAPI, 데이터 수집·전처리 |
| modeling-agent | 8011 | FastAPI, AI 모델 학습·예측 |
| execution-agent | 8012 | FastAPI, Auto DOE·승인·레시피·Admin |
| frontend | 5173 | React + Vite, 운영자 UI |
| InfluxDB | 8086 | 시계열 데이터 저장 |
| MLflow | 5000 | 모델 실험 관리 |
| Grafana | 3010 | 실시간 모니터링 (3002 사용 금지) |
| Kafka | 9092 | 내부 전용, 호스트 미노출 |
| PostgreSQL | 5432 (내부) | ades_db (기존 pm-postgres 컨테이너 공유) |
| Qdrant | 6333 | ades_ 접두사 컬렉션 (기존 컨테이너 공유) |
| Ollama | 11434 | LLM 추론 (기존 컨테이너 공유) |

> 디렉토리 구조, 라이브러리 목록, LLM 멀티 프로바이더 상세 → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
> 서버 실행 명령, 환경변수 전체 목록 → [docs/OPERATIONS.md](docs/OPERATIONS.md)

---

## 3. 판정 기준 & 탐색 공간 (절대 변경 금지)

```python
# .env의 값을 사용할 것 (하드코딩 금지)
DEPTH_OK_MIN = 0.0    # μm 초과
DEPTH_OK_MAX = 25.0   # μm 이하
# 미가공: depth > 25μm
# OK    : 0 < depth ≤ 25μm  ← AI의 목표
# 과가공: depth = 0μm
# NG    : Defect 감지

QUALITY_SCORE = {"OK": 1, "미가공": 0, "과가공": -1, "NG": -2}

SEARCH_SPACE = {
    "speed":     {"type": "discrete", "values": [200, 500, 1000]},
    "defocus":   {"type": "discrete", "values": [0, 1, 2, 3, 4]},
    "frequency": {"type": "discrete", "values": [100, 200]},
    "power":     {"type": "continuous", "range": [2.8, 59.8]},
}
# 탐색 공간 외 값은 절대 제안하지 않음
```

> Excel POC 데이터 구조, 소재 종류(material_types), 학습 데이터 범위 등 상세 → [docs/DATA_SPEC.md](docs/DATA_SPEC.md)

---

## 4. 코딩 규칙

### 필수 규칙
```python
# 1. 한국어 주석 필수
def predict_quality(features: dict) -> dict:
    """
    레이저 가공 품질 예측
    Args: features - 입력 파라미터 (speed, defocus, frequency, power 등)
    Returns: 예측 결과 (pred_depth, pred_quality, confidence, shap_values)
    """
    pred_depth = depth_model.predict(...)

# 2. 환경변수는 반드시 .env에서 읽기
from dotenv import load_dotenv
DEPTH_OK_MAX = float(os.getenv("DEPTH_OK_MAX", 25.0))  # 하드코딩 금지

# 3. 판정 기준 함수화 (여러 곳에서 직접 비교 금지)
def judge_quality(depth: float) -> str:
    if depth > DEPTH_OK_MAX:   return "미가공"
    if depth == 0.0:           return "과가공"
    if depth <= DEPTH_OK_MAX:  return "OK"
    return "NG"

# 4. API 응답 형식 통일
return {
    "success": True,
    "data": {...},
    "message": "예측 완료"
}
```

### FastAPI 엔드포인트 명명 규칙
```
POST /data/upload           ← Excel 업로드
GET  /data/summary          ← 데이터 현황
POST /model/train           ← 모델 학습
POST /predict                ← 예측 요청
POST /doe/suggest            ← Auto DOE 제안
POST /doe/approve            ← 운영자 승인
POST /doe/reject             ← 거부
GET  /recipes                ← 레시피 조회
GET  /health                 ← 서비스 상태
```

### 금지 사항
```
✗ 판정 기준값(0, 25) 하드코딩
✗ API Key 코드에 직접 입력
✗ Grafana 포트 3002 사용 (3010만 사용)
✗ 기존 rag-pm-matcher 컨테이너 수정
✗ PostgreSQL pmdb 스키마 수정 (ades_db만 사용)
✗ 파일 한 개에 500줄 이상 작성 (분리할 것)
```

---

## 5. Phase별 진행 현황

각 Phase 완료 시 claude.ai 채팅에서 보고 후 다음 Phase 착수

| Phase | 내용 | 상태 |
|---|---|---|
| Phase 0 | 환경 세팅, Docker, DB 스키마 | ✅ 완료 |
| Phase 1 | Data Prep Agent, Excel 파싱 | ✅ 완료 |
| Phase 2 | Modeling Agent, XGBoost+SHAP | ✅ 완료 |
| Phase 3 | Execution Agent, Bayesian Opt, 승인/레시피 | ✅ 완료 |
| Phase 4 | React UI + Admin Console | 🔶 진행 중 (Admin Console 9개 섹션·소재 종류 관리·외삽 경고 구현 완료, E2E 통합테스트 잔여) |
| Phase 5 | 고객사 설치 테스트 | ⬜ 대기 |
| Phase 6 | 설비 연동 + 실데이터 학습 | ⬜ 대기 |

> Phase 4 Admin Console 상세 설계/구현 현황 → [docs/PHASE4_ADMIN_SPEC.md](docs/PHASE4_ADMIN_SPEC.md)

---

## 6. 참고 파일 경로

```
개발 플랜 전체:  docs/AI-ADES_개발플랜.md
POC 데이터:     data/raw/AI-ADES_POC_data_condition_results.xlsx
업로드 테스트 샘플: data/test/ (10건 x 10파일)
DB 스키마:      data/schema/schema.sql
포트 맵:        rag-pm-matcher_PORT_MAP.md 참조 (충돌 금지)
작업 일지:      WORKLOG.md
```

---

## 7. 작업 요청 방식

Claude Code에서 작업 요청 시 아래 형식으로 주면 가장 빠릅니다.

```
[Phase N] 작업명
목표: 무엇을 만들어야 하는지
입력: 어떤 데이터/파일이 있는지
출력: 어떤 파일/결과가 나와야 하는지
제약: 특별히 주의할 것
```

**예시:**
```
[Phase 1] Excel 파서 구현
목표: Data 시트 + Sheet1 조인 → PostgreSQL 적재
입력: data/raw/AI-ADES_POC_data_condition_results.xlsx
출력: services/data-prep-agent/excel_parser.py
제약: 행 순서 1:1 조인, '300-2' 비정형 No. 처리 포함
```
