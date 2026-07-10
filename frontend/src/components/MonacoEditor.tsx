import React, { useEffect, useRef } from 'react';
import Editor, { type Monaco } from '@monaco-editor/react';
import { registerCVLLanguage } from '../monaco/cvlLanguage';

interface MonacoEditorProps {
  value: string;
  onChange: (value: string) => void;
  mappings: Record<string, string> | null;
}

export const MonacoEditor: React.FC<MonacoEditorProps> = ({
  value,
  onChange,
  mappings,
}) => {
  const monacoRef = useRef<Monaco | null>(null);

  // Re-register dynamic cvl language tokenizers when mappings change
  useEffect(() => {
    if (monacoRef.current && mappings) {
      registerCVLLanguage(monacoRef.current, mappings);
    }
  }, [mappings]);

  const handleEditorDidMount = (_editor: any, monaco: Monaco) => {
    monacoRef.current = monaco;
    
    // Register immediately with current mappings if available
    if (mappings) {
      registerCVLLanguage(monaco, mappings);
    }

    // Define custom dark theme overrides for editor components
    monaco.editor.defineTheme('codeverse-dark', {
      base: 'vs-dark',
      inherit: true,
      rules: [
        { token: 'keyword', foreground: 'c084fc', fontStyle: 'bold' }, // Purple keywords
        { token: 'predefined', foreground: '38bdf8' },               // Cyan builtins
        { token: 'type', foreground: 'fb7185' },                     // Rose types
        { token: 'tag', foreground: '34d399', fontStyle: 'italic' },   // Emerald methods
        { token: 'comment', foreground: '6b7280' },                  // Muted grey comments
        { token: 'string', foreground: 'fde047' },                   // Yellow strings
        { token: 'number', foreground: 'f97316' },                   // Orange numbers
      ],
      colors: {
        'editor.background': '#0c0d12',
        'editor.foreground': '#f3f4f6',
        'editorLineNumber.foreground': '#4b5563',
        'editorLineNumber.activeForeground': '#c084fc',
        'editor.lineHighlightBackground': '#1e1b4b30',
        'editor.selectionBackground': '#9333ea40',
      }
    });

    monaco.editor.setTheme('codeverse-dark');
  };

  return (
    <div className="w-full h-full min-h-[400px]">
      <Editor
        height="100%"
        language="cvl"
        value={value}
        onChange={(val) => onChange(val || '')}
        onMount={handleEditorDidMount}
        loading={
          <div className="flex items-center justify-center h-full gap-2 text-secondary text-sm">
            <div className="spinner" />
            <span>Loading Monaco...</span>
          </div>
        }
        options={{
          fontSize: 14,
          fontFamily: "'JetBrains Mono', Consolas, monospace",
          minimap: { enabled: false },
          automaticLayout: true,
          scrollBeyondLastLine: false,
          cursorBlinking: 'smooth',
          cursorSmoothCaretAnimation: 'on',
          lineNumbersMinChars: 3,
          padding: { top: 12, bottom: 12 },
        }}
      />
    </div>
  );
};
