import React from 'react';
import Editor from '@monaco-editor/react';
import { Sparkles } from 'lucide-react';

interface TranslationPanelProps {
  generatedCode: string;
  language: 'python' | 'sql';
  isLoading: boolean;
}

export const TranslationPanel: React.FC<TranslationPanelProps> = ({
  generatedCode,
  language,
  isLoading,
}) => {
  return (
    <div className="translation-panel glass-panel overflow-hidden flex flex-col">
      <div className="pane-header">
        <span className="pane-title">
          <Sparkles size={18} className="text-secondary" />
          Canonical translation ({language === 'python' ? 'Python' : 'PostgreSQL'})
        </span>
      </div>

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
