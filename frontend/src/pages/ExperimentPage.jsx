import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { dataPrepApi, executionApi } from '../api/client'
import { useSession } from '../context/SessionContext'

// 학습 데이터에 포함된 대표값 (빠른 선택용 프리셋). 그 외 값도 직접 입력 가능하다.
const M1_PRESETS = [4, 10, 20]
const M2_PRESETS = [10, 25, 50]

export default function ExperimentPage() {
  const navigate = useNavigate()
  const { session, startNewMaterial, setSuggestion } = useSession()

  const [m1Length, setM1Length] = useState(session.material.m1_length)
  const [m2Length, setM2Length] = useState(session.material.m2_length)
  const [thickness, setThickness] = useState(session.material.thickness)

  const [materialTypes, setMaterialTypes] = useState({ m1: [], m2: [] })
  const [m1Glass, setM1Glass] = useState(session.material.m1_glass ?? null)
  const [m2Film, setM2Film] = useState(session.material.m2_film ?? null)

  // 학습 데이터의 m1/m2 length, thickness 범위 (이 범위를 벗어나면 예측이 외삽이 되어 신뢰도 경고 표시)
  const [dataRanges, setDataRanges] = useState(null)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [recipeBanner, setRecipeBanner] = useState(null)

  const [materialInfo, setMaterialInfo] = useState(null)
  const [materialInfoLoading, setMaterialInfoLoading] = useState(false)

  const canSubmit = m1Length && m2Length && thickness !== '' && m1Glass && m2Film && !loading

  // 소재 종류(M1/M2) 목록을 조회하고, 미선택 상태면 첫 번째 항목을 기본값으로 설정한다
  useEffect(() => {
    let cancelled = false
    executionApi.get('/material-types').then((res) => {
      if (cancelled) return
      const data = res.data.data
      setMaterialTypes(data)
      setM1Glass((prev) => prev ?? data.m1?.[0]?.name ?? null)
      setM2Film((prev) => prev ?? data.m2?.[0]?.name ?? null)
    }).catch(() => {})

    return () => {
      cancelled = true
    }
  }, [])

  // 학습 데이터의 m1/m2 length, thickness 범위를 조회한다 (외삽 경고용)
  useEffect(() => {
    let cancelled = false
    dataPrepApi.get('/data/distribution').then((res) => {
      if (cancelled) return
      setDataRanges(res.data.data.data_ranges)
    }).catch(() => {})

    return () => {
      cancelled = true
    }
  }, [])

  // 소재 조합(M1/M2/Thickness) 변경 시 학습 이력 + 레시피 보유 여부를 미리 조회한다
  useEffect(() => {
    if (!m1Length || !m2Length || thickness === '' || !m1Glass || !m2Film) {
      setMaterialInfo(null)
      return
    }

    let cancelled = false
    const timer = setTimeout(async () => {
      setMaterialInfoLoading(true)
      try {
        const [distRes, recipeRes] = await Promise.allSettled([
          dataPrepApi.get('/data/distribution'),
          executionApi.get(`/recipes/${m1Length}/${m2Length}`, {
            params: { thickness: parseFloat(thickness), m1_glass: m1Glass, m2_film: m2Film },
          }),
        ])

        if (cancelled) return

        let count = 0
        if (distRes.status === 'fulfilled') {
          count = distRes.value.data.data.by_material
            .filter((m) => m.m1_length_mm === m1Length && m.m2_length_mm === m2Length
              && (m.m1_glass ?? m1Glass) === m1Glass && (m.m2_film ?? m2Film) === m2Film)
            .reduce((sum, m) => sum + m.count, 0)
        }

        let recipeStatus = 'none'
        if (recipeRes.status === 'fulfilled') {
          recipeStatus = recipeRes.value.data.message?.includes('유사') ? 'similar' : 'exact'
        }

        setMaterialInfo({ count, recipeStatus })
      } finally {
        if (!cancelled) setMaterialInfoLoading(false)
      }
    }, 400)

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [m1Length, m2Length, thickness, m1Glass, m2Film])

  const runSuggest = async (history) => {
    setLoading(true)
    setError(null)
    setRecipeBanner(null)

    try {
      const res = await executionApi.post('/doe/suggest', {
        m1_length: m1Length,
        m2_length: m2Length,
        thickness: parseFloat(thickness),
        m1_glass: m1Glass,
        m2_film: m2Film,
        experiment_history: history,
        n_suggestions: 1,
      })

      const data = res.data.data
      setSuggestion(data)

      if (data.recipe_found) {
        setRecipeBanner(data)
      } else {
        navigate('/approval')
      }
    } catch (err) {
      setError(err.response?.data?.message || err.message)
    } finally {
      setLoading(false)
    }
  }

  // 입력값이 학습 데이터 범위를 벗어나는지 확인한다 (벗어나면 모델 예측이 외삽이 되어 신뢰도가 낮아짐)
  const outOfRange = (value, key) => {
    const range = dataRanges?.[key]
    if (!range || value === '' || value === null || Number.isNaN(value)) return false
    return value < range.min || value > range.max
  }

  const m1OutOfRange = outOfRange(m1Length, 'm1_length_mm')
  const m2OutOfRange = outOfRange(m2Length, 'm2_length_mm')
  const thicknessOutOfRange = outOfRange(thickness === '' ? '' : parseFloat(thickness), 'thickness_um')

  const handleStart = () => {
    startNewMaterial({ m1_length: m1Length, m2_length: m2Length, thickness, m1_glass: m1Glass, m2_film: m2Film })
    runSuggest([])
  }

  return (
    <div style={{ maxWidth: 640, margin: '0 auto' }}>
      <h2>실험 조건 입력</h2>
      <p style={{ color: 'var(--text-muted)' }}>
        소재 조합과 두께를 입력하면 Auto DOE가 다음 실험 조건을 제안합니다.
      </p>

      <div className="card" style={{ marginTop: 16 }}>
        <h3>M1 소재 종류</h3>
        <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
          {materialTypes.m1.map((t) => (
            <button
              key={t.id}
              className={`btn ${m1Glass === t.name ? 'btn-primary' : ''}`}
              onClick={() => setM1Glass(t.name)}
              title={t.description ?? ''}
            >
              {t.name}
            </button>
          ))}
          {materialTypes.m1.length === 0 && (
            <span style={{ color: 'var(--text-muted)' }}>등록된 소재 종류가 없습니다 (관리자 콘솔에서 추가하세요)</span>
          )}
        </div>

        <h3>M1 ({m1Glass ?? '-'}) Length</h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <input
            type="number"
            step="0.1"
            value={m1Length ?? ''}
            onChange={(e) => setM1Length(e.target.value === '' ? null : parseFloat(e.target.value))}
            placeholder="예: 10"
            style={{ padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 6, width: 160 }}
          />
          <span style={{ color: 'var(--text-muted)' }}>mm</span>
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: m1OutOfRange ? 8 : 20 }}>
          {M1_PRESETS.map((v) => (
            <button
              key={v}
              className={`btn ${m1Length === v ? 'btn-primary' : ''}`}
              onClick={() => setM1Length(v)}
            >
              {v} mm
            </button>
          ))}
        </div>
        {m1OutOfRange && (
          <p style={{ color: 'var(--warn, #b45309)', marginBottom: 20, fontSize: '0.9em' }}>
            ⚠ 학습 데이터 범위({dataRanges.m1_length_mm.min}~{dataRanges.m1_length_mm.max}mm)를 벗어났습니다. 예측 신뢰도가 낮을 수 있습니다 (Auto DOE 탐색 횟수 증가 권장).
          </p>
        )}

        <h3>M2 소재 종류</h3>
        <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
          {materialTypes.m2.map((t) => (
            <button
              key={t.id}
              className={`btn ${m2Film === t.name ? 'btn-primary' : ''}`}
              onClick={() => setM2Film(t.name)}
              title={t.description ?? ''}
            >
              {t.name}
            </button>
          ))}
          {materialTypes.m2.length === 0 && (
            <span style={{ color: 'var(--text-muted)' }}>등록된 소재 종류가 없습니다 (관리자 콘솔에서 추가하세요)</span>
          )}
        </div>

        <h3>M2 ({m2Film ?? '-'}) Length</h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <input
            type="number"
            step="0.1"
            value={m2Length ?? ''}
            onChange={(e) => setM2Length(e.target.value === '' ? null : parseFloat(e.target.value))}
            placeholder="예: 25"
            style={{ padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 6, width: 160 }}
          />
          <span style={{ color: 'var(--text-muted)' }}>mm</span>
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: m2OutOfRange ? 8 : 20 }}>
          {M2_PRESETS.map((v) => (
            <button
              key={v}
              className={`btn ${m2Length === v ? 'btn-primary' : ''}`}
              onClick={() => setM2Length(v)}
            >
              {v} mm
            </button>
          ))}
        </div>
        {m2OutOfRange && (
          <p style={{ color: 'var(--warn, #b45309)', marginBottom: 20, fontSize: '0.9em' }}>
            ⚠ 학습 데이터 범위({dataRanges.m2_length_mm.min}~{dataRanges.m2_length_mm.max}mm)를 벗어났습니다. 예측 신뢰도가 낮을 수 있습니다 (Auto DOE 탐색 횟수 증가 권장).
          </p>
        )}

        <h3>Thickness (실측값)</h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: thicknessOutOfRange ? 8 : 20 }}>
          <input
            type="number"
            step="0.1"
            value={thickness}
            onChange={(e) => setThickness(e.target.value)}
            placeholder="예: 105.0"
            style={{ padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 6, width: 160 }}
          />
          <span style={{ color: 'var(--text-muted)' }}>μm</span>
        </div>
        {thicknessOutOfRange && (
          <p style={{ color: 'var(--warn, #b45309)', marginBottom: 20, fontSize: '0.9em' }}>
            ⚠ 학습 데이터 범위({dataRanges.thickness_um.min}~{dataRanges.thickness_um.max}μm)를 벗어났습니다. 예측 신뢰도가 낮을 수 있습니다 (Auto DOE 탐색 횟수 증가 권장).
          </p>
        )}

        {materialInfoLoading && (
          <p style={{ color: 'var(--text-muted)', marginBottom: 12 }}>소재 이력 조회 중...</p>
        )}

        {!materialInfoLoading && materialInfo && (
          <div className={`banner ${materialInfo.recipeStatus === 'exact' ? 'banner-success' : 'banner-info'}`} style={{ marginBottom: 16 }}>
            <p>이 소재 조합({m1Glass} {m1Length}mm + {m2Film} {m2Length}mm) 학습 데이터: {materialInfo.count}건</p>
            {materialInfo.recipeStatus === 'exact' && (
              <p style={{ marginTop: 4 }}>✅ 검증된 레시피 보유 (Thickness 일치) — 1회 확인 실험으로 완료 가능</p>
            )}
            {materialInfo.recipeStatus === 'similar' && (
              <p style={{ marginTop: 4 }}>⚠ 유사 레시피 보유 (Thickness 차이 있음) — 확인 실험 권장</p>
            )}
            {materialInfo.recipeStatus === 'none' && (
              <p style={{ marginTop: 4 }}>신규 조합입니다. Auto DOE로 조건을 탐색합니다 (약 5~7회 예상)</p>
            )}
          </div>
        )}

        {error && <div className="banner banner-warning">{error}</div>}

        {recipeBanner && (
          <div className="banner banner-info">
            저장된 레시피가 있습니다. 바로 적용하시겠습니까?
            <div style={{ marginTop: 10 }}>
              <button className="btn btn-primary" onClick={() => navigate('/approval')}>
                AI 제안 확인하기
              </button>
            </div>
          </div>
        )}

        <button className="btn btn-primary" disabled={!canSubmit} onClick={handleStart} style={{ width: '100%', padding: '12px 0' }}>
          {loading ? (
            <>
              <span className="spinner" /> 예측 중... (약 2초 소요)
            </>
          ) : (
            'Auto DOE 시작'
          )}
        </button>
      </div>
    </div>
  )
}
