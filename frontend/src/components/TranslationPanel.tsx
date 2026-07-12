import React from 'react';
import Editor from '@monaco-editor/react';
import { Sparkles } from 'lucide-react';
import type { TranslationTraceLine } from '../lib/types';

interface TranslationPanelProps {
  generatedCode: string;
  language: 'python' | 'sql';
  isLoading: boolean;
  trace: TranslationTraceLine[];
}

export const TranslationPanel: React.FC<TranslationPanelProps> = ({
  generatedCode,
  language,
  isLoading,
  trace,
}) => {
  return (
    <div className="translation-panel glass-panel overflow-hidden flex flex-col">
      <div className="pane-header">
        <span className="pane-title">
          <Sparkles size={18} className="text-secondary" />
          Canonical translation ({language === 'python' ? 'Python' : 'PostgreSQL'})
        </span>
      </div>

      {trace.length > 0 && (
        <div className="translation-trace" aria-label="Personal Python translation trace">
          <div className="translation-trace-title"><span>Python bridge</span><small>{trace.length} translated lines</small></div>
          <div className="translation-trace-lines">
            {trace.map((line) => (
              <div className="translation-trace-line" key={`${line.line}-${line.personal_source}`}>
                <span>{line.line}</span>
                <code>{line.personal_source.trim()}</code>
                <strong>-&gt;</strong>
                <code>{line.python_source.trim()}</code>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex-1 min-h-0 relative">
        {isLoading ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/40 z-10">
            <div className="spinner" />
            <span className="text-secondary text-sm">Compiling...</span>
          </div>
        ) : !generatedCode ? (
          <div className="absolute inset-0 flex items-center justify-center bg-black/40 text-muted text-sm italic">
            Compiled code will appear here.
          </div>
        ) : null}

        <div className="w-full h-full">
          <Editor
            height="100%"
            language={language}
            value={generatedCode}
            options={{
              readOnly: true,
              fontSize: 13,
              fontFamily: "'JetBrains Mono', Consolas, monospace",
              minimap: { enabled: false },
              automaticLayout: true,
              lineNumbers: 'on',
              folding: true,
              scrollBeyondLastLine: false,
              wordWrap: 'on',
              domReadOnly: true,
              theme: 'vs-dark',
              padding: { top: 12, bottom: 12 },
            }}
          />
        </div>
      </div>
    </div>
  );
};
