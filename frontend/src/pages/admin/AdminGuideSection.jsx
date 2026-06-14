// 관리자 콘솔 사용 안내 (정적 가이드 — API 호출 없음)
// 산업용 콘솔 톤: 섹션 헤더 액센트 좌측 바
const sectionHeadStyle = {
  paddingLeft: 8,
  borderLeft: '3px solid var(--accent)',
  lineHeight: 1.2,
}

// 각 관리자 메뉴: 용도 + 꼭 알아야 할 점
const MENUS = [
  {
    name: '시스템 상태',
    use: '서비스 헬스체크(ok/degraded/down), 최근 모델 학습 지표(R²/F1), CPU·RAM·Disk 사용량을 한눈에 봅니다.',
    note: '30초마다 자동 갱신. 어떤 서비스가 down이면 「서비스 관리」에서 재시작하세요.',
  },
  {
    name: '서비스 관리',
    use: '각 서비스(컨테이너)를 재시작합니다.',
    note: 'execution-agent(자기 자신)는 재시작 불가(버튼 비활성). 재시작 중 잠시 해당 기능이 멈출 수 있습니다.',
  },
  {
    name: 'LLM 모델 선택',
    use: 'AI 설명·채팅에 쓰는 LLM 프로바이더/모델을 전환합니다(ollama=무료·로컬, claude/openai=과금).',
    note: '전환 후 「연결 테스트」로 응답을 확인하세요. 폐쇄망에서는 ollama(로컬)만 사용 가능합니다.',
  },
  {
    name: '모델 재학습',
    use: '누적된 실험 데이터로 AI 모델을 다시 학습시킵니다(수동 시작 + 자동 임계값).',
    note: '학습은 수 분 소요됩니다(Optuna+XGBoost). 진행 중 중복 시작 불가. 자동 재학습은 누적 건수가 임계값을 넘으면 시작됩니다.',
  },
  {
    name: '판정 기준 설정',
    use: '품질 OK 판정 범위(Depth)와 Auto DOE 탐색 공간(Power/Speed/Defocus)을 조정합니다.',
    note: '⚠ 기준값(0μm 초과~25μm 이하)과 탐색 공간은 공정 핵심값입니다. 합의 없이 바꾸면 AI 제안·판정이 전부 달라집니다.',
    warn: true,
  },
  {
    name: '소재 종류 관리',
    use: '실험 조건 화면의 M1(Glass)/M2(Film) 소재 선택 목록을 추가·수정·활성화합니다.',
    note: '비활성화하면 운영자 선택 목록에서 빠집니다. 삭제는 신중히(과거 데이터 참조 가능).',
  },
  {
    name: '사용자 관리',
    use: '운영자/관리자 계정을 추가하고 역할·비밀번호를 변경합니다.',
    note: 'operator=운영 화면, admin=관리자 콘솔까지. 비밀번호는 분실 시 여기서 재설정합니다.',
  },
  {
    name: '알림 설정',
    use: '수신 메일 주소와 알림을 켤 이벤트(OK 판정 / 가공 실패 / 모델 성능 저하)를 고릅니다.',
    note: '체크된 이벤트만 자동 발송됩니다. 메일이 실제로 나가려면 「메일 서버 설정」이 되어 있어야 합니다.',
  },
  {
    name: '메일 서버 설정',
    use: '알림 메일을 보낼 SMTP 서버를 설정합니다. 저장값은 .env보다 우선하며 재빌드 없이 즉시 반영됩니다.',
    note: '폐쇄망에서는 사내(LAN) 메일서버만 사용하세요. 비워두면 메일은 발송되지 않고 알림은 Grafana·기록으로만 남습니다. 「연결 테스트」는 알림 설정의 수신 메일로 보냅니다.',
  },
  {
    name: '감사 로그',
    use: '승인·거부·설정 변경·재학습·데이터 삭제 등 모든 관리 작업 이력을 조회합니다.',
    note: 'action_type/operator로 검색, CSV로 내보낼 수 있습니다. 문제 추적·책임 확인용입니다.',
  },
  {
    name: '데이터 관리',
    use: 'DB 백업(pg_dump), 실험 CSV 내보내기, 학습 데이터 Excel 업로드, 테스트 데이터 정리를 합니다.',
    note: '⚠ 「테스트 데이터 정리」의 삭제는 영구이며 되돌릴 수 없습니다. 재학습에 반영된 데이터·Excel 원본은 안전을 위해 삭제 대상에서 제외됩니다.',
    warn: true,
  },
]

export default function AdminGuideSection() {
  return (
    <div style={{ maxWidth: 900 }}>
      <h2>사용 안내</h2>
      <p style={{ color: 'var(--text-muted)' }}>
        관리자 콘솔 각 메뉴의 용도와 꼭 알아야 할 주의사항입니다. 처음 사용하시거나 인수인계 시 참고하세요.
      </p>

      <div className="banner banner-warning">
        <strong>먼저 꼭 알아두세요</strong>
        <ul style={{ margin: '8px 0 0', paddingLeft: 18, lineHeight: 1.7, fontWeight: 400 }}>
          <li><b>판정 기준값(0/25μm)·탐색 공간</b>은 공정 핵심값 — 합의 없이 변경 금지(AI 제안·판정 전체에 영향).</li>
          <li><b>테스트 데이터 삭제</b>는 영구이며 되돌릴 수 없습니다.</li>
          <li><b>폐쇄망(외부 접속 불가)</b>에서는 외부 메일/Slack·외부 LLM 사용 불가 → 사내 SMTP·로컬 ollama 사용.</li>
          <li><b>모델 재학습</b>은 수 분 소요되며, 진행 중에는 예측 정확도가 일시적으로 달라질 수 있습니다.</li>
        </ul>
      </div>

      <div className="card">
        <h3 style={sectionHeadStyle}>메뉴별 사용법</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 4 }}>
          {MENUS.map((m) => (
            <div
              key={m.name}
              style={{
                borderLeft: `3px solid ${m.warn ? 'var(--warning)' : 'var(--border)'}`,
                paddingLeft: 12,
              }}
            >
              <div style={{ fontWeight: 700, marginBottom: 2 }}>{m.name}</div>
              <div style={{ fontSize: 14, marginBottom: 4 }}>{m.use}</div>
              <div style={{ fontSize: 13, color: m.warn ? 'var(--warning)' : 'var(--text-muted)', lineHeight: 1.6 }}>
                {m.note}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3 style={sectionHeadStyle}>전형적인 운영 흐름</h3>
        <ol style={{ margin: '4px 0 0', paddingLeft: 20, lineHeight: 1.8, fontSize: 14 }}>
          <li>운영자가 <b>실험 조건</b> 입력 → AI가 <b>Auto DOE</b>로 가공 조건 제안</li>
          <li>운영자가 <b>AI 제안 승인</b>(또는 수정 후 승인) → 실제 레이저 가공</li>
          <li>실측 Kerf/Depth를 <b>결과 보고</b>에 입력 → OK면 레시피 저장, 실패면 다음 제안</li>
          <li>관리자는 여기서 <b>시스템 상태·데이터·재학습·알림</b>을 관리하고, 이상 시 <b>감사 로그</b>로 추적</li>
        </ol>
      </div>
    </div>
  )
}
