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

export interface SuggestedOption {
  label: string
  value: string
}

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
  suggested_options?: SuggestedOption[]
}

export interface SessionCreateResponse {
  session_id: string
  message: string
  stage: Stage
  article_queue?: string[]
  current_article_key?: string | null
  similar_ordinances?: SimilarOrdinance[]
  suggested_options?: SuggestedOption[]
  ordinance_type?: string | null
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
  suggested_options?: SuggestedOption[]
  ordinance_type?: string | null
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
  ordinance_type?: string | null
  qa_history?: QAMessage[] | null
}

export type RevisionStatus =
  | 'editing_articles'
  | 'drafting'
  | 'editing_draft'
  | 'legal_reviewing'
  | 'ready_to_finalize'
  | 'completed'

export interface WorkspaceRevision {
  revision_id: string
  revision_number: number
  status: RevisionStatus
  version: number
  article_contents: Record<string, string | null>
  draft_full_text: string
  legal_issues: LegalIssue[]
  is_legally_valid: boolean | null
  legal_reviewed_at: string | null
  finalized_at: string | null
  created_at: string
  updated_at: string
  based_on_revision_id: string | null
}

export interface WorkspaceResponse {
  session_id: string
  active_revision_id: string | null
  finalized_revision_id: string | null
  active_revision: WorkspaceRevision | null
  finalized_revision: WorkspaceRevision | null
  revisions: WorkspaceRevision[]
  can_edit_articles: boolean
  can_edit_draft: boolean
  can_finalize: boolean
  regeneration_required: string | null
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

export interface EvidenceItem {
  id: string
  source_type: QASource['source_type']
  title: string
  article_no: string
  content: string
  relation_type?: string | null
  target_article_key?: string | null
  applicable_content?: string | null
  note?: string | null
  source_message_id?: string | null
  created_at: string
  applied_at?: string | null
}

export type EvidenceCreateInput = Omit<EvidenceItem, 'id' | 'created_at' | 'applied_at'>
export type EvidenceUpdateInput = Partial<EvidenceCreateInput>

export interface EvidenceApplyRequest {
  requestId: number
  content: string
  title: string
  targetArticleKey: string
  evidenceId?: string
}

export type ModelDeployment = 'local' | 'cloud' | string
export type ModelAvailability = 'available' | 'degraded' | 'unavailable' | string
export interface ModelRuntimeStatus { role: string; provider: string; model: string; deployment: ModelDeployment; status: ModelAvailability; detail?: string | null }
export interface ModelStatusResponse { status: ModelAvailability; models: ModelRuntimeStatus[] }
