import { NavLink, Outlet } from 'react-router-dom'

// 산업용 콘솔 톤: 채워진 알약 대신 각진(4px) 탭 + 액센트 밑선/배경으로 현재 위치를 표시
const navStyle = ({ isActive }) => ({
  padding: '7px 14px',
  borderRadius: 4,
  textDecoration: 'none',
  fontSize: 14,
  letterSpacing: '0.01em',
  fontWeight: isActive ? 600 : 500,
  color: isActive ? 'var(--accent)' : 'var(--text-muted)',
  background: isActive ? 'rgba(37,99,235,0.08)' : 'transparent',
  border: `1px solid ${isActive ? 'rgba(37,99,235,0.35)' : 'transparent'}`,
  transition: 'color 0.15s, background 0.15s, border-color 0.15s',
})

// 워드마크용 모노스페이스 스택 (외부 폰트 미사용 → 오프라인 설비에서도 안전)
const monoStack = 'ui-monospace, "Cascadia Code", Consolas, "Courier New", monospace'

export default function Layout() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 24px',
          borderTop: '2px solid var(--accent)',
          borderBottom: '1px solid var(--border)',
          background: '#fff',
          boxShadow: '0 1px 2px rgba(15, 23, 42, 0.04)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <img src="/logo.png" alt="SDC" style={{ height: 16, display: 'block' }} />
          {/* 로고와 워드마크 사이 세로 구분선 (산업용 계기판 느낌의 정밀한 디테일) */}
          <div style={{ width: 1, height: 22, background: 'var(--border)' }} />
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.15 }}>
            <span style={{ fontFamily: monoStack, fontWeight: 700, fontSize: 17, letterSpacing: '0.06em' }}>
              AI-ADES
            </span>
            <span
              style={{
                fontSize: 9,
                letterSpacing: '0.18em',
                textTransform: 'uppercase',
                color: 'var(--text-muted)',
              }}
            >
              Laser Process Console
            </span>
          </div>
        </div>
        {/* 메뉴 추가/변경 시 services/execution-agent/chat.py의 SYSTEM_GUIDE도 함께 업데이트할 것 */}
        <nav style={{ display: 'flex', gap: 4 }}>
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
