import { useEffect, useState } from 'react'
import { executionApi } from '../../api/client'

const CATEGORY_LABELS = { m1: 'M1 (Glass)', m2: 'M2 (Film)' }

export default function MaterialTypesSection() {
  const [types, setTypes] = useState([])
  const [error, setError] = useState(null)

  const [category, setCategory] = useState('m1')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [creating, setCreating] = useState(false)

  const [editingId, setEditingId] = useState(null)
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')

  const load = async () => {
    try {
      const res = await executionApi.get('/admin/material-types')
      setTypes(res.data.data.material_types)
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
      await executionApi.post('/admin/material-types', { category, name, description: description || null })
      setName('')
      setDescription('')
      await load()
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    } finally {
      setCreating(false)
    }
  }

  const handleToggleActive = async (type) => {
    setError(null)
    try {
      await executionApi.patch(`/admin/material-types/${type.id}`, { is_active: !type.is_active })
      await load()
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    }
  }

  const startEdit = (type) => {
    setEditingId(type.id)
    setEditName(type.name)
    setEditDescription(type.description ?? '')
  }

  const handleUpdate = async (id) => {
    setError(null)
    try {
      await executionApi.patch(`/admin/material-types/${id}`, { name: editName, description: editDescription || null })
      setEditingId(null)
      await load()
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    }
  }

  const handleDelete = async (type) => {
    if (!window.confirm(`"${type.name}" 소재 종류를 삭제하시겠습니까?`)) return
    setError(null)
    try {
      await executionApi.delete(`/admin/material-types/${type.id}`)
      await load()
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    }
  }

  return (
    <div>
      <h2>소재 종류 관리</h2>
      <p style={{ color: 'var(--text-muted)', marginBottom: 12 }}>
        실험 조건 입력 화면(M1/M2 소재 선택)에 표시될 소재 종류를 관리합니다. 비활성화하면 선택 목록에서 제외됩니다.
      </p>
      {error && <div className="banner banner-warning">{error}</div>}

      <div className="card" style={{ marginBottom: 16 }}>
        <h3>소재 종류 추가</h3>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            구분
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              style={{ padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 6, width: 140 }}
            >
              <option value="m1">M1 (Glass)</option>
              <option value="m2">M2 (Film)</option>
            </select>
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            이름
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="예: Borosilicate Glass"
              style={{ padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 6, width: 220 }}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            설명 (선택)
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="예: 고객사 B 전용 소재"
              style={{ padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 6, width: 260 }}
            />
          </label>
          <button className="btn btn-primary" disabled={!name || creating} onClick={handleCreate}>
            {creating ? <span className="spinner" /> : '추가'}
          </button>
        </div>
      </div>

      <div className="card">
        <h3>소재 종류 목록</h3>
        <table>
          <thead>
            <tr>
              <th>구분</th>
              <th>이름</th>
              <th>설명</th>
              <th>상태</th>
              <th>등록일</th>
              <th>관리</th>
            </tr>
          </thead>
          <tbody>
            {types.map((t) => (
              <tr key={t.id}>
                <td>{CATEGORY_LABELS[t.category] ?? t.category}</td>
                <td>
                  {editingId === t.id ? (
                    <input
                      type="text"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      style={{ padding: '4px 8px', width: 160 }}
                    />
                  ) : (
                    t.name
                  )}
                </td>
                <td>
                  {editingId === t.id ? (
                    <input
                      type="text"
                      value={editDescription}
                      onChange={(e) => setEditDescription(e.target.value)}
                      placeholder="설명 (선택)"
                      style={{ padding: '4px 8px', width: 220 }}
                    />
                  ) : (
                    t.description ?? '-'
                  )}
                </td>
                <td>
                  <span className={`pill ${t.is_active ? 'pill-ok' : 'pill-warn'}`}>
                    {t.is_active ? '활성' : '비활성'}
                  </span>
                </td>
                <td>{new Date(t.created_at).toLocaleString()}</td>
                <td>
                  {editingId === t.id ? (
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button className="btn btn-primary" disabled={!editName} onClick={() => handleUpdate(t.id)}>저장</button>
                      <button className="btn" onClick={() => setEditingId(null)}>취소</button>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button className="btn" onClick={() => startEdit(t)}>수정</button>
                      <button className="btn" onClick={() => handleToggleActive(t)}>
                        {t.is_active ? '비활성화' : '활성화'}
                      </button>
                      <button className="btn" onClick={() => handleDelete(t)}>삭제</button>
                    </div>
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
