import os
import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from google import genai
from google.genai import types
from dotenv import load_dotenv

from schemas import (
    NormalizedIntent, FinalReportJSON, TaskType, InputMode, 
<<<<<<< HEAD
    DocumentMetadata, ReportContent, CustomSection, Constraints
=======
    DocumentMetadata, ReportContent, CustomSection, Constraints, Diagram
>>>>>>> br1
)
from .logger import logger

from pathlib import Path

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

class GeminiReportingService:
    def __init__(self):
        self.api_key = os.getenv("API_KEY")
        if not self.api_key:
            logger.log("API_KEY is missing from environment variables.", "error")
            # We don't raise immediately to allow app to start, but calls will fail.
            # Or better, let's warn.
            print("CRITICAL WARNING: API_KEY is missing in backend/.env. AI features will fail.")
        else:
            self.client = genai.Client(api_key=self.api_key)

    async def normalize_intent(self, prompt: str, doc_meta: DocumentMetadata) -> NormalizedIntent:
        request_id = f"req_{int(time.time() * 1000)}"
        
        logger.log("Guardrail: Normalizing Intent & Assessing Scope", "api", {"prompt": prompt})

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"User Prompt: {prompt}\nDocument Context: {'Attached: ' + doc_meta.file_name if doc_meta.attached and doc_meta.file_name else 'None'}",
                config=types.GenerateContentConfig(
                    system_instruction="""You are a Domain Guardrail Specialist. 
          1. Classify the task as REPORTING_TASK or IRRELEVANT (chat, code, casual talk).
          2. Score intent confidence (0.0 to 1.0). If goal is vague, score < 0.4.
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
          4. Map the analytical scope precisely.""",
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {
                            "is_supported": {"type": "BOOLEAN"},
                            "confidence_score": {"type": "NUMBER"},
                            "detected_category": {"type": "STRING", "description": "A standard archetype category (e.g., 'Academic Research')"},
                            "task_type": {"type": "STRING", "enum": ["summary", "report"]},
                            "input_mode": {"type": "STRING", "enum": ["text_only", "document_based"]},
                            "content_scope": {"type": "STRING"},
                            "rejection_reason": {"type": "STRING"}
                        },
                        "required": ["is_supported", "confidence_score", "detected_category", "task_type", "input_mode", "content_scope"]
                    }
                )
            )

            result = json.loads(response.text or "{}")

            if not result.get("is_supported"):
                logger.log("Guardrail: Task rejected (Out of Scope)", "guardrail", result.get("rejection_reason"))
                raise Exception(result.get("rejection_reason") or "IRRELEVANT_TASK: This agent only handles analysis and reporting.")

            return NormalizedIntent(
                request_id=request_id,
                task_type=TaskType(result["task_type"]),
                input_mode=InputMode(result["input_mode"]),
                user_prompt=prompt,
                detected_category=result.get("detected_category") or 'Professional Analysis',
                document_metadata=doc_meta,
                content_scope=result["content_scope"],
                confidence_score=result["confidence_score"],
                is_ambiguous=result["confidence_score"] < 0.4,
                is_supported=result["is_supported"],
                constraints=Constraints(hallucination_allowed=False, output_structure_required=True),
                timestamp=datetime.now().isoformat()
            )
        except Exception as e:
            logger.log(f"Guardrail Error: {str(e)}", "error")
            raise e

    async def check_document_signal(self, file_base64: str, mime_type: str) -> bool:
        logger.log("Guardrail: Checking Document Signal Strength", "guardrail")
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Part.from_bytes(data=file_base64, mime_type=mime_type),
                    "Does this document contain meaningful analytical data or text relevant for a professional report? Respond with true/false only."
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {"has_signal": {"type": "BOOLEAN"}},
                        "required": ["has_signal"]
                    }
                )
            )
            res = json.loads(response.text or "{}")
            return res.get("has_signal", True)
        except:
            return True

    async def generate_report(
        self,
        intent: NormalizedIntent,
        file_base64: Optional[str] = None,
        memory_context: str = ""
    ) -> FinalReportJSON:
        
        override = intent.user_prompt
        long_term = memory_context or "Apply standard professional reporting standards."

        logger.log(f"Guardrail: Generating with Fact-Check Policy for domain: {intent.detected_category}", "api")

<<<<<<< HEAD
        parts = [f"""
      --- POLICY GUARDRAILS ---
      1. ZERO HALLUCINATION: Forbid estimation. If data is missing from source, state "Not Found".
      2. FACT-CHECK: Every data point MUST map to a source span.
      3. OUTPUT SCOPE: Do not over-deliver. Stick strictly to the objective: "{intent.content_scope}".
      4. MATH FORMATTING: All Big O, formulas, and technical metrics MUST be bolded: **O(N^2)**.
=======
        if intent.input_mode == InputMode.DOCUMENT_BASED:
            hallucination_policy = "1. ZERO HALLUCINATION: Forbid estimation. If data is missing from source, state 'Not Found'. FACT-CHECK: Every data point MUST map to a source span."
        else:
            hallucination_policy = "1. KNOWLEDGE BASE: Use your extensive internal knowledge to generate a comprehensive, detailed, and highly informative report on the user's prompt. Do not limit yourself to just the prompt text."

        parts = [f"""
      --- POLICY GUARDRAILS ---
      {hallucination_policy}
      2. OUTPUT SCOPE: Stick strictly to the objective: "{intent.content_scope}".
      3. MATH FORMATTING: All Big O, formulas, and technical metrics MUST be bolded: **O(N^2)**.
      4. HERO IMAGE: Provide a single, highly descriptive keyword (e.g. 'finance', 'technology', 'nature') representing the core topic of the report for the hero_image_keyword field.
      5. DIAGRAMS: Generate at least one Mermaid.js flowchart (e.g., flowchart TD) that visually summarizes a complex process, architecture, or relationship mentioned in the report. If historical, provide a timeline.
      6. SECTION IMAGES: For each additional_section, provide a highly specific 'image_keyword' (e.g. 'monument', 'architecture') so we can fetch a contextual image. If no image is needed, return 'none'.
>>>>>>> br1

      --- DOMAIN CONTEXT ---
      Identified Category: {intent.detected_category}

      --- OVERRIDE HIERARCHY ---
      - HIGHEST PRIORITY: Current User Objective: "{override}"
      - SECONDARY: Stored Style Laws: "{long_term}"
      Note: The Current User Objective ALWAYS overrides Stored Style Laws for this session.
    """]
        
        if file_base64:
            mime = 'application/pdf' if intent.document_metadata.file_type == 'pdf' else 'text/plain'
            parts.append(types.Part.from_bytes(data=file_base64, mime_type=mime))

        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=parts,
            config=types.GenerateContentConfig(
                system_instruction=f"""You are a Fact-Grounded Reporting Agent specialized in {intent.detected_category}. 
        MANDATORY: Output "Not Found" if evidence is missing. 
        Zero tolerance for hallucination or estimation. 
        Apply style laws exactly.""",
                response_mime_type="application/json",
                response_schema=self._get_report_schema()
            ),
        )

        return self._parse_response(response.text, intent.request_id, intent.input_mode)

    async def refine_report(
        self,
        previous_report: FinalReportJSON,
        suggestion: str,
        intent: NormalizedIntent,
        memory_context: str = ""
    ) -> FinalReportJSON:
        
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"""
        HARD CONSTRAINTS: {memory_context}
        NEW OVERRIDE: "{suggestion}"
        PREVIOUS DATA: {json.dumps(previous_report.report.dict())}
        
        CRITICAL: Apply the command while respecting existing grounding and bolding policies for the domain: {intent.detected_category}.
      """,
            config=types.GenerateContentConfig(
                system_instruction="Refinement Mode. Grounding must be preserved.",
                response_mime_type="application/json",
                response_schema=self._get_report_schema()
            ),
        )

        return self._parse_response(
            response.text, 
            previous_report.request_id, 
            InputMode.DOCUMENT_BASED if previous_report.source_type == 'document' else InputMode.TEXT_ONLY
        )

    async def extract_style_preferences(
        self,
        intent: NormalizedIntent,
        iterations: List[str],
        final_report: FinalReportJSON,
        current_memory: str
    ) -> Dict[str, str]:
        
        logger.log("Guardrail: Meta-Learning Feedback Integrity", "api")

        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"""
        DOMAIN: {intent.detected_category}
        EXISTING RULES: "{current_memory}"
        FEEDBACK HISTORY: [{' THEN '.join(iterations)}]
        SUCCESSFUL OUTPUT: {json.dumps(final_report.report.dict())[:1000]}
      """,
            config=types.GenerateContentConfig(
                system_instruction=f"""You are an Eager Preference Learner. 
        Extract ANY preference, correction, or stylistic choice from the feedback history for the specific domain: {intent.detected_category}.
        - ALWAYS incorporate the new feedback into the existing rules.
        - NEVER ignore user feedback. Assume all changes are permanent preferences for this user.""",
                response_mime_type="application/json",
                response_schema={
                    "type": "OBJECT",
                    "properties": {
                        "preference_rules": {"type": "STRING"},
                        "interaction_summary": {"type": "STRING"}
                    },
                    "required": ["preference_rules", "interaction_summary"]
                }
            ),
        )

        try:
            res = json.loads(response.text or "{}")
            return {
                "newMemory": res.get("preference_rules") or current_memory,
                "interactionSummary": res.get("interaction_summary") or "Session complete."
            }
        except:
            return {"newMemory": current_memory, "interactionSummary": "Session complete."}

    def _get_report_schema(self):
        return {
            "type": "OBJECT",
            "properties": {
                "report": {
                    "type": "OBJECT",
                    "properties": {
<<<<<<< HEAD
=======
                        "hero_image_keyword": {"type": "STRING"},
>>>>>>> br1
                        "executive_summary": {"type": "STRING"},
                        "highlights": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "risks_and_blockers": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "actions_required": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "evidence_links": {"type": "ARRAY", "items": {"type": "STRING"}},
<<<<<<< HEAD
=======
                        "diagrams": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {"title": {"type": "STRING"}, "mermaid_code": {"type": "STRING"}},
                                "required": ["title", "mermaid_code"]
                            }
                        },
>>>>>>> br1
                        "additional_sections": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
<<<<<<< HEAD
                                "properties": {"title": {"type": "STRING"}, "content": {"type": "STRING"}},
                                "required": ["title", "content"]
                            }
                        }
                    },
                    "required": ["executive_summary", "highlights", "risks_and_blockers", "actions_required", "evidence_links", "additional_sections"]
=======
                                "properties": {
                                    "title": {"type": "STRING"},
                                    "content": {"type": "STRING"},
                                    "image_keyword": {"type": "STRING"}
                                },
                                "required": ["title", "content", "image_keyword"]
                            }
                        }
                    },
                    "required": ["hero_image_keyword", "executive_summary", "highlights", "risks_and_blockers", "actions_required", "evidence_links", "diagrams", "additional_sections"]
>>>>>>> br1
                },
                "confidence_level": {"type": "STRING", "enum": ["high", "medium", "low"]}
            },
            "required": ["report", "confidence_level"]
        }

    def _parse_response(self, json_str: Optional[str], id: str, mode: InputMode) -> FinalReportJSON:
        from datetime import datetime
        try:
            raw_text = json_str or "{}"
            # Clean up potential markdown code blocks
            if raw_text.strip().startswith("```"):
                raw_text = raw_text.strip().split("\n", 1)[-1].rsplit("\n", 1)[0]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:].strip()
            
            raw = json.loads(raw_text)
            data = raw.get("report") or raw
            return FinalReportJSON(
                request_id=id,
                status='completed',
                report=ReportContent(
<<<<<<< HEAD
=======
                    hero_image_keyword=data.get("hero_image_keyword") or "abstract",
>>>>>>> br1
                    executive_summary=data.get("executive_summary") or "Not Found.",
                    highlights=data.get("highlights") if isinstance(data.get("highlights"), list) else [],
                    risks_and_blockers=data.get("risks_and_blockers") if isinstance(data.get("risks_and_blockers"), list) else [],
                    actions_required=data.get("actions_required") if isinstance(data.get("actions_required"), list) else [],
                    evidence_links=data.get("evidence_links") if isinstance(data.get("evidence_links"), list) else [],
<<<<<<< HEAD
=======
                    diagrams=[Diagram(**s) for s in (data.get("diagrams") or [])],
>>>>>>> br1
                    additional_sections=[CustomSection(**s) for s in (data.get("additional_sections") or [])]
                ),
                source_type='document' if mode == InputMode.DOCUMENT_BASED else 'text',
                confidence_level=raw.get("confidence_level") or 'medium',
                generated_at=datetime.now().isoformat()
            )
        except Exception as e:
            logger.log(f"Parse Error: {e}", "error", {"raw": raw_text})
            print(f"FAILED JSON: {raw_text}") # Force print to stdout for visibility
            raise Exception(f"Analysis parsing failed: {e}")
