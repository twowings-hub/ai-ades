import { useEffect, useState } from 'react'
import { executionApi } from '../api/client'

// 학습 데이터에 포함된 대표값 (빠른 선택용 프리셋). 그 외 값도 직접 입력 가능하다.
const M1_PRESETS = [4, 10, 20]
const M2_PRESETS = [10, 25, 50]

// 산업용 콘솔 톤: 섹션 헤더 액센트 좌측 바, 표·입력 수치는 모노스페이스(계기판 느낌) — 타 화면과 통일
const sectionHeadStyle = {
  paddingLeft: 8,
  borderLeft: '3px solid var(--accent)',
  lineHeight: 1.2,
}
const readingStyle = {
  fontFamily: 'ui-monospace, Consolas, "Courier New", monospace',
}
const inputBase = {
  padding: '8px 10px',
  border: '1px solid #c7cbd1',
  borderRadius: 4,
  fontFamily: 'ui-monospace, Consolas, "Courier New", monospace',
  fontSize: 14,
}
// 판정 의미색 (타 화면과 동일 기준) — 레시피 목록의 판정도 pill로 통일
const QUALITY_PILL = {
  OK: 'pill-ok',
  미가공: 'pill-warn',
  과가공: 'pill-warn',
  NG: 'pill-danger',
}

export default function RecipeSearchPage() {
  const [materialTypes, setMaterialTypes] = useState({ m1: [], m2: [] })
  const [m1Glass, setM1Glass] = useState(null)
  const [m2Film, setM2Film] = useState(null)
  const [m1Length, setM1Length] = useState('')
  const [m2Length, setM2Length] = useState('')
  const [thickness, setThickness] = useState('')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null) // { recipe, exact_match, message } | { notFound: true }

  const [recipes, setRecipes] = useState([])
  const [listError, setListError] = useState(null)

  // 소재 종류(M1/M2) 목록을 조회하고, 미선택 상태면 첫 번째 항목을 기본값으로 설정한다
  useEffect(() => {
    executionApi.get('/material-types').then((res) => {
      const data = res.data.data
      setMaterialTypes(data)
      setM1Glass((prev) => prev ?? data.m1?.[0]?.name ?? null)
      setM2Film((prev) => prev ?? data.m2?.[0]?.name ?? null)
    }).catch(() => {})
  }, [])

  const loadRecipes = () => {
    executionApi.get('/recipes').then((res) => {
      setRecipes(res.data.data.recipes)
    }).catch((err) => {
      setListError(err.response?.data?.message || err.message)
    })
  }

  // 전체 레시피 목록 조회
  useEffect(() => {
    loadRecipes()
  }, [])

  const canSubmit = m1Glass && m2Film && !loading
  const hasLengths = m1Length !== '' && m2Length !== ''

  const handleSearch = async () => {
    setLoading(true)
    setError(null)
    setResult(null)

    // M1/M2 길이 입력이 없으면 소재 종류만으로 전체 레시피 목록을 필터링한다
    if (!hasLengths) {
      const matches = recipes.filter((r) => r.m1_glass === m1Glass && r.m2_film === m2Film)
      setResult({ materialMatches: matches })
      setLoading(false)
      return
    }

    try {
      const res = await executionApi.get(`/recipes/${m1Length}/${m2Length}`, {
        params: {
          m1_glass: m1Glass,
          m2_film: m2Film,
          thickness: thickness === '' ? undefined : parseFloat(thickness),
        },
      })
      setResult(res.data.data)
    } catch (err) {
      if (err.response?.status === 404) {
        setResult({ notFound: true })
      } else {
        setError(err.response?.data?.message || err.message)
      }
    } finally {
      setLoading(false)
    }
  }

  // 전체 목록에서 행을 클릭하면 입력 조건을 채우고 해당 레시피를 결과로 표시한다
  const handleRowClick = (recipe) => {
    setM1Glass(recipe.m1_glass)
    setM2Film(recipe.m2_film)
    setM1Length(recipe.m1_length)
    setM2Length(recipe.m2_length)
    setThickness(recipe.thickness)
    setError(null)
    setResult({ recipe, exact_match: true, message: '레시피 조회 완료' })
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <h2>레시피 조회</h2>
      <p style={{ color: 'var(--text-muted)' }}>
        재질과 M1/M2 길이, Thickness를 입력하면 저장된 레시피(레이저 가공조건)를 조회합니다.
      </p>

      {/* 입력 영역 */}
      <div className="card" style={{ marginTop: 16, paddingBottom: 8 }}>
        <h3 style={sectionHeadStyle}>M1 소재 종류</h3>
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

        <h3 style={sectionHeadStyle}>M2 소재 종류</h3>
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

        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 20 }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            M1 ({m1Glass ?? '-'}) Length (mm) <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(선택)</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <input
                type="number"
                step="0.1"
                value={m1Length}
                onChange={(e) => setM1Length(e.target.value === '' ? '' : parseFloat(e.target.value))}
                placeholder="예: 10"
                style={{ ...inputBase, width: 120 }}
              />
              <div style={{ display: 'flex', gap: 6 }}>
                {M1_PRESETS.map((v) => (
                  <button
                    key={v}
                    type="button"
                    className={`btn btn-sm ${m1Length === v ? 'btn-selected' : ''}`}
                    onClick={() => setM1Length(v)}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            M2 ({m2Film ?? '-'}) Length (mm) <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(선택)</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <input
                type="number"
                step="0.1"
                value={m2Length}
                onChange={(e) => setM2Length(e.target.value === '' ? '' : parseFloat(e.target.value))}
                placeholder="예: 25"
                style={{ ...inputBase, width: 120 }}
              />
              <div style={{ display: 'flex', gap: 6 }}>
                {M2_PRESETS.map((v) => (
                  <button
                    key={v}
                    type="button"
                    className={`btn btn-sm ${m2Length === v ? 'btn-selected' : ''}`}
                    onClick={() => setM2Length(v)}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            Thickness (μm) <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(선택)</span>
            <input
              type="number"
              step="0.1"
              value={thickness}
              onChange={(e) => setThickness(e.target.value)}
              placeholder="예: 105.0"
              style={{ ...inputBase, width: 160 }}
            />
          </label>
        </div>

        <p style={{ color: 'var(--text-muted)', marginBottom: 12, fontSize: 13 }}>
          M1/M2 길이 없이 소재 종류만 선택하면 해당 소재 조합의 모든 레시피를 보여줍니다.
        </p>

        <button className="btn btn-primary" disabled={!canSubmit} onClick={handleSearch}>
          {loading ? <><span className="spinner" /> 조회 중...</> : '레시피 조회'}
        </button>
      </div>

      {/* 결과 영역 */}
      {error && <div className="banner banner-warning" style={{ marginTop: 4 }}>{error}</div>}

      {result?.notFound && (
        <div className="banner banner-warning" style={{ marginTop: 4 }}>
          레시피가 없습니다. Auto DOE를 실행해 새 레시피를 만들어주세요.
        </div>
      )}

      {result?.materialMatches && (
        <div className="card" style={{ marginTop: 4 }}>
          {result.materialMatches.length === 0 ? (
            <div className="banner banner-warning">
              {m1Glass} / {m2Film} 조합의 레시피가 없습니다. Auto DOE를 실행해 새 레시피를 만들어주세요.
            </div>
          ) : (
            <>
              <div className="banner banner-success">
                {m1Glass} / {m2Film} 조합의 레시피 {result.materialMatches.length}건을 찾았습니다.
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>M1</th>
                      <th>M2</th>
                      <th>Thickness</th>
                      <th>Speed</th>
                      <th>Defocus</th>
                      <th>Frequency</th>
                      <th>Power</th>
                      <th>예측 Depth</th>
                      <th>판정</th>
                      <th>승인자</th>
                      <th>승인일</th>
                    </tr>
                  </thead>
                  <tbody style={readingStyle}>
                    {result.materialMatches.map((r) => (
                      <tr key={r.id} onClick={() => handleRowClick(r)} style={{ cursor: 'pointer' }}>
                        <td>{r.id}</td>
                        <td>{r.m1_glass} {r.m1_length}mm</td>
                        <td>{r.m2_film} {r.m2_length}mm</td>
                        <td>{r.thickness}μm</td>
                        <td>{r.opt_speed}</td>
                        <td>{r.opt_defocus}</td>
                        <td>{r.opt_frequency}</td>
                        <td>{r.opt_power}</td>
                        <td>{r.pred_depth}</td>
                        <td><span className={`pill ${QUALITY_PILL[r.pred_quality] ?? 'pill-muted'}`}>{r.pred_quality}</span></td>
                        <td>{r.approved_by}</td>
                        <td>{r.created_at ? new Date(r.created_at).toLocaleDateString() : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {result?.recipe && (
        <div className="card" style={{ marginTop: 4 }}>
          <div className={`banner ${result.exact_match ? 'banner-success' : 'banner-info'}`} style={{ marginBottom: 16 }}>
            {result.exact_match
              ? '✅ 정확히 일치하는 레시피입니다.'
              : `⚠ ${result.message}`}
          </div>

          <h3 style={sectionHeadStyle}>소재 조건</h3>
          <table style={{ marginBottom: 20 }}>
            <tbody style={readingStyle}>
              <tr><td>M1</td><td>{result.recipe.m1_glass} {result.recipe.m1_length} mm</td></tr>
              <tr><td>M2</td><td>{result.recipe.m2_film} {result.recipe.m2_length} mm</td></tr>
              <tr><td>Thickness</td><td>{result.recipe.thickness} μm</td></tr>
            </tbody>
          </table>

          <h3 style={sectionHeadStyle}>레이저 가공 조건</h3>
          <table style={{ marginBottom: 20 }}>
            <tbody style={readingStyle}>
              <tr><td>Speed</td><td>{result.recipe.opt_speed} mm/s</td></tr>
              <tr><td>Defocus</td><td>{result.recipe.opt_defocus} mm</td></tr>
              <tr><td>Frequency</td><td>{result.recipe.opt_frequency} kHz</td></tr>
              <tr><td>Power</td><td>{result.recipe.opt_power} W</td></tr>
            </tbody>
          </table>

          <h3 style={sectionHeadStyle}>예측 결과 / 이력</h3>
          <table>
            <tbody style={readingStyle}>
              <tr><td>예측 Kerf</td><td>{result.recipe.pred_kerf} μm</td></tr>
              <tr><td>예측 Depth</td><td>{result.recipe.pred_depth} μm</td></tr>
              <tr><td>판정</td><td><span className={`pill ${QUALITY_PILL[result.recipe.pred_quality] ?? 'pill-muted'}`}>{result.recipe.pred_quality}</span></td></tr>
              <tr><td>신뢰도</td><td>{result.recipe.confidence != null ? `${(result.recipe.confidence * 100).toFixed(1)}%` : '-'}</td></tr>
              <tr><td>DOE 수렴 회차</td><td>{result.recipe.doe_attempts}</td></tr>
              <tr><td>승인자 / 일시</td><td>{result.recipe.approved_by} / {result.recipe.created_at ? new Date(result.recipe.created_at).toLocaleString() : '-'}</td></tr>
              {result.recipe.notes && (
                <tr><td>설명 (보고용 메모)</td><td style={{ whiteSpace: 'pre-wrap' }}>{result.recipe.notes}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* 전체 레시피 목록 */}
      <div className="card" style={{ marginTop: 4, paddingTop: 10 }}>
        <h3 style={sectionHeadStyle}>전체 레시피 목록 ({recipes.length}건)</h3>
        <p style={{ color: 'var(--text-muted)', marginBottom: 8 }}>행을 클릭하면 위 입력 조건과 결과에 반영됩니다.</p>
        {listError && <div className="banner banner-warning">{listError}</div>}

        {/* 레시피가 6건 이상이면 고정 높이 슬라이드(스크롤) 윈도우로 표시 */}
        <div style={{ overflowX: 'auto', ...(recipes.length >= 6 ? { maxHeight: 240, overflowY: 'auto' } : {}) }}>
          <table>
            <thead style={recipes.length >= 6 ? { position: 'sticky', top: 0, zIndex: 1 } : undefined}>
              <tr>
                <th>ID</th>
                <th>M1</th>
                <th>M2</th>
                <th>Thickness</th>
                <th>Speed</th>
                <th>Defocus</th>
                <th>Frequency</th>
                <th>Power</th>
                <th>예측 Depth</th>
                <th>판정</th>
                <th>승인자</th>
                <th>승인일</th>
              </tr>
            </thead>
            <tbody style={readingStyle}>
              {recipes.map((r) => (
                <tr key={r.id} onClick={() => handleRowClick(r)} style={{ cursor: 'pointer' }}>
                  <td>{r.id}</td>
                  <td>{r.m1_glass} {r.m1_length}mm</td>
                  <td>{r.m2_film} {r.m2_length}mm</td>
                  <td>{r.thickness}μm</td>
                  <td>{r.opt_speed}</td>
                  <td>{r.opt_defocus}</td>
                  <td>{r.opt_frequency}</td>
                  <td>{r.opt_power}</td>
                  <td>{r.pred_depth}</td>
                  <td><span className={`pill ${QUALITY_PILL[r.pred_quality] ?? 'pill-muted'}`}>{r.pred_quality}</span></td>
                  <td>{r.approved_by}</td>
                  <td>{r.created_at ? new Date(r.created_at).toLocaleDateString() : '-'}</td>
                </tr>
              ))}
              {recipes.length === 0 && (
                <tr><td colSpan={12} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>저장된 레시피가 없습니다</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
