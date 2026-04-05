import React, { useState } from 'react';
import { ApiService } from '../services/api';
import { FinalReportJSON, NormalizedIntent, TaskType, InputMode } from '../../types';

const api = new ApiService();

// Reusable spinner component for UI polish
const Spinner = () => (
  <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
  </svg>
);

const ReportingAgent = () => {
  const [prompt, setPrompt] = useState("");
  const [reportData, setReportData] = useState<FinalReportJSON | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setErrorMsg("");
    
    try {
        const intent: NormalizedIntent = {
            request_id: `req_${Date.now()}`,
            task_type: TaskType.REPORT,
            input_mode: InputMode.TEXT_ONLY,
            user_prompt: prompt,
            document_metadata: { attached: false, file_type: 'none', file_name: null },
            content_scope: 'General summary',
            constraints: { hallucination_allowed: false, output_structure_required: true },
            timestamp: new Date().toISOString()
        };

        const response = await api.generateReport(intent);
        setReportData(response.structuredJSON);
    } catch (err: any) {
        console.error(err);
        setErrorMsg(err.message || "Failed to contact backend API. Check if the server is running.");
    } finally {
        setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-50 shadow-2xl rounded-2xl overflow-hidden border border-slate-200 transition-all duration-300">
        <header className="bg-gradient-to-r from-blue-700 to-blue-500 p-5 text-white shadow-md z-10">
            <h1 className="text-2xl font-extrabold tracking-tight">AI Reporting Agent</h1>
        </header>
        
        <main className="flex-1 p-6 md:p-8 flex flex-col xl:flex-row gap-8 items-start h-[calc(100vh-90px)] overflow-hidden">
            
            {/* Input Form Column */}
            <form onSubmit={handleSubmit} className="w-full xl:w-1/3 bg-white p-6 rounded-xl border border-slate-200 shadow-md h-full flex flex-col transition-all hover:shadow-lg">
              <label htmlFor="prompt" className="block text-lg font-bold text-slate-800 mb-3 tracking-wide">
                Issue Request
              </label>
              <textarea 
                id="prompt" 
                rows={10}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                className="w-full rounded-lg border border-slate-300 shadow-sm focus:border-blue-500 focus:ring-4 focus:ring-blue-500/20 text-base p-4 flex-grow resize-none transition-all placeholder:text-slate-400"
                placeholder="Instruct the agent on what to analyze..."
              />
              <div className="mt-5 flex justify-end">
                <button 
                  type="submit" 
                  disabled={!prompt.trim() || isLoading}
                  className="bg-blue-600 text-white px-8 py-3 rounded-lg shadow-md hover:bg-blue-700 disabled:opacity-50 font-bold transition-all flex items-center justify-center transform active:scale-95"
                >
                  {isLoading && <Spinner />}
                  {isLoading ? 'Processing' : 'Generate'}
                </button>
              </div>
            </form>

            {/* Results Visualization Column */}
            <div className="w-full xl:w-2/3 h-full bg-white rounded-xl p-8 border border-slate-200 shadow-inner overflow-y-auto">
                {errorMsg ? (
                    <div className="bg-red-50 text-red-800 border-2 border-red-200 p-8 rounded-xl h-full flex flex-col justify-center items-center transform transition-all animate-pulse">
                        <span className="text-5xl mb-4">⚠️</span>
                        <h2 className="text-2xl font-bold mb-2">Connection Error</h2>
                        <p className="text-center font-medium">{errorMsg}</p>
                    </div>
                ) : reportData ? (
                    <div className="space-y-6 animate-fade-in-up">
                        <div className="flex items-center justify-between border-b pb-4">
                            <h2 className="text-3xl font-extrabold text-slate-800">Final Report</h2>
                            <span className="inline-block bg-blue-100 text-blue-800 text-xs px-4 py-1.5 rounded-full uppercase font-bold tracking-widest shadow-sm">
                                {reportData.confidence_level} Confidence
                            </span>
                        </div>
                        <div className="bg-slate-50 p-6 rounded-xl border border-slate-200 shadow-sm mt-4 hover:shadow-md transition-all">
                            <h3 className="font-bold text-slate-500 uppercase tracking-widest text-xs mb-3 flex items-center gap-2">
                                <span className="w-2 h-2 rounded-full bg-blue-500"></span> Executive Summary
                            </h3>
                            <p className="text-slate-700 leading-relaxed font-medium text-lg">{reportData.report.executive_summary}</p>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="bg-emerald-50/50 p-6 rounded-xl border border-emerald-100 shadow-sm hover:shadow-md transition-all">
                                <h3 className="font-bold text-slate-500 uppercase tracking-widest text-xs mb-3 flex items-center gap-2">
                                    <span className="w-2 h-2 rounded-full bg-emerald-500"></span> Highlights
                                </h3>
                                <ul className="list-disc pl-5 mt-1 text-sm text-slate-700 space-y-2 font-medium">
                                    {reportData.report.highlights.map((h, i) => <li key={i}>{h}</li>)}
                                </ul>
                            </div>
                            <div className="bg-rose-50/50 p-6 rounded-xl border border-rose-100 shadow-sm hover:shadow-md transition-all">
                                <h3 className="font-bold text-slate-500 uppercase tracking-widest text-xs mb-3 flex items-center gap-2">
                                    <span className="w-2 h-2 rounded-full bg-rose-500"></span> Risks & Blockers
                                </h3>
                                <ul className="list-disc pl-5 mt-1 text-sm text-slate-700 space-y-2 font-medium">
                                    {reportData.report.risks_and_blockers.map((r, i) => <li key={i}>{r}</li>)}
                                </ul>
                            </div>
                        </div>
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center h-full text-slate-400 opacity-60">
                        <svg className="w-24 h-24 mb-6 stroke-current stroke-1" fill="none" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m3.75 9v6m3-3H9m1.5-12H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"></path></svg>
                        <p className="font-medium text-xl tracking-wide">Awaiting Instructions...</p>
                    </div>
                )}
            </div>
        </main>
    </div>
  );
};

export default ReportingAgent;
