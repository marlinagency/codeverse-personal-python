import React from 'react';
import { Play, Code } from 'lucide-react';

interface RunButtonProps {
  onCompile: () => void;
  onExecute: () => void;
  isCompiling: boolean;
  isRunning: boolean;
  disabled: boolean;
}

export const RunButton: React.FC<RunButtonProps> = ({
  onCompile,
  onExecute,
  isCompiling,
  isRunning,
  disabled,
}) => {
  return (
    <div className="flex items-center gap-2">
      <button
        onClick={onCompile}
        disabled={disabled || isCompiling || isRunning}
        className="btn-secondary py-[10px]"
        title="Compile to Python only (Ctrl+B)"
      >
        {isCompiling ? (
          <div className="spinner !border-t-primary" />
        ) : (
          <Code size={16} className="text-secondary" />
        )}
        <span>Compile</span>
      </button>

      <button
        onClick={onExecute}
        disabled={disabled || isCompiling || isRunning}
        className="btn-primary"
        title="Compile and run in the sandbox (Ctrl+Enter)"
      >
        {isRunning ? (
          <div className="spinner" />
        ) : (
          <Play size={16} fill="currentColor" />
        )}
        <span>Run</span>
      </button>
    </div>
  );
};
