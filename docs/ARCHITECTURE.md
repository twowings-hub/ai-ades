# AI-ADES 아키텍처 상세

> CLAUDE.md 2장의 상세 버전. 디렉토리 구조, 라이브러리, LLM 멀티 프로바이더 설정.

---

## 기존 rag-pm-matcher에서 공유 (새로 띄우지 않음)

| 서비스 | 포트 | 용도 |
|---|---|---|
| PostgreSQL | 5432 (내부) | ades_db 스키마 신규 추가 |
| Qdrant | 6333 | ades_ 접두사 컬렉션 분리 |
| Ollama | 11434 | LLM 추론 (Qwen2.5:7b-instruct) |

## AI-ADES 신규 서비스

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

## AI/ML 라이브러리

```
xgboost, scikit-learn, shap, optuna   ← 품질 예측
torch (CPU 모드), botorch              ← 이상감지, Auto DOE
mlflow                                 ← 실험 관리
influxdb-client                        ← 시계열 DB
kafka-python                           ← 데이터 파이프라인
```

## LLM 멀티 프로바이더 (기존 rag-pm-matcher 패턴 재활용)

```python
LLM_PROVIDER=ollama   # 기본 (로컬, 무료)
LLM_PROVIDER=claude   # Claude API
LLM_PROVIDER=openai   # ChatGPT API
# .env의 LLM_PROVIDER 값으로 런타임 전환
```

Admin Console에서 provider/model을 즉시 전환 가능 (`/admin/llm/switch`).
- `provider=claude` → 모델: `claude-sonnet-4-6`
- `provider=openai` → 모델: `gpt-4o`, `gpt-4o-mini`
- `provider=ollama` → `ollama list` 결과(설치된 모델) 동적 조회

---

## 디렉토리 구조

```
D:\Claude\ai-ades\
├── CLAUDE.md                      ← 작업 지침서 (요약)
├── docs/                          ← 상세 문서 (이 폴더)
├── docker-compose.yml             ← 로컬 개발용
├── docker-compose.prod.yml        ← 고객사 설치용 (GPU 포함)
├── .env                           ← 환경변수 (절대 git push 금지)
├── .env.example                   ← 환경변수 템플릿
├── .gitignore
│
├── services/
│   ├── data-prep-agent/           ← Port 8010
│   │   ├── main.py
│   │   ├── excel_parser.py        ← Data+Sheet1 행순서 조인
│   │   ├── preprocessor.py        ← quality_score 파생, 이상값 처리
│   │   ├── influx_writer.py       ← InfluxDB 적재
│   │   └── plasma_parser.py       ← Plasma CSV (Phase 6)
│   │
│   ├── modeling-agent/            ← Port 8011
│   │   ├── main.py
│   │   ├── feature_engineering.py
│   │   ├── xgboost_pipeline.py    ← kerf/depth/quality 3개 모델
│   │   ├── lstm_model.py          ← Plasma 시계열 (Phase 6)
│   │   ├── shap_analyzer.py
│   │   ├── optuna_tuner.py
│   │   └── mlflow_tracker.py
│   │
│   ├── execution-agent/           ← Port 8012
│   │   ├── main.py                ← /doe/*, /recipes, /material-types
│   │   ├── bayesian_opt.py        ← BoTorch Auto DOE
│   │   ├── recipe_db.py           ← 레시피 조회/저장 (m1_glass/m2_film 포함)
│   │   ├── approval.py            ← 승인/거부 + audit_logs
│   │   ├── llm_explainer.py       ← LLM 멀티 프로바이더
│   │   ├── material_types.py      ← 소재 종류 CRUD (/admin/material-types)
│   │   ├── admin.py                ← Admin Console API (시스템상태/LLM/재학습/설정/사용자/알림)
│   │   ├── admin_data.py          ← Admin 데이터관리/감사로그/서비스재시작
│   │   ├── env_utils.py           ← .env 런타임 갱신
│   │   ├── db.py                  ← DB 커넥션, judge_quality
│   │   └── responses.py           ← 공통 응답 포맷
│   │
│   └── monitoring/
│       └── grafana/dashboards/
│
├── frontend/                      ← Port 5173
│   └── src/
│       ├── pages/
│       │   ├── ExperimentPage.jsx ← 조건 입력 (M1/M2 소재+길이+두께, 외삽 경고)
│       │   ├── ApprovalPage.jsx   ← AI 제안 승인 (핵심 화면)
│       │   ├── ResultPage.jsx     ← 결과 보고
│       │   ├── AdminPage.jsx      ← 관리자 콘솔 (9개 섹션)
│       │   └── admin/             ← 섹션별 컴포넌트 (LlmSection, MaterialTypesSection 등)
│       └── context/SessionContext.jsx  ← 세션 상태 (소재 조건, 제안, 승인 결과)
│
└── data/
    ├── raw/                       ← 원본 Excel (변경 금지)
    ├── test/                      ← 업로드 테스트용 샘플 Excel
    └── schema/schema.sql          ← DB 스키마
```
