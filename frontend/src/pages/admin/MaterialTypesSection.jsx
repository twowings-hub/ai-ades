import { useEffect, useState } from 'react'
import { executionApi } from '../../api/client'

const CATEGORY_LABELS = { m1: 'M1 (Glass)', m2: 'M2 (Film)' }

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
        <h3 style={sectionHeadStyle}>소재 종류 추가</h3>
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            구분
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              style={{ ...formInputStyle, width: 140 }}
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
              style={{ ...formInputStyle, width: 220 }}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            설명 (선택)
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="예: 고객사 B 전용 소재"
              style={{ ...formInputStyle, width: 260 }}
            />
          </label>
          <button className="btn btn-primary" disabled={!name || creating} onClick={handleCreate}>
            {creating ? <span className="spinner" /> : '추가'}
          </button>
        </div>
      </div>

      <div className="card">
        <h3 style={sectionHeadStyle}>소재 종류 목록</h3>
        <div style={{ overflowX: 'auto', ...(types.length >= 10 ? { maxHeight: 400, overflowY: 'auto' } : {}) }}>
          <table className="admin-table" style={readingStyle}>
            <thead style={types.length >= 10 ? { position: 'sticky', top: 0, zIndex: 1 } : undefined}>
              <tr>
                <th style={{ width: 90 }}>구분</th>
                <th style={{ width: 180 }}>이름</th>
                <th style={{ width: 260 }}>설명</th>
                <th style={{ width: 70 }}>상태</th>
                <th style={{ width: 140 }}>등록일</th>
                <th style={{ width: 220 }}>관리</th>
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
                        style={{ padding: '2px 6px', width: 160 }}
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
                        style={{ padding: '2px 6px', width: 240 }}
                      />
                    ) : (
                      t.description ?? '-'
                    )}
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    <span className={`pill ${t.is_active ? 'pill-ok' : 'pill-warn'}`}>
                      {t.is_active ? '활성' : '비활성'}
                    </span>
                  </td>
                  <td>{new Date(t.created_at).toLocaleDateString()}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {editingId === t.id ? (
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'nowrap' }}>
                        <button className="btn btn-sm btn-primary" disabled={!editName} onClick={() => handleUpdate(t.id)}>저장</button>
                        <button className="btn btn-sm" onClick={() => setEditingId(null)}>취소</button>
                      </div>
                    ) : (
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'nowrap' }}>
                        <button className="btn btn-sm" onClick={() => startEdit(t)}>수정</button>
                        <button className="btn btn-sm" onClick={() => handleToggleActive(t)}>
                          {t.is_active ? '비활성화' : '활성화'}
                        </button>
                        <button className="btn btn-sm" onClick={() => handleDelete(t)}>삭제</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
