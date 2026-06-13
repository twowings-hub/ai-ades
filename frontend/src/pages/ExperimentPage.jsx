import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { dataPrepApi, executionApi } from '../api/client'
import { useSession } from '../context/SessionContext'

// 학습 데이터에 포함된 대표값 (빠른 선택용 프리셋). 그 외 값도 직접 입력 가능하다.
const M1_PRESETS = [4, 10, 20]
const M2_PRESETS = [10, 25, 50]
// M1 입력 시 M2 length 기본값을 M1 × M2_RATIO로 자동 설정 (학습 데이터 기준 M2 = M1 × 2.5)
const M2_RATIO = 2.5

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
      // 검증된 레시피(recipe_found)든 신규 조합이든 동일하게 승인 화면으로 이동한다.
      // 승인 화면이 이미 Human-in-the-Loop 확인 단계이므로 중간 배너 단계는 두지 않는다.
      navigate('/approval')
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
      <h2 style={{ fontSize: 18, marginBottom: 2 }}>실험 조건 입력</h2>
      <p style={{ color: 'var(--text-muted)', margin: '0 0 8px', fontSize: 13 }}>
        소재 조합과 두께를 입력하면 Auto DOE가 다음 실험 조건을 제안합니다.
      </p>

      <div className="card card-compact" style={{ marginTop: 8 }}>
        <h3 style={{ fontSize: 14, marginBottom: 6 }}>M1 소재 종류</h3>
        <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
          {materialTypes.m1.map((t) => (
            <button
              key={t.id}
              className={`btn btn-sm ${m1Glass === t.name ? 'btn-primary' : ''}`}
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

        <h3 style={{ fontSize: 14, marginBottom: 6 }}>M1 ({m1Glass ?? '-'}) Length</h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
          <input
            type="number"
            step="0.1"
            value={m1Length ?? ''}
            onChange={(e) => {
              const v = e.target.value === '' ? null : parseFloat(e.target.value)
              setM1Length(v)
              setM2Length(v === null || Number.isNaN(v) ? null : v * M2_RATIO)
            }}
            placeholder="예: 10"
            style={{ padding: '6px 8px', border: '1px solid var(--border)', borderRadius: 6, width: 140 }}
          />
          <span style={{ color: 'var(--text-muted)' }}>mm</span>
          <div style={{ display: 'flex', gap: 6, marginLeft: 8 }}>
            {M1_PRESETS.map((v) => (
              <button
                key={v}
                className={`btn btn-sm ${m1Length === v ? 'btn-selected' : ''}`}
                onClick={() => { setM1Length(v); setM2Length(v * M2_RATIO) }}
              >
                {v} mm
              </button>
            ))}
          </div>
        </div>
        {m1OutOfRange && (
          <p style={{ color: 'var(--warn, #b45309)', marginTop: 6, fontSize: '0.85em' }}>
            ⚠ 학습 데이터 범위({dataRanges.m1_length_mm.min}~{dataRanges.m1_length_mm.max}mm)를 벗어났습니다. 예측 신뢰도가 낮을 수 있습니다 (Auto DOE 탐색 횟수 증가 권장).
          </p>
        )}
      </div>

      <div className="card card-compact" style={{ marginTop: 8 }}>
        <h3 style={{ fontSize: 14, marginBottom: 6 }}>M2 소재 종류</h3>
        <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
          {materialTypes.m2.map((t) => (
            <button
              key={t.id}
              className={`btn btn-sm ${m2Film === t.name ? 'btn-primary' : ''}`}
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

        <h3 style={{ fontSize: 14, marginBottom: 6 }}>M2 ({m2Film ?? '-'}) Length</h3>
        <p style={{ color: 'var(--text-muted)', margin: '0 0 6px', fontSize: '0.85em' }}>
          M1 입력 시 M1 × {M2_RATIO}로 자동 설정됩니다. 필요하면 직접 수정하세요.
        </p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
          <input
            type="number"
            step="0.1"
            value={m2Length ?? ''}
            onChange={(e) => setM2Length(e.target.value === '' ? null : parseFloat(e.target.value))}
            placeholder="예: 25"
            style={{ padding: '6px 8px', border: '1px solid var(--border)', borderRadius: 6, width: 140 }}
          />
          <span style={{ color: 'var(--text-muted)' }}>mm</span>
          <div style={{ display: 'flex', gap: 6, marginLeft: 8 }}>
            {M2_PRESETS.map((v) => (
              <button
                key={v}
                className={`btn btn-sm ${m2Length === v ? 'btn-selected' : ''}`}
                onClick={() => setM2Length(v)}
              >
                {v} mm
              </button>
            ))}
          </div>
        </div>
        {m2OutOfRange && (
          <p style={{ color: 'var(--warn, #b45309)', marginTop: 6, fontSize: '0.85em' }}>
            ⚠ 학습 데이터 범위({dataRanges.m2_length_mm.min}~{dataRanges.m2_length_mm.max}mm)를 벗어났습니다. 예측 신뢰도가 낮을 수 있습니다 (Auto DOE 탐색 횟수 증가 권장).
          </p>
        )}
      </div>

      <div className="card card-compact" style={{ marginTop: 8 }}>
        <h3 style={{ fontSize: 14, marginBottom: 6 }}>Thickness (실측값)</h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <input
            type="number"
            step="0.1"
            value={thickness}
            onChange={(e) => setThickness(e.target.value)}
            placeholder="예: 105.0"
            style={{ padding: '6px 8px', border: '1px solid var(--border)', borderRadius: 6, width: 140 }}
          />
          <span style={{ color: 'var(--text-muted)' }}>μm</span>
        </div>
        {thicknessOutOfRange && (
          <p style={{ color: 'var(--warn, #b45309)', marginTop: 6, fontSize: '0.85em' }}>
            ⚠ 학습 데이터 범위({dataRanges.thickness_um.min}~{dataRanges.thickness_um.max}μm)를 벗어났습니다. 예측 신뢰도가 낮을 수 있습니다 (Auto DOE 탐색 횟수 증가 권장).
          </p>
        )}
      </div>

      <div className="card card-compact" style={{ marginTop: 8 }}>
        {materialInfoLoading && (
          <p style={{ color: 'var(--text-muted)', marginBottom: 8, fontSize: 13 }}>소재 이력 조회 중...</p>
        )}

        {!materialInfoLoading && materialInfo && (
          <div className={`banner ${materialInfo.recipeStatus === 'exact' ? 'banner-success' : 'banner-info'}`} style={{ marginBottom: 8, padding: '8px 12px', fontSize: 13 }}>
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

        {error && <div className="banner banner-warning" style={{ padding: '8px 12px', fontSize: 13 }}>{error}</div>}

        <button className="btn btn-primary" disabled={!canSubmit} onClick={handleStart} style={{ width: '100%', padding: '10px 0', marginTop: 4 }}>
          {loading ? (
            <>
              <span className="spinner" /> 예측 중...
            </>
          ) : (
            'Auto DOE 시작'
          )}
        </button>
      </div>
    </div>
  )
}
