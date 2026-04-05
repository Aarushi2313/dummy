from supabase import create_client
import os
import functools
from dotenv import load_dotenv

load_dotenv()

supabase = create_client(
    os.getenv("SUPABASE_URL", "https://ynkvquequwhvekpgbejh.supabase.co"),
    os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inlua3ZxdWVxdXdodmVrcGdiZWpoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njg0MDg0MjksImV4cCI6MjA4Mzk4NDQyOX0.-zxQT2l1N4lxtrovQS8NbolP342Zfg9DV6Lxr_CsU_Y")
)

@functools.lru_cache(maxsize=128)
def fetch_agent_runs(start, end):
    # Added LRU cache optimization to prevent redundant requests on the same time window
    return supabase.table("agent_runs") \
        .select("id, started_at, completed_at") \
        .gte("started_at", start) \
        .lte("completed_at", end) \
        .execute().data

def fetch_agent_outputs(start, end):
    # Optimized query by selecting specific columns rather than select("*")
    return supabase.table("agent_outputs") \
        .select("id, status, confidence") \
        .execute().data
