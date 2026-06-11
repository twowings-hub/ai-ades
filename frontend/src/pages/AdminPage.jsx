import { useState } from 'react'
import SystemStatusSection from './admin/SystemStatusSection'
import ServiceManagementSection from './admin/ServiceManagementSection'
import LlmSection from './admin/LlmSection'
import RetrainSection from './admin/RetrainSection'
import CriteriaSection from './admin/CriteriaSection'
import UsersSection from './admin/UsersSection'
import NotificationsSection from './admin/NotificationsSection'
import AuditLogsSection from './admin/AuditLogsSection'
import DataManagementSection from './admin/DataManagementSection'
import MaterialTypesSection from './admin/MaterialTypesSection'

const SECTIONS = [
  { key: 'status', label: '시스템 상태', Component: SystemStatusSection },
  { key: 'services', label: '서비스 관리', Component: ServiceManagementSection },
  { key: 'llm', label: 'LLM 모델 선택', Component: LlmSection },
  { key: 'retrain', label: '모델 재학습', Component: RetrainSection },
  { key: 'criteria', label: '판정 기준 설정', Component: CriteriaSection },
  { key: 'material-types', label: '소재 종류 관리', Component: MaterialTypesSection },
  { key: 'users', label: '사용자 관리', Component: UsersSection },
  { key: 'notifications', label: '알림 설정', Component: NotificationsSection },
  { key: 'audit', label: '감사 로그', Component: AuditLogsSection },
  { key: 'data', label: '데이터 관리', Component: DataManagementSection },
]

export default function AdminPage() {
  const [active, setActive] = useState(SECTIONS[0].key)
  const ActiveComponent = SECTIONS.find((s) => s.key === active)?.Component ?? (() => null)

  return (
    <div style={{ display: 'flex', gap: 16 }}>
      <aside className="card" style={{ width: 200, flexShrink: 0, padding: 12 }}>
        <h3 style={{ marginBottom: 12 }}>관리자 콘솔</h3>
        <nav style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {SECTIONS.map((s) => (
            <button
              key={s.key}
              onClick={() => setActive(s.key)}
              className={`btn ${active === s.key ? 'btn-primary' : ''}`}
              style={{ textAlign: 'left', border: active === s.key ? undefined : 'none', background: active === s.key ? undefined : 'transparent' }}
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
