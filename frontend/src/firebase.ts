import { initializeApp } from 'firebase/app'
import {
  GoogleAuthProvider,
  User,
  getAuth,
  onAuthStateChanged,
  signInWithPopup,
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

export const loginWithGoogle = () => signInWithPopup(auth, googleProvider)
export const logout = () => signOut(auth)
export { onAuthStateChanged }
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
