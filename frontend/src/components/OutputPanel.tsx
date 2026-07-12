import React from 'react';
import { Terminal, Clock, CheckCircle2, XCircle, AlertCircle } from 'lucide-react';

interface Diagnostic {
  message: string;
  themed_message?: string;
  line?: number;
  col?: number;
  severity?: string;
  stage?: string;
  personal_source?: string | null;
  python_source?: string | null;
  personal_token?: string | null;
  python_token?: string | null;
}

interface ExecutionResult {
  status: string; // 'success' | 'runtime_error' | 'parse_error' | 'codegen_error' | 'timeout' | 'sandbox_error' | 'running'
  stdout?: string | null;
  stderr_raw?: string | null;
  error_message_themed?: string | null;
  duration_ms?: number;
  diagnostic_error?: Diagnostic | null; // From compilation phase
}

interface OutputPanelProps {
  result: ExecutionResult | null;
  isLoading: boolean;
}

export const OutputPanel: React.FC<OutputPanelProps> = ({ result, isLoading }) => {
  if (isLoading) {
    return (
      <div className="output-panel glass-panel overflow-hidden flex flex-col">
        <div className="pane-header">
          <span className="pane-title">
            <Terminal size={18} className="text-secondary" />
            Terminal Output
          </span>
        </div>
        <div className="flex-1 flex flex-col items-center justify-center gap-2 bg-black/40">
          <div className="spinner" />
          <span className="text-secondary text-sm">Running program (Docker sandbox)...</span>
        </div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="output-panel glass-panel overflow-hidden flex flex-col">
        <div className="pane-header">
          <span className="pane-title">
            <Terminal size={18} className="text-secondary" />
            Terminal Output
          </span>
        </div>
        <div className="flex-1 flex items-center justify-center bg-black/40 text-muted text-sm italic">
          Press "Run" to compile and execute your code.
        </div>
      </div>
    );
  }

  const getStatusBadge = () => {
    switch (result.status) {
      case 'success':
        return (
          <span className="success-badge flex items-center gap-1">
            <CheckCircle2 size={14} />
            SUCCESS
          </span>
        );
      case 'parse_error':
        return (
          <span className="error-badge flex items-center gap-1">
            <XCircle size={14} />
            SYNTAX ERROR
          </span>
        );
      case 'codegen_error':
        return (
          <span className="error-badge flex items-center gap-1">
            <XCircle size={14} />
            CODEGEN ERROR
          </span>
        );
      case 'runtime_error':
        return (
          <span className="error-badge flex items-center gap-1">
            <XCircle size={14} />
            RUNTIME ERROR
          </span>
        );
      case 'timeout':
        return (
          <span className="error-badge flex items-center gap-1">
            <Clock size={14} />
            TIMEOUT
          </span>
        );
      case 'sandbox_error':
        return (
          <span className="error-badge flex items-center gap-1">
            <AlertCircle size={14} />
            SANDBOX ERROR
          </span>
        );
      default:
        return (
          <span className="error-badge flex items-center gap-1">
            <AlertCircle size={14} />
            ERROR
          </span>
        );
    }
  };

  // Extract themed and unthemed error messages if any
  const themedError = result.error_message_themed || result.diagnostic_error?.themed_message;
  const rawError = result.stderr_raw || result.diagnostic_error?.message;
  const line = result.diagnostic_error?.line;
  const col = result.diagnostic_error?.col;

  return (
    <div className="output-panel glass-panel overflow-hidden flex flex-col">
      <div className="pane-header">
        <span className="pane-title">
          <Terminal size={18} className="text-secondary" />
          Terminal Output
        </span>
        <div className="flex items-center gap-3">
          {result.duration_ms !== undefined && (
            <div className="flex items-center gap-1 text-xs text-secondary">
              <Clock size={12} />
              <span>{result.duration_ms} ms</span>
            </div>
          )}
          {getStatusBadge()}
        </div>
      </div>

      <div className="flex-1 flex flex-col min-height-0">
        {/* Themed Error Box - CodeVerse specialty */}
        {themedError && (
          <div className="m-4 p-4 rounded-lg bg-red-500/10 border border-red-500/30 flex flex-col gap-2">
            <div className="text-sm font-semibold text-red-300 uppercase tracking-wider flex items-center gap-2">
              <AlertCircle size={16} className="text-red-400" />
              <span>Themed error message:</span>
            </div>
            <div className="text-base text-red-200 font-medium">
              "{themedError}"
            </div>
            {line !== undefined && (
              <div className="text-xs text-red-400 font-mono">
                Line {line}, Column {col}
              </div>
            )}
            {result.diagnostic_error?.personal_source && (
              <div className="diagnostic-bridge">
                <div><small>Your line</small><code>{result.diagnostic_error.personal_source}</code></div>
                <span>-&gt;</span>
                <div><small>Python sees</small><code>{result.diagnostic_error.python_source}</code></div>
              </div>
            )}
            {result.diagnostic_error?.personal_token && result.diagnostic_error.python_token && (
              <div className="diagnostic-token-map">
                <code>{result.diagnostic_error.personal_token}</code>
                <span>-&gt;</span>
                <code>{result.diagnostic_error.python_token}</code>
              </div>
            )}
          </div>
        )}

        {/* Console logs */}
        <div className="output-console flex-1">
          {result.stdout && (
            <pre className="text-emerald-400 m-0 whitespace-pre-wrap">{result.stdout}</pre>
          )}
          {rawError && (
            <pre className="text-red-400 m-0 whitespace-pre-wrap mt-2">
              {rawError}
            </pre>
          )}
          {!result.stdout && !rawError && (
            <div className="text-muted italic text-sm">
              [System: Code ran successfully but produced no output.]
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
