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
  file_type: 'pdf' | 'txt' | 'none';
  file_name: string | null;
  content?: string;
}

export interface NormalizedIntent {
  request_id: string;
  task_type: TaskType;
  input_mode: InputMode;
  user_prompt: string;
  document_metadata: DocumentMetadata;
  content_scope: string;
  constraints: {
    hallucination_allowed: boolean;
    output_structure_required: boolean;
  };
  timestamp: string;
}

export interface FinalReportJSON {
  request_id: string;
  status: 'completed' | 'error';
  report: {
    executive_summary: string;
    highlights: string[];
    risks_and_blockers: string[];
    actions_required: string[];
    evidence_links: string[];
  };
  source_type: 'text' | 'document';
  confidence_level: 'high' | 'medium' | 'low';
  generated_at: string;
}

export interface ValidationError {
  status: 'error';
  error_type: 'INVALID_PROMPT' | 'MISSING_DOCUMENT' | 'UNSUPPORTED_TASK' | 'INVALID_FORMAT';
  message: string;
}

export type AgentResponse = {
  naturalReport: string;
  structuredJSON: FinalReportJSON;
};

export type AgentWorkflowStatus = 'idle' | 'validating' | 'normalizing' | 'generating' | 'completed' | 'error';
