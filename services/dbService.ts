
import { createClient, SupabaseClient } from "@supabase/supabase-js";
import { NormalizedIntent, FinalReportJSON } from "../types";
import { logger } from "./logger";

export class DatabaseService {
  private supabase: SupabaseClient | null = null;
  private cache = new Map<string, FinalReportJSON>();

  constructor() {
    const url = "https://koznbqrznjrtfebbqzph.supabase.co";
    const key = "sb_publishable_4ckWXA5XdQO894Kaa4nReg_qdvBlEHh";
    try {
      this.supabase = createClient(url, key);
      logger.log("Supabase Client initialized", "db");
    } catch (e) {
      logger.log("Supabase connectivity error", "error", e);
    }
  }

  /**
   * GUARDRAIL: Duplicate Detection Caching
   */
  getRequestHash(prompt: string, fileName: string | null, size: number): string {
    const raw = `${prompt}:${fileName || 'none'}:${size}`;
    let hash = 0;
    for (let i = 0; i < raw.length; i++) {
      hash = (hash << 5) - hash + raw.charCodeAt(i);
      hash |= 0; 
    }
    return `h_${hash}`;
  }

  getCachedReport(hash: string): FinalReportJSON | null {
    return this.cache.get(hash) || null;
  }

  setCachedReport(hash: string, report: FinalReportJSON): void {
    this.cache.set(hash, report);
  }

  async storeInitialIntent(intent: NormalizedIntent): Promise<void> {
    if (!this.supabase) return;
    logger.log(`Logging initial intent: ${intent.request_id}`, "db");
    try {
      await this.supabase.from('agent_requests').insert([{
        request_id: intent.request_id,
        task_type: intent.task_type,
        input_mode: intent.input_mode,
        user_prompt: intent.user_prompt,
        detected_category: intent.detected_category,
        document_metadata: intent.document_metadata
      }]);
    } catch (e) {
      logger.log("Failed to log request intent to DB", "warn", e);
    }
  }

  async getPreferences(category: string): Promise<string> {
    logger.log(`Fetching rules for domain: ${category}`, "db");
    if (!this.supabase) {
      const local = localStorage.getItem(`pref_${category}`);
      return local || "Apply standard professional reporting standards.";
    }
    
    try {
      const { data, error } = await this.supabase
        .from('agent_preferences')
        .select('preference_rules')
        .eq('category', category)
        .single();
      
      if (!error && data) {
        logger.log("Domain-specific rules found", "success");
        return data.preference_rules;
      }

      logger.log("Domain rules not found, falling back to general", "info");
      const { data: general } = await this.supabase
        .from('agent_preferences')
        .select('preference_rules')
        .eq('category', 'general')
        .single();
      
      return general?.preference_rules || "Apply standard professional reporting standards.";
    } catch (e) {
      return "Apply standard professional reporting standards.";
    }
  }

  async updatePreference(category: string, rules: string): Promise<void> {
    logger.log(`Updating memory for category: ${category}`, "db");
    if (!this.supabase) {
      localStorage.setItem(`pref_${category}`, rules);
      return;
    }

    try {
      const { data: existing } = await this.supabase
        .from('agent_preferences')
        .select('interaction_count, confidence_weight')
        .eq('category', category)
        .single();

      if (existing) {
        await this.supabase
          .from('agent_preferences')
          .update({ 
            preference_rules: rules, 
            interaction_count: (existing.interaction_count || 0) + 1,
            confidence_weight: Math.min((existing.confidence_weight || 1.0) + 0.1, 5.0),
            last_updated: new Date().toISOString()
          })
          .eq('category', category);
      } else {
        await this.supabase
          .from('agent_preferences')
          .insert([{ 
            category, 
            preference_rules: rules, 
            confidence_weight: 1.0, 
            interaction_count: 1 
          }]);
      }
      logger.log("Long-term memory updated in database", "success");
    } catch (e) {
      logger.log("Preference memory update failed", "error", e);
    }
  }

  async storeInteractionSummary(requestId: string, category: string, summary: string, score: number): Promise<void> {
    if (!this.supabase) return;
    logger.log(`Persisting interaction audit log for ${requestId}`, "db");
    try {
      await this.supabase.from('agent_interactions').insert([{
        request_id: requestId,
        category,
        interaction_summary: summary,
        feedback_score: score
      }]);
    } catch (e) {
      logger.log("Outcome summary logging failed", "warn", e);
    }
  }
}
