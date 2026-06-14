import { useState } from 'react'
import { ADMIN_AUTH_ENABLED, ADMIN_PASSWORD } from '../config/adminAuth'
import AdminGuideSection from './admin/AdminGuideSection'
import SystemStatusSection from './admin/SystemStatusSection'
import ServiceManagementSection from './admin/ServiceManagementSection'
import LlmSection from './admin/LlmSection'
import RetrainSection from './admin/RetrainSection'
import CriteriaSection from './admin/CriteriaSection'
import UsersSection from './admin/UsersSection'
import NotificationsSection from './admin/NotificationsSection'
import MailServerSection from './admin/MailServerSection'
import AuditLogsSection from './admin/AuditLogsSection'
import DataManagementSection from './admin/DataManagementSection'
import MaterialTypesSection from './admin/MaterialTypesSection'

// 산업용 콘솔 톤: 좌측 탭은 네비 탭과 동일한 액센트 틴트 활성 언어로 통일, 헤더는 액센트 좌측 바
const sectionHeadStyle = {
  paddingLeft: 8,
  borderLeft: '3px solid var(--accent)',
  lineHeight: 1.2,
}
const tabStyle = (isActive) => ({
  textAlign: 'left',
  borderRadius: 4,
  padding: '7px 12px',
  fontSize: 14,
  whiteSpace: 'nowrap',
  fontWeight: isActive ? 600 : 500,
  color: isActive ? 'var(--accent)' : 'var(--text-muted)',
  background: isActive ? 'rgba(37, 99, 235, 0.08)' : 'transparent',
  border: `1px solid ${isActive ? 'rgba(37, 99, 235, 0.35)' : 'transparent'}`,
  transition: 'color 0.15s, background 0.15s, border-color 0.15s',
})

const SECTIONS = [
  { key: 'guide', label: '사용 안내', Component: AdminGuideSection },
  { key: 'status', label: '시스템 상태', Component: SystemStatusSection },
  { key: 'services', label: '서비스 관리', Component: ServiceManagementSection },
  { key: 'llm', label: 'LLM 모델 선택', Component: LlmSection },
  { key: 'retrain', label: '모델 재학습', Component: RetrainSection },
  { key: 'criteria', label: '판정 기준 설정', Component: CriteriaSection },
  { key: 'material-types', label: '소재 종류 관리', Component: MaterialTypesSection },
  { key: 'users', label: '사용자 관리', Component: UsersSection },
  { key: 'notifications', label: '알림 설정', Component: NotificationsSection },
  { key: 'mail-server', label: '메일 서버 설정', Component: MailServerSection },
  { key: 'audit', label: '감사 로그', Component: AuditLogsSection },
  { key: 'data', label: '데이터 관리', Component: DataManagementSection },
]

// 관리자 콘솔 접근 비밀번호 게이트
// ADMIN_AUTH_ENABLED=false 이면(테스트 중) 비밀번호 없이 통과한다.
function AdminGate({ children }) {
  const [authed, setAuthed] = useState(
    () => !ADMIN_AUTH_ENABLED || sessionStorage.getItem('ades_admin_authed') === '1',
  )
  const [pw, setPw] = useState('')
  const [error, setError] = useState(false)

  if (authed) return children

  const submit = (e) => {
    e.preventDefault()
    if (pw === ADMIN_PASSWORD) {
      // 같은 탭 세션 동안은 다시 묻지 않는다
      sessionStorage.setItem('ades_admin_authed', '1')
      setAuthed(true)
    } else {
      setError(true)
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: '60px auto' }}>
      <div className="card">
        <h2 style={{ marginBottom: 4 }}>관리자 인증</h2>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 0 }}>
          관리자 콘솔에 접근하려면 비밀번호를 입력하세요.
        </p>
        <form onSubmit={submit}>
          <input
            type="password"
            autoFocus
            value={pw}
            onChange={(e) => { setPw(e.target.value); setError(false) }}
            placeholder="비밀번호"
            style={{ width: '100%', padding: '8px 10px', border: '1px solid #c7cbd1', borderRadius: 4 }}
          />
          {error && (
            <div className="banner banner-warning" style={{ marginTop: 10, marginBottom: 0 }}>
              비밀번호가 올바르지 않습니다.
            </div>
          )}
          <button className="btn btn-primary" type="submit" style={{ marginTop: 12, width: '100%' }}>
            확인
          </button>
        </form>
      </div>
    </div>
  )
}

export default function AdminPage() {
  return (
    <AdminGate>
      <AdminConsole />
    </AdminGate>
  )
}

function AdminConsole() {
  const [active, setActive] = useState(SECTIONS[0].key)
  const ActiveComponent = SECTIONS.find((s) => s.key === active)?.Component ?? (() => null)

  return (
    <div style={{ display: 'flex', gap: 16 }}>
      <aside className="card" style={{ width: 200, flexShrink: 0, padding: 12 }}>
        <h3 style={{ ...sectionHeadStyle, marginBottom: 12 }}>관리자 콘솔</h3>
        <nav style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {SECTIONS.map((s) => (
            <button
              key={s.key}
              onClick={() => setActive(s.key)}
              style={tabStyle(active === s.key)}
            >
              {s.label}
            </button>
          ))}
        </nav>
      </aside>

      <div style={{ flex: 1, minWidth: 0 }}>
        <ActiveComponent />
      </div>
    </div>
  )
}
