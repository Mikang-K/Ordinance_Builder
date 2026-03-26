export type Stage =
  | 'intent_analysis'
  | 'interviewing'
  | 'retrieving'
  | 'drafting'
  | 'draft_review'
  | 'legal_review_requested'
  | 'legal_checking'
  | 'completed'

export interface SimilarOrdinance {
  ordinance_id: string
  region_name: string
  title: string
  similarity_score: number
  relevance_reason: string
}

export interface LegalIssue {
  severity: 'HIGH' | 'MEDIUM' | 'LOW'
  related_statute?: string
  related_provision?: string
  description: string
  suggestion?: string
}

export interface ChatMessage {
  role: 'user' | 'ai'
  text: string
}

export interface SessionCreateResponse {
  session_id: string
  message: string
  stage: Stage
}

export interface ChatResponse {
  session_id: string
  message: string
  stage: Stage
  is_complete: boolean
  draft?: string
  legal_issues?: LegalIssue[]
  is_legally_valid?: boolean | null
  similar_ordinances?: SimilarOrdinance[]
}

export interface FinalizeResponse {
  session_id: string
  draft: string
  legal_issues: LegalIssue[]
  is_legally_valid: boolean | null
}
