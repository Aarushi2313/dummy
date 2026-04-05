
import { LogEntry, LogType } from "../types";

type LogListener = (entry: LogEntry) => void;

class Logger {
  private listeners: LogListener[] = [];

  log(message: string, type: LogType = 'info', payload?: any) {
    const entry: LogEntry = {
      id: `log_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      timestamp: new Date().toLocaleTimeString(),
      type,
      message,
      payload
    };
    
    // Also log to browser console for dev convenience
    const style = this.getConsoleStyle(type);
    console.log(`%c[${entry.timestamp}] [${type.toUpperCase()}] ${message}`, style, payload || '');

    if (import.meta.env.DEV) {
      try {
        fetch('/__log-to-terminal', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(entry)
        }).catch(() => { });
      } catch (e) {
        // Ignore errors sending logs
      }
    }
    // Broadcast to UI listeners (Terminal component)
    this.listeners.forEach(l => l(entry));
  }

  subscribe(listener: LogListener) {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter(l => l !== listener);
    };
  }

  private getConsoleStyle(type: LogType): string {
    switch (type) {
      case 'api': return 'color: #818cf8; font-weight: bold;';
      case 'success': return 'color: #10b981; font-weight: bold;';
      case 'error': return 'color: #ef4444; font-weight: bold;';
      case 'warn': return 'color: #f59e0b; font-weight: bold;';
      case 'db': return 'color: #ec4899; font-weight: bold;';
      default: return 'color: #64748b;';
    }
  }
}

export const logger = new Logger();
