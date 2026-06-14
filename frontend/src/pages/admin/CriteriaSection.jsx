import { useState } from 'react'
import { executionApi } from '../../api/client'

// 산업용 콘솔 톤: 섹션 헤더 액센트 좌측 바, 수치/값 입력은 모노스페이스+각진 모서리 — 타 화면과 통일
const sectionHeadStyle = {
  paddingLeft: 8,
  borderLeft: '3px solid var(--accent)',
  lineHeight: 1.2,
}
const numInputStyle = {
  padding: '8px 10px',
  border: '1px solid #c7cbd1',
  borderRadius: 4,
  fontFamily: 'ui-monospace, Consolas, "Courier New", monospace',
  fontSize: 14,
}

export default function CriteriaSection() {
  const [depthOkMin, setDepthOkMin] = useState('0.0')
  const [depthOkMax, setDepthOkMax] = useState('25.0')
  const [criteriaResult, setCriteriaResult] = useState(null)
  const [criteriaError, setCriteriaError] = useState(null)
  const [savingCriteria, setSavingCriteria] = useState(false)

  const [powerMin, setPowerMin] = useState('2.8')
  const [powerMax, setPowerMax] = useState('59.8')
  const [speedValues, setSpeedValues] = useState('200,500,1000')
  const [defocusValues, setDefocusValues] = useState('0,1,2,3,4')
  const [spaceResult, setSpaceResult] = useState(null)
  const [spaceError, setSpaceError] = useState(null)
  const [savingSpace, setSavingSpace] = useState(false)

  const handleSaveCriteria = async () => {
    setSavingCriteria(true)
    setCriteriaError(null)
    setCriteriaResult(null)
    try {
      const res = await executionApi.patch('/admin/settings/quality-criteria', {
        depth_ok_min: parseFloat(depthOkMin),
        depth_ok_max: parseFloat(depthOkMax),
      })
      setCriteriaResult(res.data)
    } catch (err) {
      setCriteriaError(err.response?.data?.message || err.message)
    } finally {
      setSavingCriteria(false)
    }
  }

  const handleSaveSpace = async () => {
    setSavingSpace(true)
    setSpaceError(null)
    setSpaceResult(null)
    try {
      const res = await executionApi.patch('/admin/settings/search-space', {
        power_min: parseFloat(powerMin),
        power_max: parseFloat(powerMax),
        speed_values: speedValues.split(',').map((v) => parseFloat(v.trim())),
        defocus_values: defocusValues.split(',').map((v) => parseFloat(v.trim())),
      })
      setSpaceResult(res.data)
    } catch (err) {
      setSpaceError(err.response?.data?.message || err.message)
    } finally {
      setSavingSpace(false)
    }
  }

  return (
    <div>
      <h2>판정 기준 설정</h2>

      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={sectionHeadStyle}>품질 판정 기준 (Depth)</h3>
        {criteriaError && <div className="banner banner-warning">{criteriaError}</div>}
        <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            DEPTH_OK_MIN (μm)
            <input
              type="number"
              step="0.1"
              value={depthOkMin}
              onChange={(e) => setDepthOkMin(e.target.value)}
              style={{ ...numInputStyle, width: 140 }}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            DEPTH_OK_MAX (μm)
            <input
              type="number"
              step="0.1"
              value={depthOkMax}
              onChange={(e) => setDepthOkMax(e.target.value)}
              style={{ ...numInputStyle, width: 140 }}
            />
          </label>
        </div>
        <button className="btn btn-primary" disabled={savingCriteria} onClick={handleSaveCriteria}>
          {savingCriteria ? <span className="spinner" /> : '판정 기준 저장'}
        </button>
        {criteriaResult && (
          <div className="banner banner-success" style={{ marginTop: 16 }}>
            {criteriaResult.message} (OK 범위: {criteriaResult.data.depth_ok_min}μm &lt; Depth ≤ {criteriaResult.data.depth_ok_max}μm)
          </div>
        )}
      </div>

      <div className="card">
        <h3 style={sectionHeadStyle}>Auto DOE 탐색 공간</h3>
        {spaceError && <div className="banner banner-warning">{spaceError}</div>}
        <div style={{ display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            Power Min (W)
            <input
              type="number"
              step="0.1"
              value={powerMin}
              onChange={(e) => setPowerMin(e.target.value)}
              style={{ ...numInputStyle, width: 140 }}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            Power Max (W)
            <input
              type="number"
              step="0.1"
              value={powerMax}
              onChange={(e) => setPowerMax(e.target.value)}
              style={{ ...numInputStyle, width: 140 }}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            Speed 값 (콤마 구분)
            <input
              type="text"
              value={speedValues}
              onChange={(e) => setSpeedValues(e.target.value)}
              style={{ ...numInputStyle, width: 200 }}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            Defocus 값 (콤마 구분)
            <input
              type="text"
              value={defocusValues}
              onChange={(e) => setDefocusValues(e.target.value)}
              style={{ ...numInputStyle, width: 200 }}
            />
          </label>
        </div>
        <button className="btn btn-primary" disabled={savingSpace} onClick={handleSaveSpace}>
          {savingSpace ? <span className="spinner" /> : '탐색 공간 저장'}
        </button>
        {spaceResult && (
          <div className="banner banner-success" style={{ marginTop: 16 }}>
            {spaceResult.message}
          </div>
        )}
      </div>
    </div>
  )
}
