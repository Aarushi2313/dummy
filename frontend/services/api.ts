import { NormalizedIntent, FinalReportJSON, AgentResponse } from '../types';

const API_BASE_URL = 'http://localhost:8000';

export class ApiService {
  /**
   * Generates a report by asking the backend FastAPI service
   */
  async generateReport(intent: NormalizedIntent): Promise<AgentResponse> {
    const response = await fetch(`${API_BASE_URL}/report`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        report_type: intent.task_type === 'summary' ? 'weekly_summary' : 'daily_brief',
        user_role: 'admin',
        time_window: {
          start: new Date(Date.now() - 86400000).toISOString(),
          end: new Date().toISOString()
        },
        custom_prompt: intent.user_prompt // Send the real prompt to the backend LLM loop
      })
    });

    if (!response.ok) {
      throw new Error(`API Error: ${response.statusText}`);
    }

    const data = await response.json();
    
    // Parse backend JSON model to frontend expectation skeleton
    return {
      naturalReport: `Report generated on ${data.generated_at} with status ${data.data_completeness}.`,
      structuredJSON: {
        request_id: intent.request_id,
        status: data.data_completeness.includes('failed') ? 'failed' : 'completed',
        report: {
          executive_summary: data.summary.executive_summary || "Automated aggregation report",
          highlights: data.summary.highlights || [`Total actions: ${data.summary.total_actions || 0}`],
          risks_and_blockers: data.risks.map((r: any) => `[${r.severity}] ${r.issue}`) || [],
          actions_required: data.approvals_needed.map((a: any) => `[Urgency: ${a.urgency}] ${a.item}`) || [],
          evidence_links: []
        },
        source_type: 'llm_inference',
        confidence_level: data.data_completeness.includes('failed') ? 'low' : 'high',
        generated_at: data.generated_at
      }
    };
  }
}
