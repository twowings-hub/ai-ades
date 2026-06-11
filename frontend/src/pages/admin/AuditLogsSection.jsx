import { useEffect, useState } from 'react'
import { executionApi } from '../../api/client'

const LIMIT = 20

export default function AuditLogsSection() {
  const [logs, setLogs] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [actionType, setActionType] = useState('')
  const [operator, setOperator] = useState('')
  const [error, setError] = useState(null)

  const load = async () => {
    try {
      const res = await executionApi.get('/admin/audit-logs', {
        params: {
          page,
          limit: LIMIT,
          action_type: actionType || undefined,
          operator: operator || undefined,
        },
      })
      setLogs(res.data.data.logs)
      setTotal(res.data.data.total)
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page])

  const handleSearch = () => {
    setPage(1)
    load()
  }

  const handleExportCsv = () => {
    const header = ['id', 'action_type', 'operator', 'description', 'old_value', 'new_value', 'created_at']
    const rows = logs.map((log) =>
      header.map((key) => {
        const value = log[key]
        const text = typeof value === 'object' && value !== null ? JSON.stringify(value) : (value ?? '')
        return `"${String(text).replace(/"/g, '""')}"`
      }).join(',')
    )
    const csv = [header.join(','), ...rows].join('\n')
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `audit_logs_page${page}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const totalPages = Math.max(1, Math.ceil(total / LIMIT))

  return (
    <div>
      <h2>감사 로그</h2>
      {error && <div className="banner banner-warning">{error}</div>}

      <div className="card">
        <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            action_type
            <input
              type="text"
              value={actionType}
              onChange={(e) => setActionType(e.target.value)}
              placeholder="예: approval, llm_change"
              style={{ padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 6, width: 200 }}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            operator
            <input
              type="text"
              value={operator}
              onChange={(e) => setOperator(e.target.value)}
              style={{ padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 6, width: 160 }}
            />
          </label>
          <button className="btn btn-primary" onClick={handleSearch}>검색</button>
          <button className="btn" onClick={handleExportCsv}>CSV 내보내기 (현재 페이지)</button>
        </div>

        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>구분</th>
              <th>운영자</th>
              <th>설명</th>
              <th>시각</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => (
              <tr key={log.id}>
                <td>{log.id}</td>
                <td>{log.action_type}</td>
                <td>{log.operator}</td>
                <td>{log.description}</td>
                <td>{new Date(log.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div style={{ display: 'flex', gap: 8, marginTop: 16, alignItems: 'center' }}>
          <button className="btn" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>이전</button>
          <span>{page} / {totalPages}</span>
          <button className="btn" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>다음</button>
          <span style={{ color: 'var(--text-muted)' }}>총 {total}건</span>
        </div>
      </div>
    </div>
  )
}
