// 관리자 콘솔 접근 비밀번호 게이트 설정
//
// - ADMIN_AUTH_ENABLED: 비밀번호 창(모달) 사용 여부
//     false  → 게이트 없이 바로 접근
//     true   → '관리자' 메뉴 진입 시 비밀번호 모달이 뜸 (현재 설정)
//   (이 파일을 저장하면 프런트엔드에 즉시 반영됩니다 — HMR, 재빌드 불필요)
//
// - ADMIN_AUTH_TEST_BYPASS: 테스트 단계 바이패스
//     true   → 모달은 뜨지만 비밀번호 검증 없이 [확인]만 누르면 입장 (현재, 테스트용)
//     false  → 운영 배포 시. ADMIN_PASSWORD와 일치해야만 입장
//
// - ADMIN_PASSWORD: 관리자 콘솔 접근 비밀번호 (운영 시 반드시 변경)
//
// 참고: 이 게이트는 화면(UI) 접근을 막는 용도입니다. API 자체 보안이 필요하면
//       별도로 백엔드 인증을 붙여야 합니다.
export const ADMIN_AUTH_ENABLED = true
export const ADMIN_AUTH_TEST_BYPASS = true
export const ADMIN_PASSWORD = 'ades-admin'
