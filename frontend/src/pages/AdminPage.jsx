import { useState } from 'react'
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

export default function AdminPage() {
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
