export type Stage =
  | 'intent_analysis'
  | 'interviewing'
  | 'article_interviewing'
  | 'article_complete'
  | 'retrieving'
  | 'drafting'
  | 'draft_review'
  | 'legal_review_requested'
  | 'legal_checking'
  | 'completed'
  | 'error'

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
  article_queue?: string[]
  current_article_key?: string | null
  similar_ordinances?: SimilarOrdinance[]
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
  article_queue?: string[]
  current_article_key?: string | null
}

export interface FinalizeResponse {
  session_id: string
  draft: string
  legal_issues: LegalIssue[]
  is_legally_valid: boolean | null
}

export interface SessionSummary {
  session_id: string
  title: string
  stage: Stage
  created_at: string
}

export interface SessionStateResponse {
  session_id: string
  title: string
  stage: Stage
  created_at: string
  messages: ChatMessage[]
  draft?: string
  similar_ordinances?: SimilarOrdinance[]
  legal_issues?: LegalIssue[]
  ordinance_info: Record<string, string>
  article_queue?: string[] | null
  current_article_key?: string | null
}

export interface QASource {
  source_type: 'statute' | 'ordinance' | 'legal_term'
  title: string
  article_no: string
  content: string
  relation_type: string
}

export interface QAMessage {
  role: 'user' | 'ai'
  text: string
  sources?: QASource[]
  applicable_content?: string | null
  applicable_article_key?: string | null
}

export interface QAResponse {
  answer: string
  sources: QASource[]
  applicable_content?: string | null
  applicable_article_key?: string | null
}
