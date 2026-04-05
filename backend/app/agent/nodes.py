import google.generativeai as genai
import os
import json

def validate_context(state):
    return state

def fetch_data(state):
    return state

def extract(state):
    prompt_intent = state.get("user_prompt") or "Generate a placeholder report about system diagnostics."
    api_key = os.getenv("GEMINI_API_KEY", "")
    
    if not api_key or api_key == "your_gemini_api_key_here":
        # Safe fallback if user didn't configure their .env
        state["llm_output"] = '{"summary": {"total_actions": 0, "executive_summary": "Configure GEMINI_API_KEY in .env to enable AI"}, "approvals_needed": [], "risks": [{"issue": "Missing GEMINI_API_KEY", "severity": "Critical", "evidence": []}]}'
        return state

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        system_instruction = """
        You are an AI Reporting agent. Analyze the user prompt and output a STRICT raw JSON string (no markdown ticks like ```json) following this exact schema:
        {
           "summary": {"total_actions": <int>, "executive_summary": "<str>", "highlights": ["<str>"]},
           "approvals_needed": [{"item": "<str>", "urgency": "High/Low", "impact": "High/Low", "evidence": []}],
           "risks": [{"issue": "<str>", "severity": "High/Low", "evidence": []}]
        }
        """
        
        response = model.generate_content(f"{system_instruction}\n\nUser Request: {prompt_intent}")
        # Strip markdown if Gemini hallucinates formatting tags
        clean_text = response.text.replace('```json', '').replace('```', '').strip()
        state["llm_output"] = clean_text
    except Exception as e:
        state["llm_output"] = f'{{"summary": {{"total_actions": 0, "executive_summary": "LLM Inference failed"}}, "approvals_needed": [], "risks": [{{"issue": "API Error: {str(e)}", "severity": "High", "evidence": []}}]}}'
        
    return state

def summarize(state):
    return state

def structure(state):
    raw_response = state.get("llm_output", "{}")
    try:
        parsed = json.loads(raw_response)
        state["structured_data"] = parsed
    except json.JSONDecodeError:
        state["structured_data"] = {"error": "Failed to parse rigorous JSON structure", "raw": raw_response}
    return state
