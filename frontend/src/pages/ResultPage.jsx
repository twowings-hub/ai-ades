import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
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

export default function ResultPage() {
  const navigate = useNavigate()
  const { session, setSuggestion, addHistoryEntry } = useSession()
  const suggestion = session.suggestion
  const finalParams = session.approval?.final_params ?? suggestion?.suggested_params

  const [actualKerf, setActualKerf] = useState('')
  const [actualDepth, setActualDepth] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

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

  const canSubmit = actualKerf !== '' && actualDepth !== '' && !loading

  const handleSave = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await executionApi.post('/doe/result', {
        suggestion_id: suggestion.suggestion_id,
        actual_kerf: parseFloat(actualKerf),
        actual_depth: parseFloat(actualDepth),
        operator_name: session.operatorName,
      })
      const data = res.data.data
      setResult(data)
      addHistoryEntry({
        ...finalParams,
        actual_kerf: parseFloat(actualKerf),
        actual_depth: parseFloat(actualDepth),
        quality: data.quality,
      })
    } catch (err) {
      setError(err.response?.data?.message || err.message)
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
        <h3>승인된 파라미터 ({suggestion.doe_attempt}차)</h3>
        <table>
          <thead>
            <tr>
              {Object.values(PARAM_LABELS).map((label) => (
                <th key={label}>{label}</th>
              ))}
              <th>예측 Kerf</th>
              <th>예측 Depth</th>
              <th>예측 판정</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              {Object.keys(PARAM_LABELS).map((key) => (
                <td key={key}>{finalParams[key]}</td>
              ))}
              <td>{suggestion.pred_kerf} μm</td>
              <td>{suggestion.pred_depth} μm</td>
              <td>
                <span className={`pill ${QUALITY_PILL[suggestion.pred_quality] ?? 'pill-muted'}`}>
                  {suggestion.pred_quality}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>실측 결과 입력</h3>
        <div style={{ display: 'flex', gap: 24, marginBottom: 16 }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            Kerf (μm)
            <input
              type="number"
              step="0.1"
              value={actualKerf}
              onChange={(e) => setActualKerf(e.target.value)}
              disabled={!!result}
              style={{ padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 6, width: 160 }}
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
              style={{ padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 6, width: 160 }}
            />
          </label>
        </div>

        {!result && (
          <button className="btn btn-primary" disabled={!canSubmit} onClick={handleSave}>
            {loading ? (
              <>
                <span className="spinner" /> 저장 중...
              </>
            ) : (
              '결과 저장'
            )}
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

      {session.experimentHistory.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>Auto DOE 수렴 이력 (이번 세션)</h3>
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
                    <td key={key}>{entry[key]}</td>
                  ))}
                  <td>{entry.actual_kerf} μm</td>
                  <td>{entry.actual_depth} μm</td>
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
