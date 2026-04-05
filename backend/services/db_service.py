import os
from typing import Optional, Dict
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

from schemas import NormalizedIntent, FinalReportJSON
from .logger import logger

from pathlib import Path

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

class DatabaseService:
    def __init__(self):
        self.supabase: Optional[Client] = None
        self.cache: Dict[str, FinalReportJSON] = {}
        
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        
        if url and key:
            try:
                self.supabase = create_client(url, key)
                logger.log("Supabase Client initialized", "db")
            except Exception as e:
                logger.log("Supabase connectivity error", "error", e)
        else:
             logger.log("Supabase credentials missing in .env", "warn")

    def get_request_hash(self, prompt: str, file_name: Optional[str], size: Optional[int]) -> str:
        raw = f"{prompt}:{file_name or 'none'}:{size or 0}"
        hash_val = 0
        for char in raw:
            hash_val = ((hash_val << 5) - hash_val) + ord(char)
            hash_val |= 0  # 32bit integer
        return f"h_{hash_val}"

    def get_cached_report(self, hash_val: str) -> Optional[FinalReportJSON]:
        return self.cache.get(hash_val)

    def set_cached_report(self, hash_val: str, report: FinalReportJSON) -> None:
        self.cache[hash_val] = report

    async def store_initial_intent(self, intent: NormalizedIntent) -> None:
        if not self.supabase:
            return
        logger.log(f"Logging initial intent: {intent.request_id}", "db")
        try:
            self.supabase.table('agent_requests').insert({
                "request_id": intent.request_id,
                "task_type": intent.task_type.value,
                "input_mode": intent.input_mode.value,
                "user_prompt": intent.user_prompt,
                "detected_category": intent.detected_category,
                "document_metadata": intent.document_metadata.model_dump(mode='json') if hasattr(intent.document_metadata, 'model_dump') else intent.document_metadata.dict()
            }).execute()
        except Exception as e:
            logger.log("Failed to log request intent to DB", "warn", str(e))

    async def get_preferences(self, category: str) -> str:
        logger.log(f"Fetching rules for domain: {category}", "db")
        default_rule = "Apply standard professional reporting standards."
        
        if not self.supabase:
            return default_rule
        
        try:
            response = self.supabase.table('agent_preferences').select('preference_rules').eq('category', category).execute()
            data = response.data
            
            if data and len(data) > 0:
                logger.log("Domain-specific rules found", "success")
                return data[0]['preference_rules']

            logger.log("Domain rules not found, falling back to general", "info")
            response_gen = self.supabase.table('agent_preferences').select('preference_rules').eq('category', 'general').execute()
            general = response_gen.data
            
            return general[0]['preference_rules'] if general and len(general) > 0 else default_rule
        except Exception as e:
            logger.log(f"Error fetching rules: {e}", "warn")
            return default_rule

    async def update_preference(self, category: str, rules: str) -> None:
        logger.log(f"Updating memory for category: {category}", "db")
        if not self.supabase:
            return

        try:
            existing_response = self.supabase.table('agent_preferences').select('interaction_count, confidence_weight').eq('category', category).execute()
            existing = existing_response.data

            if existing and len(existing) > 0:
                row = existing[0]
                self.supabase.table('agent_preferences').update({
                    "preference_rules": rules,
                    "interaction_count": (row.get('interaction_count') or 0) + 1,
                    "confidence_weight": min((row.get('confidence_weight') or 1.0) + 0.1, 5.0),
                    "last_updated": datetime.now().isoformat()
                }).eq('category', category).execute()
            else:
                self.supabase.table('agent_preferences').insert({
                    "category": category,
                    "preference_rules": rules,
                    "confidence_weight": 1.0,
                    "interaction_count": 1
                }).execute()
            logger.log("Long-term memory updated in database", "success")
        except Exception as e:
            logger.log("Preference memory update failed", "error", str(e))

    async def store_interaction_summary(self, request_id: str, category: str, summary: str, score: float) -> None:
        if not self.supabase:
            return
        logger.log(f"Persisting interaction audit log for {request_id}", "db")
        try:
            self.supabase.table('agent_interactions').insert({
                "request_id": request_id,
                "category": category,
                "interaction_summary": summary,
                "feedback_score": int(round(score))
            }).execute()
        except Exception as e:
            logger.log("Outcome summary logging failed", "warn", str(e))
