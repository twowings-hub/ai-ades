import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { executionApi } from '../api/client'
import { useSession } from '../context/SessionContext'

const PARAM_LABELS = {
  speed: 'Speed',
  defocus: 'Defocus',
  frequency: 'Frequency',
  power: 'Power',
}

const QUALITY_PILL = {
  OK: 'pill-ok',
  미가공: 'pill-warn',
  과가공: 'pill-warn',
  NG: 'pill-danger',
}

export default function ApprovalPage() {
  const navigate = useNavigate()
  const { session, setApproval } = useSession()
  const suggestion = session.suggestion

  const [editing, setEditing] = useState(false)
  const [editedParams, setEditedParams] = useState(suggestion?.suggested_params ?? {})
  const [showRejectModal, setShowRejectModal] = useState(false)
  const [rejectReason, setRejectReason] = useState('')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  if (!suggestion) {
    return (
      <div className="card">
        <p>제안 정보가 없습니다. 먼저 실험 조건을 입력해주세요.</p>
        <button className="btn btn-primary" onClick={() => navigate('/')}>
          실험 조건 입력으로 이동
        </button>
      </div>
    )
  }

  const shapData = Object.entries(suggestion.shap_values ?? {})
    .slice(0, 5)
    .map(([feature, value]) => ({ feature, value }))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))

  const handleApprove = async (paramsOverride) => {
    setLoading(true)
    setError(null)
    try {
      const res = await executionApi.post('/doe/approve', {
        suggestion_id: suggestion.suggestion_id,
        operator_name: session.operatorName,
        final_params: paramsOverride ?? null,
      })
      setApproval({
        ...res.data.data,
        final_params: paramsOverride ?? suggestion.suggested_params,
      })
      navigate('/result')
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleReject = async () => {
    setLoading(true)
    setError(null)
    try {
      await executionApi.post('/doe/reject', {
        suggestion_id: suggestion.suggestion_id,
        operator_name: session.operatorName,
        reason: rejectReason,
      })
      setShowRejectModal(false)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2>AI 제안 승인 ({suggestion.doe_attempt}차)</h2>
      {error && <div className="banner banner-warning">{error}</div>}

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        {/* 좌측 패널 */}
        <div className="card" style={{ flex: 1 }}>
          <h3>AI 제안 파라미터</h3>
          <table>
            <thead>
              <tr>
                <th>항목</th>
                <th>값</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(PARAM_LABELS).map(([key, label]) => (
                <tr key={key}>
                  <td>{label}</td>
                  <td>
                    {editing ? (
                      <input
                        type="number"
                        step="0.1"
                        value={editedParams[key]}
                        onChange={(e) =>
                          setEditedParams((prev) => ({ ...prev, [key]: parseFloat(e.target.value) }))
                        }
                        style={{ width: 120, padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 4 }}
                      />
                    ) : (
                      editedParams[key]
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3 style={{ marginTop: 24 }}>예측 결과</h3>
          <table>
            <tbody>
              <tr>
                <td>예측 Kerf</td>
                <td>{suggestion.pred_kerf} μm</td>
              </tr>
              <tr>
                <td>예측 Depth</td>
                <td>{suggestion.pred_depth} μm</td>
              </tr>
              <tr>
                <td>예측 판정</td>
                <td>
                  <span className={`pill ${QUALITY_PILL[suggestion.pred_quality] ?? 'pill-muted'}`}>
                    {suggestion.pred_quality}
                  </span>
                </td>
              </tr>
              <tr>
                <td>신뢰도</td>
                <td>{(suggestion.confidence * 100).toFixed(1)}%</td>
              </tr>
            </tbody>
          </table>

          <h3 style={{ marginTop: 24 }}>SHAP 영향도 (Depth, 상위 5개)</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={shapData} layout="vertical" margin={{ left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" />
              <YAxis type="category" dataKey="feature" width={90} />
              <Tooltip />
              <Bar dataKey="value">
                {shapData.map((entry, idx) => (
                  <Cell key={idx} fill={entry.value >= 0 ? 'var(--accent)' : 'var(--danger)'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* 우측 패널 */}
        <div className="card" style={{ flex: 1 }}>
          <h3>AI 설명</h3>
          <div
            style={{
              background: 'var(--bg)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              padding: 14,
              minHeight: 120,
              whiteSpace: 'pre-wrap',
              color: suggestion.llm_explanation ? 'var(--text)' : 'var(--text-muted)',
            }}
          >
            {suggestion.llm_explanation || 'LLM 설명을 생성하지 못했습니다.'}
          </div>

          <div style={{ display: 'flex', gap: 8, marginTop: 24 }}>
            {!editing ? (
              <>
                <button className="btn btn-success" disabled={loading} onClick={() => handleApprove(null)}>
                  ✓ 승인
                </button>
                <button className="btn" disabled={loading} onClick={() => setEditing(true)}>
                  ✎ 수정 후 승인
                </button>
                <button className="btn btn-danger" disabled={loading} onClick={() => setShowRejectModal(true)}>
                  ✗ 거부
                </button>
              </>
            ) : (
              <>
                <button className="btn btn-success" disabled={loading} onClick={() => handleApprove(editedParams)}>
                  ✓ 수정값으로 승인
                </button>
                <button className="btn" disabled={loading} onClick={() => { setEditing(false); setEditedParams(suggestion.suggested_params) }}>
                  취소
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {showRejectModal && (
        <div className="modal-overlay">
          <div className="modal">
            <h3>거부 사유 입력</h3>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              rows={4}
              style={{ width: '100%', padding: 8, border: '1px solid var(--border)', borderRadius: 6, marginTop: 8 }}
              placeholder="거부 사유를 2자 이상 입력하세요"
            />
            <div style={{ display: 'flex', gap: 8, marginTop: 16, justifyContent: 'flex-end' }}>
              <button className="btn" onClick={() => setShowRejectModal(false)}>
                취소
              </button>
              <button className="btn btn-danger" disabled={loading || rejectReason.trim().length < 2} onClick={handleReject}>
                거부 확정
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
