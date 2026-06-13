import { useEffect, useState } from 'react'
import { executionApi } from '../../api/client'

// 산업용 콘솔 톤: 섹션 헤더 액센트 좌측 바, 폼 입력 각진 모서리, 목록 표 모노스페이스 — 타 화면과 통일
const sectionHeadStyle = {
  paddingLeft: 8,
  borderLeft: '3px solid var(--accent)',
  lineHeight: 1.2,
}
const formInputStyle = {
  padding: '8px 10px',
  border: '1px solid #c7cbd1',
  borderRadius: 4,
}
const readingStyle = {
  fontFamily: 'ui-monospace, Consolas, "Courier New", monospace',
}

export default function UsersSection() {
  const [users, setUsers] = useState([])
  const [error, setError] = useState(null)

  const [name, setName] = useState('')
  const [role, setRole] = useState('operator')
  const [password, setPassword] = useState('')
  const [creating, setCreating] = useState(false)

  const [editingId, setEditingId] = useState(null)
  const [editRole, setEditRole] = useState('')
  const [editPassword, setEditPassword] = useState('')

  const load = async () => {
    try {
      const res = await executionApi.get('/admin/users')
      setUsers(res.data.data.users)
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleCreate = async () => {
    setCreating(true)
    setError(null)
    try {
      await executionApi.post('/admin/users', { name, role, password })
      setName('')
      setPassword('')
      setRole('operator')
      await load()
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    } finally {
      setCreating(false)
    }
  }

  const startEdit = (user) => {
    setEditingId(user.id)
    setEditRole(user.role)
    setEditPassword('')
  }

  const handleUpdate = async (id) => {
    setError(null)
    try {
      const payload = { role: editRole }
      if (editPassword) payload.password = editPassword
      await executionApi.patch(`/admin/users/${id}`, payload)
      setEditingId(null)
      await load()
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    }
  }

  return (
    <div>
      <h2>사용자 관리</h2>
      {error && <div className="banner banner-warning">{error}</div>}

      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={sectionHeadStyle}>사용자 추가</h3>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            이름
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              style={{ ...formInputStyle, width: 160 }}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            역할
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              style={{ ...formInputStyle, width: 140 }}
            >
              <option value="operator">operator</option>
              <option value="admin">admin</option>
            </select>
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            비밀번호
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{ ...formInputStyle, width: 160 }}
            />
          </label>
          <button className="btn btn-primary" disabled={!name || !password || creating} onClick={handleCreate}>
            {creating ? <span className="spinner" /> : '추가'}
          </button>
        </div>
      </div>

      <div className="card">
        <h3 style={sectionHeadStyle}>사용자 목록</h3>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>이름</th>
              <th>역할</th>
              <th>생성일</th>
              <th>관리</th>
            </tr>
          </thead>
          <tbody style={readingStyle}>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.id}</td>
                <td>{u.name}</td>
                <td>
                  {editingId === u.id ? (
                    <select value={editRole} onChange={(e) => setEditRole(e.target.value)} style={{ padding: '4px 8px' }}>
                      <option value="operator">operator</option>
                      <option value="admin">admin</option>
                    </select>
                  ) : (
                    u.role
                  )}
                </td>
                <td>{new Date(u.created_at).toLocaleString()}</td>
                <td>
                  {editingId === u.id ? (
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      <input
                        type="password"
                        placeholder="새 비밀번호(선택)"
                        value={editPassword}
                        onChange={(e) => setEditPassword(e.target.value)}
                        style={{ padding: '4px 8px', width: 140 }}
                      />
                      <button className="btn btn-primary" onClick={() => handleUpdate(u.id)}>저장</button>
                      <button className="btn" onClick={() => setEditingId(null)}>취소</button>
                    </div>
                  ) : (
                    <button className="btn" onClick={() => startEdit(u)}>수정</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
