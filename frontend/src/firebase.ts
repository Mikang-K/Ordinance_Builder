import { initializeApp } from 'firebase/app'
import {
  GoogleAuthProvider,
  User,
  getAuth,
  getRedirectResult,
  onAuthStateChanged,
  signInWithPopup,
  signInWithRedirect,
  signOut,
} from 'firebase/auth'

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
}

const app = initializeApp(firebaseConfig)
export const auth = getAuth(app)
export const googleProvider = new GoogleAuthProvider()

const isLocalDevelopment =
  window.location.hostname === 'localhost' ||
  window.location.hostname === '127.0.0.1'

export const loginWithGoogle = async () => {
  // 로컬에서는 Firebase 인증 도메인과 앱의 출처가 달라 redirect 인증 상태가
  // 브라우저의 타사 저장소 제한에 의해 유실될 수 있으므로 popup 방식을 사용한다.
  if (isLocalDevelopment) {
    await signInWithPopup(auth, googleProvider)
    return
  }

  // 배포 환경에서는 기존 Firebase Hosting redirect 로그인 흐름을 유지한다.
  await signInWithRedirect(auth, googleProvider)
}
export const logout = () => signOut(auth)
export { onAuthStateChanged, getRedirectResult }
export type { User }

/**
 * 현재 로그인된 사용자의 Firebase ID Token을 반환합니다.
 * 토큰은 1시간마다 자동 갱신되며, getIdToken()이 필요 시 갱신을 처리합니다.
 */
export async function getIdToken(): Promise<string> {
  const user = auth.currentUser
  if (!user) throw new Error('로그인이 필요합니다.')
  return user.getIdToken()
}
