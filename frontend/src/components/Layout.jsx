import { NavLink, Outlet } from 'react-router-dom'

const navStyle = ({ isActive }) => ({
  padding: '8px 16px',
  borderRadius: 6,
  textDecoration: 'none',
  color: isActive ? '#fff' : 'var(--text)',
  background: isActive ? 'var(--accent)' : '#eceef1',
  border: `1px solid ${isActive ? 'var(--accent)' : '#9aa0a8'}`,
  fontWeight: 500,
})

export default function Layout() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 24px',
          borderBottom: '1px solid var(--border)',
          background: '#fff',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <img src="/logo.png" alt="SDC" style={{ height: 14, position: 'relative', top: 4 }} />
          <span style={{ fontWeight: 700, fontSize: 18 }}>AI-ADES</span>
        </div>
        {/* 메뉴 추가/변경 시 services/execution-agent/chat.py의 SYSTEM_GUIDE도 함께 업데이트할 것 */}
        <nav style={{ display: 'flex', gap: 8 }}>
          <NavLink to="/" style={navStyle} end>
            실험 조건
          </NavLink>
          <NavLink to="/approval" style={navStyle}>
            AI 제안 승인
          </NavLink>
          <NavLink to="/result" style={navStyle}>
            결과 보고
          </NavLink>
          <NavLink to="/recipes" style={navStyle}>
            레시피 조회
          </NavLink>
          <NavLink to="/history" style={navStyle}>
            실험 이력
          </NavLink>
          <NavLink to="/chat" style={navStyle}>
            AI 채팅
          </NavLink>
          <NavLink to="/admin" style={navStyle}>
            관리자
          </NavLink>
        </nav>
      </header>
      <main style={{ flex: 1, padding: 24 }}>
        <Outlet />
      </main>
    </div>
  )
}
