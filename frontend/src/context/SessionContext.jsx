import { createContext, useContext, useState } from 'react'

const SessionContext = createContext(null)

const initialState = {
  // 소재 조건 (ExperimentPage)
  material: { m1_length: null, m2_length: null, thickness: '', m1_glass: null, m2_film: null },
  // 이번 세션의 Auto DOE 시도 이력 (재제안 시 GP에 누적 전달)
  experimentHistory: [],
  // 가장 최근 /doe/suggest 응답
  suggestion: null,
  // /doe/approve 결과
  approval: null,
  // 운영자 이름
  operatorName: '운영자',
}

export function SessionProvider({ children }) {
  const [session, setSession] = useState(initialState)

  const updateMaterial = (material) =>
    setSession((s) => ({ ...s, material }))

  const setSuggestion = (suggestion) =>
    setSession((s) => ({ ...s, suggestion }))

  const setApproval = (approval) =>
    setSession((s) => ({ ...s, approval }))

  const addHistoryEntry = (entry) =>
    setSession((s) => ({ ...s, experimentHistory: [...s.experimentHistory, entry] }))

  const resetSession = () => setSession(initialState)

  // 새 소재 조건으로 시작 (이력 초기화)
  const startNewMaterial = (material) =>
    setSession((s) => ({
      ...initialState,
      material,
      operatorName: s.operatorName,
    }))

  return (
    <SessionContext.Provider
      value={{
        session,
        updateMaterial,
        setSuggestion,
        setApproval,
        addHistoryEntry,
        resetSession,
        startNewMaterial,
      }}
    >
      {children}
    </SessionContext.Provider>
  )
}

export function useSession() {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error('useSession은 SessionProvider 내부에서만 사용할 수 있습니다')
  return ctx
}
