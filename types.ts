
export enum TaskType {
  SUMMARY = 'summary',
  REPORT = 'report'
}

export enum InputMode {
  TEXT_ONLY = 'text_only',
  DOCUMENT_BASED = 'document_based'
}

export interface DocumentMetadata {
  attached: boolean;
  file_type: 'pdf' | 'txt' | 'docx' | 'none';
  file_name: string | null;
  content?: string;
  size?: number;
  low_signal?: boolean;
}

export interface CustomSection {
  title: string;
  content: string;
}

export interface NormalizedIntent {
  request_id: string;
  task_type: TaskType;
  input_mode: InputMode;
  user_prompt: string;
  detected_category: string;
  content_scope: string;
  confidence_score: number;
  is_ambiguous: boolean;
  is_supported: boolean;
  rejection_reason?: string;
  constraints: {
    hallucination_allowed: boolean;
    output_structure_required: boolean;
  };
  timestamp: string;
  document_metadata: DocumentMetadata;
}

export interface FinalReportJSON {
  request_id: string;
  status: 'completed' | 'error' | 'cached';
  report: {
    executive_summary: string;
    highlights: string[];
    risks_and_blockers: string[];
    actions_required: string[];
    evidence_links: string[];
    additional_sections: CustomSection[];
  };
  source_type: 'text' | 'document';
  confidence_level: 'high' | 'medium' | 'low';
  generated_at: string;
}

export type AgentWorkflowStatus = 'idle' | 'validating' | 'ambiguous' | 'normalizing' | 'generating' | 'refining' | 'completed' | 'error' | 'low_signal';

export interface ValidationError {
  status: 'error';
  error_type: 'UNSUPPORTED_TASK' | 'INVALID_FORMAT' | 'INVALID_PROMPT' | 'MISSING_DOCUMENT' | 'LOW_SIGNAL' | 'DUPLICATE' | 'IRRELEVANT' | 'AMBIGUOUS';
  message: string;
}

export type LogType = 'info' | 'warn' | 'error' | 'success' | 'api' | 'db' | 'guardrail';

export interface LogEntry {
  id: string;
  timestamp: string;
  type: LogType;
  message: string;
  payload?: any;
}
