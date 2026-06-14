import { useEffect, useState } from 'react'
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

// SHAP 그래프의 feature 키를 사람이 읽기 쉬운 한국어 이름으로 변환
const FEATURE_LABELS = {
  speed: 'Speed',
  defocus: 'Defocus',
  frequency: 'Frequency',
  power: 'Power',
  thickness: 'Thickness',
  m1_length: 'M1 Length',
  m2_length: 'M2 Length',
  energy_density: 'Energy Density',
  normalized_power: 'Normalized Power',
  power_x_defocus: 'Power×Defocus',
  freq_x_power: 'Frequency×Power',
  thickness_ratio: 'Thickness Ratio',
}

// 산업용 콘솔 톤: 섹션 헤더 액센트 좌측 바, 수치 판독값은 모노스페이스(계기판 느낌) — 실험 조건 화면과 통일
const sectionHeadStyle = {
  paddingLeft: 8,
  borderLeft: '3px solid var(--accent)',
  lineHeight: 1.2,
}
const readingStyle = {
  fontFamily: 'ui-monospace, Consolas, "Courier New", monospace',
}

export default function ApprovalPage() {
  const navigate = useNavigate()
  const { session, setSuggestion, setApproval } = useSession()
  const suggestion = session.suggestion

  const [editing, setEditing] = useState(false)
  const [editedParams, setEditedParams] = useState(suggestion?.suggested_params ?? {})
  const [showRejectModal, setShowRejectModal] = useState(false)
  const [rejectReason, setRejectReason] = useState('')

  // 수정 후 승인 시 재예측 결과 (없으면 AI 최초 제안값을 사용)
  const [predOverride, setPredOverride] = useState(null)
  const [lastPredictedParams, setLastPredictedParams] = useState(suggestion?.suggested_params ?? {})
  const [repredictLoading, setRepredictLoading] = useState(false)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // LLM 설명은 백그라운드에서 생성되므로 완료될 때까지 폴링한다
  useEffect(() => {
    if (!suggestion || suggestion.llm_explanation_status !== 'pending') return

    const interval = setInterval(async () => {
      try {
        const res = await executionApi.get(`/doe/explanation/${suggestion.suggestion_id}`)
        const { llm_explanation, status } = res.data.data
        if (status === 'ready') {
          setSuggestion({ ...suggestion, llm_explanation, llm_explanation_status: status })
          clearInterval(interval)
        }
      } catch {
        clearInterval(interval)
      }
    }, 2000)

    return () => clearInterval(interval)
  }, [suggestion, setSuggestion])

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

  // 재예측 결과가 있으면 그 값을, 없으면 AI 최초 제안의 예측값을 화면에 표시한다
  const displayPred = predOverride ?? {
    pred_kerf: suggestion.pred_kerf,
    pred_depth: suggestion.pred_depth,
    pred_quality: suggestion.pred_quality,
    confidence: suggestion.confidence,
    shap_values: suggestion.shap_values,
  }

  // 수정 모드에서 마지막 재예측 시점의 값과 현재 입력값이 다르면 "재예측 필요" 경고를 표시한다
  const isStale = editing && JSON.stringify(editedParams) !== JSON.stringify(lastPredictedParams)

  const shapData = Object.entries(displayPred.shap_values ?? {})
    .slice(0, 5)
    .map(([feature, value]) => ({ feature, label: FEATURE_LABELS[feature] ?? feature, value }))
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
      // 재예측을 했다면, 결과 보고 화면의 샘플값도 재예측 결과를 기준으로 채워지도록 갱신
      if (predOverride) {
        setSuggestion({ ...suggestion, ...predOverride })
      }
      navigate('/result')
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleRepredict = async () => {
    setRepredictLoading(true)
    setError(null)
    try {
      const res = await executionApi.post('/doe/repredict', {
        suggestion_id: suggestion.suggestion_id,
        params: editedParams,
      })
      setPredOverride(res.data.data)
      setLastPredictedParams(editedParams)
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    } finally {
      setRepredictLoading(false)
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
      <h2>
        AI 제안 승인 ({suggestion.doe_attempt}차)
        {suggestion.recipe_found && (
          <span className="pill pill-ok" style={{ marginLeft: 10, fontSize: 13, verticalAlign: 'middle' }}>
            ✅ 검증된 레시피 · 확인 실험
          </span>
        )}
      </h2>
      {error && <div className="banner banner-warning">{error}</div>}

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        {/* 좌측 패널 */}
        <div className="card" style={{ flex: 1 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap' }}>
            <div style={{ paddingRight: 32 }}>
              <h3 style={sectionHeadStyle}>AI 제안 파라미터</h3>
              <table className="kv-table kv-table--params">
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
                            style={{
                              width: '100%',
                              textAlign: 'right',
                              border: 'none',
                              background: 'transparent',
                              padding: 0,
                              margin: 0,
                              fontSize: 'inherit',
                              fontFamily: 'inherit',
                              color: 'inherit',
                              boxShadow: 'inset 0 -1px 0 0 var(--border)',
                            }}
                          />
                        ) : (
                          editedParams[key]
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div style={{ paddingLeft: 32 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <h3 style={sectionHeadStyle}>예측 결과</h3>
                {editing && (
                  <button className="btn btn-sm" disabled={repredictLoading} onClick={handleRepredict}>
                    {repredictLoading ? <><span className="spinner" /> 재예측 중...</> : '재예측'}
                  </button>
                )}
              </div>
              {isStale && (
                <p style={{ color: 'var(--warning)', fontSize: 12, margin: '0 0 6px' }}>
                  ⚠ 수정된 값 기준으로 재예측이 필요합니다
                </p>
              )}
              <table className="kv-table">
                <tbody>
                  <tr>
                    <td>예측 Kerf</td>
                    <td style={readingStyle}>{displayPred.pred_kerf} μm</td>
                  </tr>
                  <tr>
                    <td>예측 Depth</td>
                    <td style={readingStyle}>{displayPred.pred_depth} μm</td>
                  </tr>
                  <tr>
                    <td>예측 판정</td>
                    <td style={{ textAlign: 'center' }}>
                      <span className={`pill ${QUALITY_PILL[displayPred.pred_quality] ?? 'pill-muted'}`}>
                        {displayPred.pred_quality}
                      </span>
                    </td>
                  </tr>
                  <tr>
                    <td>신뢰도</td>
                    <td style={readingStyle}>{(displayPred.confidence * 100).toFixed(1)}%</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <h3 style={{ ...sectionHeadStyle, marginTop: 24 }}>SHAP 영향도 (Depth, 상위 5개)</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={shapData} layout="vertical" margin={{ left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" />
              <YAxis type="category" dataKey="label" width={120} tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="value">
                {shapData.map((entry, idx) => (
                  <Cell key={idx} fill={entry.value >= 0 ? 'var(--accent)' : 'var(--danger)'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>

          {shapData.length > 0 && (
            <div
              style={{
                background: 'var(--bg)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                padding: 14,
                marginTop: 12,
                fontSize: 13,
              }}
            >
              <p style={{ margin: 0, lineHeight: 1.6, fontWeight: 700, color: 'var(--text)' }}>
                이번 제안에서는 {FEATURE_LABELS[shapData[0].feature] ?? shapData[0].feature}가 Depth 예측에 가장 큰 영향을 주었습니다
                ({shapData[0].value >= 0 ? 'Depth를 늘리는 방향' : 'Depth를 줄이는 방향'}).
              </p>
            </div>
          )}
        </div>

        {/* 우측 패널 */}
        <div className="card" style={{ flex: 1 }}>
          <h3 style={sectionHeadStyle}>AI 설명</h3>
          <div
            style={{
              background: 'var(--bg)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              padding: 14,
              minHeight: 120,
              whiteSpace: 'pre-wrap',
              color: suggestion.llm_explanation ? 'var(--text)' : 'var(--text-muted)',
              display: 'flex',
              alignItems: suggestion.llm_explanation_status === 'pending' ? 'center' : 'flex-start',
              gap: 8,
            }}
          >
            {suggestion.llm_explanation_status === 'pending' ? (
              <>
                <span className="spinner" /> AI 설명 생성 중...
              </>
            ) : (
              suggestion.llm_explanation || 'LLM 설명을 생성하지 못했습니다.'
            )}
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
                <button
                  className="btn"
                  disabled={loading}
                  onClick={() => {
                    setEditing(false)
                    setEditedParams(suggestion.suggested_params)
                    setPredOverride(null)
                    setLastPredictedParams(suggestion.suggested_params)
                  }}
                >
                  취소
                </button>
              </>
            )}
          </div>

          <div
            style={{
              background: 'var(--bg)',
              border: '1px solid var(--border)',
              borderRadius: 8,
              padding: 14,
              marginTop: 24,
              fontSize: 13,
              color: 'var(--text-muted)',
            }}
          >
            <h3 style={{ fontSize: 14, color: 'var(--text)', marginBottom: 8 }}>결과 해석 가이드</h3>
            <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.6 }}>
              <li><strong>예측 Kerf / Depth</strong>: AI 제안 파라미터로 가공했을 때 예상되는 절단폭(Kerf)과 가공 깊이(Depth)입니다. Depth는 0μm 초과 ~ 25μm 이하일 때 OK로 판정됩니다.</li>
              <li><strong>예측 판정</strong>: 예측 Depth를 기준으로 OK / 미가공(과소 가공) / 과가공 / NG 중 하나로 자동 분류한 결과입니다.</li>
              <li><strong>신뢰도</strong>: AI 모델이 위 판정을 얼마나 확신하는지를 나타내는 값입니다. 낮을수록 실제 결과와 차이가 날 수 있습니다.</li>
              <li><strong>SHAP 영향도 그래프</strong>: 각 파라미터(또는 조합 변수)가 예측 Depth를 얼마나, 어느 방향으로 바꾸는지를 보여줍니다. 막대가 오른쪽(파란색, 양수)이면 Depth를 늘리는 방향, 왼쪽(빨간색, 음수)이면 줄이는 방향으로 작용했다는 의미이며, 막대가 길수록 영향이 큽니다.</li>
            </ul>
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
