
import { GoogleGenAI, Type } from "@google/genai";
import { 
  NormalizedIntent, 
  FinalReportJSON, 
  TaskType, 
  InputMode,
  DocumentMetadata 
} from "../types";
import { logger } from "./logger";

export class GeminiReportingService {
  async normalizeIntent(
    prompt: string, 
    docMeta: DocumentMetadata
  ): Promise<NormalizedIntent> {
    const requestId = `req_${Date.now()}`;
    const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });
    
    logger.log("Guardrail: Normalizing Intent & Assessing Scope", "api", { prompt });

    try {
      const response = await ai.models.generateContent({
        model: "gemini-3-flash-preview",
        contents: `User Prompt: ${prompt}\nDocument Context: ${docMeta.attached ? 'Attached: ' + docMeta.file_name : 'None'}`,
        config: {
          systemInstruction: `You are a Domain Guardrail Specialist. 
          1. Classify the task as REPORTING_TASK or IRRELEVANT (chat, code, casual talk).
          2. Score intent confidence (0.0 to 1.0). If goal is vague, score < 0.3.
          3. CATEGORIZATION ARCHETYPES: You must map the document to a standard mid-level professional archetype. 
             - STRICT RULE: Do NOT use the document's title or specific topic as the category name.
             - STRICT RULE: Similar document types MUST be classified with the same archetype name to ensure consistency.
             - PRIORITY TAXONOMY:
               - Scientific or Research documents -> 'Academic Research'
               - Presentation slides or summaries -> 'Business/Technical Presentation'
               - Lectures or educational notes -> 'Educational Material'
               - Job specs or resumes -> 'Employment Document'
               - Financial docs or audits -> 'Financial Report'
               - Manuals or tech docs -> 'Technical Documentation'
               - Industry-specific reports (e.g. NASA, SpaceX) -> '[Industry Name] Industry' (e.g., 'Aerospace Industry')
             - Examples:
               - "CS Technical Report" and "Research Presentation" -> both should be 'Academic Research' or 'Technical Documentation' depending on depth.
               - "Bio Lecture 1" and "History Notes" -> both should be 'Educational Material'.
          4. Map the analytical scope precisely.`,
          responseMimeType: "application/json",
          responseSchema: {
            type: Type.OBJECT,
            properties: {
              is_supported: { type: Type.BOOLEAN },
              confidence_score: { type: Type.NUMBER },
              detected_category: { type: Type.STRING, description: "A standard archetype category (e.g., 'Academic Research')" },
              task_type: { type: Type.STRING, enum: ["summary", "report"] },
              input_mode: { type: Type.STRING, enum: ["text_only", "document_based"] },
              content_scope: { type: Type.STRING },
              rejection_reason: { type: Type.STRING }
            },
            required: ["is_supported", "confidence_score", "detected_category", "task_type", "input_mode", "content_scope"]
          },
        },
      });

      const result = JSON.parse(response.text || "{}");

      if (!result.is_supported) {
        logger.log("Guardrail: Task rejected (Out of Scope)", "guardrail", result.rejection_reason);
        throw new Error(result.rejection_reason || "IRRELEVANT_TASK: This agent only handles analysis and reporting.");
      }

      return {
        request_id: requestId,
        task_type: result.task_type as TaskType,
        input_mode: result.input_mode as InputMode,
        user_prompt: prompt,
        detected_category: result.detected_category || 'Professional Analysis',
        document_metadata: docMeta,
        content_scope: result.content_scope,
        confidence_score: result.confidence_score,
        is_ambiguous: result.confidence_score < 0.3,
        is_supported: result.is_supported,
        constraints: { hallucination_allowed: false, output_structure_required: true },
        timestamp: new Date().toISOString(),
      };
    } catch (e: any) {
      logger.log(`Guardrail Error: ${e.message}`, "error");
      throw e;
    }
  }

  async checkDocumentSignal(fileBase64: string, mimeType: string): Promise<boolean> {
    const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });
    logger.log("Guardrail: Checking Document Signal Strength", "guardrail");
    
    try {
      const response = await ai.models.generateContent({
        model: "gemini-3-flash-preview",
        contents: [
          { inlineData: { mimeType, data: fileBase64 } },
          { text: "Does this document contain meaningful analytical data or text relevant for a professional report? Respond with true/false only." }
        ],
        config: {
          responseMimeType: "application/json",
          responseSchema: {
            type: Type.OBJECT,
            properties: { has_signal: { type: Type.BOOLEAN } },
            required: ["has_signal"]
          }
        }
      });
      const res = JSON.parse(response.text || "{}");
      return res.has_signal ?? true;
    } catch {
      return true; // Default to true if signal check fails
    }
  }

  async generateReport(
    intent: NormalizedIntent,
    fileBase64?: string,
    memoryContext: string = ""
  ): Promise<FinalReportJSON> {
    const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });
    
    // GUARDRAIL 5: Conflict Resolution Hierarchy
    const override = intent.user_prompt;
    const longTerm = memoryContext || "Apply standard professional reporting standards.";

    logger.log(`Guardrail: Generating with Fact-Check Policy for domain: ${intent.detected_category}`, "api");

    const parts: any[] = [{ text: `
      --- POLICY GUARDRAILS ---
      1. ZERO HALLUCINATION: Forbid estimation. If data is missing from source, state "Not Found".
      2. FACT-CHECK: Every data point MUST map to a source span.
      3. OUTPUT SCOPE: Do not over-deliver. Stick strictly to the objective: "${intent.content_scope}".
      4. MATH FORMATTING: All Big O, formulas, and technical metrics MUST be bolded: **O(N^2)**.

      --- DOMAIN CONTEXT ---
      Identified Category: ${intent.detected_category}

      --- OVERRIDE HIERARCHY ---
      - HIGHEST PRIORITY: Current User Objective: "${override}"
      - SECONDARY: Stored Style Laws: "${longTerm}"
      Note: The Current User Objective ALWAYS overrides Stored Style Laws for this session.
    ` }];
    
    if (fileBase64) {
      const mime = intent.document_metadata.file_type === 'pdf' ? 'application/pdf' : 'text/plain';
      parts.push({ inlineData: { mimeType: mime, data: fileBase64 } });
    }

    const response = await ai.models.generateContent({
      model: "gemini-3-flash-preview",
      contents: { parts },
      config: {
        systemInstruction: `You are a Fact-Grounded Reporting Agent specialized in ${intent.detected_category}. 
        MANDATORY: Output "Not Found" if evidence is missing. 
        Zero tolerance for hallucination or estimation. 
        Apply style laws exactly.`,
        responseMimeType: "application/json",
        responseSchema: this.getReportSchema()
      },
    });

    return this.parseResponse(response.text, intent.request_id, intent.input_mode);
  }

  async refineReport(
    previousReport: FinalReportJSON,
    suggestion: string,
    intent: NormalizedIntent,
    memoryContext: string = ""
  ): Promise<FinalReportJSON> {
    const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });
    
    const response = await ai.models.generateContent({
      model: "gemini-3-flash-preview",
      contents: `
        HARD CONSTRAINTS: ${memoryContext}
        NEW OVERRIDE: "${suggestion}"
        PREVIOUS DATA: ${JSON.stringify(previousReport.report)}
        
        CRITICAL: Apply the command while respecting existing grounding and bolding policies for the domain: ${intent.detected_category}.
      `,
      config: {
        systemInstruction: `Refinement Mode. Grounding must be preserved.`,
        responseMimeType: "application/json",
        responseSchema: this.getReportSchema()
      },
    });

    return this.parseResponse(response.text, previousReport.request_id, previousReport.source_type === 'document' ? InputMode.DOCUMENT_BASED : InputMode.TEXT_ONLY);
  }

  async extractStylePreferences(
    intent: NormalizedIntent,
    iterations: string[],
    finalReport: FinalReportJSON,
    currentMemory: string
  ): Promise<{ newMemory: string, interactionSummary: string }> {
    const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });
    
    logger.log("Guardrail: Meta-Learning Feedback Integrity", "api");

    const response = await ai.models.generateContent({
      model: "gemini-3-pro-preview",
      contents: `
        DOMAIN: ${intent.detected_category}
        EXISTING RULES: "${currentMemory}"
        FEEDBACK HISTORY: [${iterations.join(' THEN ')}]
        SUCCESSFUL OUTPUT: ${JSON.stringify(finalReport.report).substring(0, 1000)}
      `,
      config: {
        systemInstruction: `You are a Style Invariant Analyst. 
        Extract PERMANENT formatting or structural rules from the feedback history for the specific domain: ${intent.detected_category}.
        - IGNORE data corrections. 
        - CAPTURE style patterns (e.g. "always bold dates"). 
        - DELAYED LEARNING: Only commit rules that appear as consistent patterns.`,
        responseMimeType: "application/json",
        responseSchema: {
          type: Type.OBJECT,
          properties: {
            preference_rules: { type: Type.STRING },
            interaction_summary: { type: Type.STRING }
          },
          required: ["preference_rules", "interaction_summary"]
        }
      },
    });

    try {
      const res = JSON.parse(response.text || "{}");
      return {
        newMemory: res.preference_rules || currentMemory,
        interactionSummary: res.interaction_summary || `Session complete.`
      };
    } catch (e) {
      return { newMemory: currentMemory, interactionSummary: "Session complete." };
    }
  }

  private getReportSchema() {
    return {
      type: Type.OBJECT,
      properties: {
        report: {
          type: Type.OBJECT,
          properties: {
            executive_summary: { type: Type.STRING },
            highlights: { type: Type.ARRAY, items: { type: Type.STRING } },
            risks_and_blockers: { type: Type.ARRAY, items: { type: Type.STRING } },
            actions_required: { type: Type.ARRAY, items: { type: Type.STRING } },
            evidence_links: { type: Type.ARRAY, items: { type: Type.STRING } },
            additional_sections: { 
              type: Type.ARRAY, 
              items: { 
                type: Type.OBJECT, 
                properties: { title: { type: Type.STRING }, content: { type: Type.STRING } },
                required: ["title", "content"]
              } 
            }
          },
          required: ["executive_summary", "highlights", "risks_and_blockers", "actions_required", "evidence_links", "additional_sections"]
        },
        confidence_level: { type: Type.STRING, enum: ["high", "medium", "low"] }
      },
      required: ["report", "confidence_level"]
    };
  }

  private parseResponse(jsonStr: string | undefined, id: string, mode: InputMode): FinalReportJSON {
    try {
      const raw = JSON.parse(jsonStr || "{}");
      const data = raw.report || raw;
      return {
        request_id: id,
        status: 'completed',
        report: {
          executive_summary: data.executive_summary || "Not Found.",
          highlights: Array.isArray(data.highlights) ? data.highlights : [],
          risks_and_blockers: Array.isArray(data.risks_and_blockers) ? data.risks_and_blockers : [],
          actions_required: Array.isArray(data.actions_required) ? data.actions_required : [],
          evidence_links: Array.isArray(data.evidence_links) ? data.evidence_links : [],
          additional_sections: Array.isArray(data.additional_sections) ? data.additional_sections : []
        },
        source_type: mode === InputMode.DOCUMENT_BASED ? 'document' : 'text',
        confidence_level: raw.confidence_level || 'medium',
        generated_at: new Date().toISOString()
      };
    } catch (e) {
      throw new Error("Analysis parsing failed.");
    }
  }
}
