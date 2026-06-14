import { Fragment, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { executionApi } from '../api/client'
import { useSession } from '../context/SessionContext'

const PARAM_LABELS = {
  speed: 'Speed',
  defocus: 'Defocus',
  frequency: 'Frequency',
  power: 'Power',
}

// 각 파라미터의 표시 단위 (레시피 조회 화면과 동일 기준)
const PARAM_UNITS = {
  speed: 'mm/s',
  defocus: 'mm',
  frequency: 'kHz',
  power: 'W',
}

const QUALITY_PILL = {
  OK: 'pill-ok',
  미가공: 'pill-warn',
  과가공: 'pill-warn',
  NG: 'pill-danger',
}

// 산업용 콘솔 톤: 섹션 헤더 액센트 좌측 바, 수치 입력/판독값 모노스페이스(계기판 느낌) — 타 화면과 통일
const sectionHeadStyle = {
  paddingLeft: 8,
  borderLeft: '3px solid var(--accent)',
  lineHeight: 1.2,
}
const readingStyle = {
  fontFamily: 'ui-monospace, Consolas, "Courier New", monospace',
}
const inputStyle = {
  padding: '8px 10px',
  border: '1px solid #c7cbd1',
  borderRadius: 4,
  width: 160,
  fontFamily: 'ui-monospace, Consolas, "Courier New", monospace',
  fontSize: 14,
}

export default function ResultPage() {
  const navigate = useNavigate()
  const { session, setSuggestion, addHistoryEntry } = useSession()
  const suggestion = session.suggestion
  const finalParams = session.approval?.final_params ?? suggestion?.suggested_params

  // 예측값을 샘플 값으로 미리 채워두고, 운영자가 실측값으로 수정하도록 한다
  const [actualKerf, setActualKerf] = useState(suggestion?.pred_kerf ?? '')
  const [actualDepth, setActualDepth] = useState(suggestion?.pred_depth ?? '')
  const [notes, setNotes] = useState('')
  const [notesEdited, setNotesEdited] = useState(false)
  const [evalLoading, setEvalLoading] = useState(false)
  const [evalElapsedMs, setEvalElapsedMs] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  // 결과 저장 전 실측값 확인 모달 표시 여부
  const [showConfirm, setShowConfirm] = useState(false)
  // 현재 품질 판정 기준(.env DEPTH_OK_MIN/MAX) — 사전 판정 미리보기용
  const [criteria, setCriteria] = useState(null)

  if (!suggestion || !finalParams) {
    return (
      <div className="card">
        <p>승인된 제안 정보가 없습니다. 먼저 실험 조건을 입력하고 승인해주세요.</p>
        <button className="btn btn-primary" onClick={() => navigate('/')}>
          실험 조건 입력으로 이동
        </button>
      </div>
    )
  }

  // AI 평가 생성 중 경과 시간 기반으로 진행률/예상 남은 시간을 표시한다
  // (실제 완료 시점을 알 수 없으므로 EVAL_ESTIMATED_MS 기준으로 95%까지 점진적으로 채움)
  useEffect(() => {
    if (!evalLoading) {
      setEvalElapsedMs(0)
      return
    }
    const startedAt = Date.now()
    const interval = setInterval(() => setEvalElapsedMs(Date.now() - startedAt), 200)
    return () => clearInterval(interval)
  }, [evalLoading])

  // 현재 판정 기준을 받아온다 (관리자 콘솔에서 변경 시 즉시 반영)
  useEffect(() => {
    executionApi.get('/doe/criteria').then((res) => setCriteria(res.data.data)).catch(() => {})
  }, [])

  // 입력한 실측 Depth 기준 사전 판정 (서버 judge_quality와 동일 로직, 기준값은 API에서 수신)
  // NG(Defect 감지)는 Depth만으로 판단할 수 없으므로 미리보기 대상에서 제외한다
  const previewQuality = (() => {
    if (!criteria || actualDepth === '') return null
    const d = parseFloat(actualDepth)
    if (Number.isNaN(d)) return null
    if (d > criteria.depth_ok_max) return '미가공'
    if (d <= criteria.depth_ok_min) return '과가공'
    return 'OK'
  })()

  const EVAL_ESTIMATED_MS = 8000
  const evalProgressPct = Math.min(95, (evalElapsedMs / EVAL_ESTIMATED_MS) * 100)
  const evalRemainingS = Math.max(0, Math.ceil((EVAL_ESTIMATED_MS - evalElapsedMs) / 1000))

  const canSubmit = actualKerf !== '' && actualDepth !== '' && !loading
  const canEvaluate = actualKerf !== '' && actualDepth !== '' && !evalLoading && !result

  const handleGenerateEvaluation = async () => {
    if (!canEvaluate) return
    setEvalLoading(true)
    setError(null)
    try {
      const res = await executionApi.post('/doe/evaluate', {
        suggestion_id: suggestion.suggestion_id,
        actual_kerf: parseFloat(actualKerf),
        actual_depth: parseFloat(actualDepth),
      })
      const { evaluation } = res.data.data
      if (evaluation) {
        setNotes(evaluation)
        setNotesEdited(false)
      }
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    } finally {
      setEvalLoading(false)
    }
  }

  const handleSave = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await executionApi.post('/doe/result', {
        suggestion_id: suggestion.suggestion_id,
        actual_kerf: parseFloat(actualKerf),
        actual_depth: parseFloat(actualDepth),
        operator_name: session.operatorName,
        notes: notes.trim() === '' ? null : notes.trim(),
      })
      const data = res.data.data
      setResult(data)
      setShowConfirm(false)
      addHistoryEntry({
        ...finalParams,
        actual_kerf: parseFloat(actualKerf),
        actual_depth: parseFloat(actualDepth),
        quality: data.quality,
      })
    } catch (err) {
      setError(err.response?.data?.message || err.message)
      setShowConfirm(false)
    } finally {
      setLoading(false)
    }
  }

  const handleNextSuggestion = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await executionApi.post('/doe/suggest', {
        m1_length: session.material.m1_length,
        m2_length: session.material.m2_length,
        thickness: parseFloat(session.material.thickness),
        experiment_history: session.experimentHistory,
        n_suggestions: 1,
      })
      setSuggestion(res.data.data)
      navigate('/approval')
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 760, margin: '0 auto' }}>
      <h2>실험 결과 입력</h2>
      {error && <div className="banner banner-warning">{error}</div>}

      <div className="card">
        <h3 style={sectionHeadStyle}>승인된 파라미터 ({suggestion.doe_attempt}차)</h3>
        <table className="table-bordered">
          <thead>
            <tr>
              {Object.values(PARAM_LABELS).map((label) => (
                <th key={label} style={{ textAlign: 'center' }}>{label}</th>
              ))}
              <th style={{ textAlign: 'center' }}>예측 Kerf</th>
              <th style={{ textAlign: 'center' }}>예측 Depth</th>
              <th style={{ textAlign: 'center' }}>예측 판정</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              {Object.keys(PARAM_LABELS).map((key) => (
                <td key={key} style={{ textAlign: 'center', ...readingStyle }}>
                  {finalParams[key]} {PARAM_UNITS[key]}
                </td>
              ))}
              <td style={{ textAlign: 'center', ...readingStyle }}>{suggestion.pred_kerf} μm</td>
              <td style={{ textAlign: 'center', ...readingStyle }}>{suggestion.pred_depth} μm</td>
              <td style={{ textAlign: 'center' }}>
                <span className={`pill ${QUALITY_PILL[suggestion.pred_quality] ?? 'pill-muted'}`}>
                  {suggestion.pred_quality}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3 style={sectionHeadStyle}>실측 결과 입력</h3>
        <div style={{ display: 'flex', gap: 24, marginBottom: 16 }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            Kerf (μm)
            <input
              type="number"
              step="0.1"
              value={actualKerf}
              onChange={(e) => setActualKerf(e.target.value)}
              disabled={!!result}
              style={inputStyle}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            Depth (μm)
            <input
              type="number"
              step="0.1"
              value={actualDepth}
              onChange={(e) => setActualDepth(e.target.value)}
              disabled={!!result}
              style={inputStyle}
            />
          </label>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span>
              실험 결과 설명 (보고용) <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(선택)</span>
            </span>
            {!result && (
              <button
                type="button"
                className="btn btn-sm btn-primary"
                disabled={!canEvaluate}
                onClick={() => { setNotesEdited(false); handleGenerateEvaluation() }}
              >
                {evalLoading ? <><span className="spinner" /> AI 평가 생성 중...</> : 'AI 평가'}
              </button>
            )}
          </div>
          {evalLoading && (
            <div>
              <div className="progress-bar">
                <div className="progress-bar-fill" style={{ width: `${evalProgressPct}%` }} />
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                AI 평가 생성 중... {Math.round(evalProgressPct)}%
                {evalRemainingS > 0 ? ` (약 ${evalRemainingS}초 남음)` : ' (잠시만 기다려주세요)'}
              </div>
            </div>
          )}
          <textarea
            value={notes}
            onChange={(e) => { setNotes(e.target.value); setNotesEdited(true) }}
            disabled={!!result}
            rows={3}
            placeholder="Kerf/Depth를 입력하면 AI가 평가 초안을 작성합니다. 내용을 검토하고 필요시 수정/보완하세요."
            style={{ padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 6, resize: 'vertical', fontFamily: 'inherit' }}
          />
        </div>

        {!result && (
          <button className="btn btn-primary" disabled={!canSubmit} onClick={() => setShowConfirm(true)}>
            결과 저장
          </button>
        )}

        {result && (
          <>
            {result.quality === 'OK' ? (
              <div className="banner banner-success">
                OK 달성! (Depth {actualDepth}μm) {result.recipe_saved && `레시피가 저장되었습니다. (recipe_id: ${result.recipe_id})`}
              </div>
            ) : (
              <div className="banner banner-warning">
                {result.quality} 판정입니다. ({result.message})
                <div style={{ marginTop: 10 }}>
                  <button className="btn btn-primary" disabled={loading} onClick={handleNextSuggestion}>
                    {loading ? (
                      <>
                        <span className="spinner" /> 제안 생성 중...
                      </>
                    ) : (
                      '다음 제안 요청'
                    )}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {showConfirm && (
        <div className="modal-overlay">
          <div className="modal">
            <h3>실측 결과 확인</h3>
            <p style={{ color: 'var(--text-muted)', marginTop: 0, fontSize: 13 }}>
              아래 입력값이 정확한지 확인한 뒤 저장하세요. 저장 후에는 수정할 수 없으며,
              이 값으로 판정(OK/미가공/과가공/NG)이 결정됩니다.
            </p>
            <table className="kv-table" style={{ width: '100%' }}>
              <tbody>
                <tr>
                  <td style={{ whiteSpace: 'nowrap', paddingRight: 16 }}>승인 파라미터 ({suggestion.doe_attempt}차)</td>
                  <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                    <div style={{ display: 'inline-grid', gridTemplateColumns: 'auto auto', justifyContent: 'end' }}>
                      {Object.keys(PARAM_LABELS).map((k) => (
                        <Fragment key={k}>
                          <span style={{ textAlign: 'right' }}>{PARAM_LABELS[k]}:</span>
                          <span style={{ textAlign: 'right' }}>{finalParams[k]} {PARAM_UNITS[k]}</span>
                        </Fragment>
                      ))}
                    </div>
                  </td>
                </tr>
                <tr>
                  <td>실측 Kerf</td>
                  <td style={{ textAlign: 'right', fontWeight: 700, ...readingStyle }}>{actualKerf} μm</td>
                </tr>
                <tr>
                  <td>실측 Depth</td>
                  <td style={{ textAlign: 'right', fontWeight: 700, ...readingStyle }}>{actualDepth} μm</td>
                </tr>
                <tr>
                  <td>사전 판정 미리보기</td>
                  <td style={{ textAlign: 'right' }}>
                    {previewQuality ? (
                      <span className={`pill ${QUALITY_PILL[previewQuality] ?? 'pill-muted'}`}>{previewQuality}</span>
                    ) : (
                      <span style={{ color: 'var(--text-muted)' }}>—</span>
                    )}
                    {criteria && (
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                        OK 기준: {criteria.depth_ok_min}μm 초과 ~ {criteria.depth_ok_max}μm 이하
                      </div>
                    )}
                  </td>
                </tr>
                <tr>
                  <td>결과 설명</td>
                  <td style={{ textAlign: 'left', whiteSpace: 'pre-wrap', color: 'var(--text-muted)' }}>
                    {notes.trim() === '' ? '(없음)' : notes.trim()}
                  </td>
                </tr>
              </tbody>
            </table>
            <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8, marginBottom: 0 }}>
              ※ 사전 판정은 입력한 Depth 기준 예상값입니다. 최종 판정은 저장 시 서버 기준으로 확정되며,
              NG(Defect 감지)는 미리보기에서 판단하지 않습니다.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
              <button className="btn" disabled={loading} onClick={() => setShowConfirm(false)}>
                수정
              </button>
              <button className="btn btn-primary" disabled={loading} onClick={handleSave}>
                {loading ? (
                  <>
                    <span className="spinner" /> 저장 중...
                  </>
                ) : (
                  '확인 후 저장'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {session.experimentHistory.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3 style={sectionHeadStyle}>Auto DOE 수렴 이력 (이번 세션)</h3>
          <table>
            <thead>
              <tr>
                <th>차수</th>
                {Object.values(PARAM_LABELS).map((label) => (
                  <th key={label}>{label}</th>
                ))}
                <th>실측 Kerf</th>
                <th>실측 Depth</th>
                <th>판정</th>
              </tr>
            </thead>
            <tbody>
              {session.experimentHistory.map((entry, idx) => (
                <tr key={idx}>
                  <td>{idx + 1}</td>
                  {Object.keys(PARAM_LABELS).map((key) => (
                    <td key={key} style={readingStyle}>{entry[key]}</td>
                  ))}
                  <td style={readingStyle}>{entry.actual_kerf} μm</td>
                  <td style={readingStyle}>{entry.actual_depth} μm</td>
                  <td>
                    <span className={`pill ${QUALITY_PILL[entry.quality] ?? 'pill-muted'}`}>{entry.quality}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
