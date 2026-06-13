import { useEffect, useState } from 'react'
import { executionApi } from '../api/client'

const QUALITY_PILL = {
  OK: 'pill-ok',
  미가공: 'pill-warn',
  과가공: 'pill-warn',
  NG: 'pill-danger',
}

const QUALITY_OPTIONS = ['', 'OK', '미가공', '과가공', 'NG']

const PAGE_SIZE = 20

// 산업용 콘솔 톤: 섹션 헤더 액센트 좌측 바, 수치 판독값 모노스페이스(계기판 느낌), 필터 입력 각진 모서리 — 타 화면과 통일
const sectionHeadStyle = {
  paddingLeft: 8,
  borderLeft: '3px solid var(--accent)',
  lineHeight: 1.2,
}
const readingStyle = {
  fontFamily: 'ui-monospace, Consolas, "Courier New", monospace',
}
const filterInputStyle = {
  padding: '8px 10px',
  border: '1px solid #c7cbd1',
  borderRadius: 4,
}

export default function ExperimentHistoryPage() {
  const [quality, setQuality] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)

  const [experiments, setExperiments] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const load = () => {
    setLoading(true)
    setError(null)
    executionApi
      .get('/experiments', {
        params: {
          quality: quality || undefined,
          search: search.trim() || undefined,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
        },
      })
      .then((res) => {
        setExperiments(res.data.data.experiments)
        setTotal(res.data.data.total)
      })
      .catch((err) => setError(err.response?.data?.message || err.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quality, page])

  const handleSearch = () => {
    setPage(0)
    load()
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <h2>실험 이력 조회</h2>
      <p style={{ color: 'var(--text-muted)' }}>
        Auto DOE로 수행된 모든 실험 결과(판정/실측값/보고용 설명)를 조회합니다.
      </p>

      {/* 필터 영역 */}
      <div className="card" style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            판정
            <select
              value={quality}
              onChange={(e) => { setPage(0); setQuality(e.target.value) }}
              style={{ ...filterInputStyle, width: 140 }}
            >
              {QUALITY_OPTIONS.map((q) => (
                <option key={q} value={q}>{q === '' ? '전체' : q}</option>
              ))}
            </select>
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: 1, minWidth: 240 }}>
            검색 (실험 번호 / 설명)
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="예: DOE-1234abcd 또는 메모 내용 일부"
              style={filterInputStyle}
            />
          </label>
          <button className="btn btn-primary" onClick={handleSearch} disabled={loading}>
            {loading ? <><span className="spinner" /> 조회 중...</> : '검색'}
          </button>
        </div>
      </div>

      {error && <div className="banner banner-warning" style={{ marginTop: 16 }}>{error}</div>}

      {/* 결과 목록 */}
      <div className="card" style={{ marginTop: 16 }}>
        <h3 style={sectionHeadStyle}>실험 결과 ({total}건)</h3>

        {experiments.length === 0 && !loading && (
          <p style={{ textAlign: 'center', color: 'var(--text-muted)' }}>조회된 실험 이력이 없습니다</p>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {experiments.map((e) => (
            <div
              key={e.id}
              style={{
                display: 'flex',
                gap: 16,
                border: '1px solid var(--border)',
                borderRadius: 8,
                padding: 14,
                flexWrap: 'wrap',
              }}
            >
              {/* 파라미터: 입력값 / 가공 조건 / 측정 결과 3개 컬럼 그룹으로 표시 */}
              <div style={{ minWidth: 360, display: 'flex', flexDirection: 'column', gap: 8, fontSize: 14, ...readingStyle }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <strong>{e.exp_no}</strong>
                  <span className={`pill ${QUALITY_PILL[e.quality] ?? 'pill-muted'}`}>{e.quality}</span>
                </div>
                <div style={{ display: 'flex', gap: 20 }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>입력값</div>
                    <div>M1: {e.m1_glass} {e.m1_length}mm</div>
                    <div>M2: {e.m2_film} {e.m2_length}mm</div>
                    <div>Thickness: {e.thickness}μm</div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>가공 조건</div>
                    <div>Speed: {e.speed}</div>
                    <div>Defocus: {e.defocus}</div>
                    <div>Frequency: {e.frequency}</div>
                    <div>Power: {e.power}</div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>측정 결과</div>
                    <div>Kerf: {e.kerf}μm</div>
                    <div>Depth: {e.depth}μm</div>
                  </div>
                </div>
                <div style={{ color: 'var(--text-muted)', marginTop: 4 }}>
                  {e.created_at ? new Date(e.created_at).toLocaleString() : '-'}
                </div>
              </div>

              {/* 설명(보고용): 최대한 넓게 */}
              <div style={{ flex: 1, minWidth: 280, display: 'flex', flexDirection: 'column' }}>
                <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 6 }}>설명 (보고용)</div>
                <div
                  style={{
                    flex: 1,
                    whiteSpace: 'pre-wrap',
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    borderRadius: 6,
                    padding: 10,
                    fontSize: 14,
                    lineHeight: 1.6,
                  }}
                >
                  {e.notes || '-'}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* 페이지네이션 */}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', alignItems: 'center', marginTop: 16 }}>
          <button className="btn btn-sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            이전
          </button>
          <span style={{ color: 'var(--text-muted)', fontSize: 14 }}>
            {page + 1} / {totalPages}
          </span>
          <button className="btn btn-sm" disabled={page + 1 >= totalPages} onClick={() => setPage((p) => p + 1)}>
            다음
          </button>
        </div>
      </div>
    </div>
  )
}
