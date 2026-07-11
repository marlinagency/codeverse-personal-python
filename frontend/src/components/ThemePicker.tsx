import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { ArrowLeft, ArrowUp, Plus, Palette, AlertTriangle, X } from 'lucide-react';
import { BASE_URL } from '../lib/api';

interface ThemeMapping {
  id: string;
  theme_name: string;
  mappings: Record<string, string>;
  rationale?: Record<string, string>;
  llm_provider: string;
  llm_model: string;
  version: number;
}

interface ClarifyingOption {
  label: string;
  icon: string;
}

interface ClarifyingQuestion {
  id: string;
  question: string;
  options: ClarifyingOption[];
}

interface ThemePickerProps {
  themes: ThemeMapping[];
  selectedTheme: ThemeMapping | null;
  onSelectTheme: (theme: ThemeMapping) => void;
  token: string;
  onRefreshThemes: () => Promise<void>;
  mode?: 'bar' | 'hero';
}

//: a hung request is the realistic failure mode for an LLM call, not just a
//: rejection — the wizard must degrade the same way for both.
const QUESTIONS_TIMEOUT_MS = 20000;

type WizardStage = 'idle' | 'loading-questions' | 'wizard';

export const ThemePicker: React.FC<ThemePickerProps> = ({
  themes,
  selectedTheme,
  onSelectTheme,
  token,
  onRefreshThemes,
  mode = 'bar',
}) => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newThemePrompt, setNewThemePrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [validationProblems, setValidationProblems] = useState<string[]>([]);

  const [stage, setStage] = useState<WizardStage>('idle');
  const [questions, setQuestions] = useState<ClarifyingQuestion[]>([]);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [progressPct, setProgressPct] = useState(0);
  const [loadingQuestionsSuccess, setLoadingQuestionsSuccess] = useState(false);
  const [generationSuccess, setGenerationSuccess] = useState(false);

  useEffect(() => {
    let intervalId: any = null;

    if (generationSuccess || loadingQuestionsSuccess) {
      setProgressPct(100);
    } else if (stage === 'loading-questions') {
      setProgressPct(10);
      intervalId = setInterval(() => {
        setProgressPct((prev) => {
          if (prev < 90) {
            return prev + 2;
          }
          return prev;
        });
      }, 100);
    } else if (isGenerating) {
      setProgressPct((prev) => Math.max(prev, 10));
      intervalId = setInterval(() => {
        setProgressPct((prev) => {
          if (prev < 95) {
            return prev + 1;
          }
          return prev;
        });
      }, 150);
    } else {
      setProgressPct(0);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [stage, isGenerating, loadingQuestionsSuccess, generationSuccess]);

  const resetWizardState = () => {
    setStage('idle');
    setQuestions([]);
    setQuestionIndex(0);
    setAnswers({});
    setSelectedOption(null);
  };

  const runGenerate = async (theme: string, clarifyingAnswers: Record<string, string>) => {
    setIsGenerating(true);
    setErrorMsg(null);
    setValidationProblems([]);

    try {
      const response = await fetch(`${BASE_URL}/themes/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          theme,
          output_language: 'en',
          clarifying_answers: Object.keys(clarifyingAnswers).length ? clarifyingAnswers : null,
        }),
      });

      const raw = await response.text();
      const data = raw ? JSON.parse(raw) : {};

      if (!response.ok) {
        if (response.status === 422 || response.status === 502) {
          setValidationProblems(data.detail?.problems || ['Theme rules could not be validated.']);
        } else {
          throw new Error(data.detail || 'Something went wrong while generating the theme.');
        }
        return;
      }

      setGenerationSuccess(true);
      setProgressPct(100);
      setTimeout(async () => {
        try {
          await onRefreshThemes();
          onSelectTheme(data);
          setIsModalOpen(false);
          setNewThemePrompt('');
          resetWizardState();
        } finally {
          setGenerationSuccess(false);
        }
      }, 800);
    } catch (err: any) {
      setErrorMsg(err.message || 'Server connection error.');
    } finally {
      setIsGenerating(false);
    }
  };

  const startWizard = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newThemePrompt.trim()) return;

    setErrorMsg(null);
    setValidationProblems([]);
    setStage('loading-questions');

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), QUESTIONS_TIMEOUT_MS);

    try {
      const response = await fetch(`${BASE_URL}/themes/questions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ theme: newThemePrompt }),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!response.ok) throw new Error('clarifying questions request failed');
      const data = await response.json();
      if (!Array.isArray(data.questions) || data.questions.length === 0) {
        throw new Error('no clarifying questions returned');
      }

      setLoadingQuestionsSuccess(true);
      setProgressPct(100);
      setTimeout(() => {
        setQuestions(data.questions);
        setQuestionIndex(0);
        setAnswers({});
        setSelectedOption(null);
        setStage('wizard');
        setLoadingQuestionsSuccess(false);
      }, 800);
    } catch {
      clearTimeout(timeoutId);
      // Graceful degradation: the user must never be blocked by this step —
      // skip the wizard and generate directly from the raw theme, same as
      // before this feature existed.
      setStage('idle');
      await runGenerate(newThemePrompt, {});
    }
  };

  const goToQuestion = (index: number, currentAnswers: Record<string, string>) => {
    setQuestionIndex(index);
    setSelectedOption(currentAnswers[questions[index].question] ?? null);
  };

  const handleBack = () => {
    if (questionIndex === 0) return;
    goToQuestion(questionIndex - 1, answers);
  };

  const advance = (nextAnswers: Record<string, string>) => {
    if (questionIndex + 1 < questions.length) {
      goToQuestion(questionIndex + 1, nextAnswers);
    } else {
      resetWizardState();
      runGenerate(newThemePrompt, nextAnswers);
    }
  };

  const handleContinue = () => {
    const current = questions[questionIndex];
    const nextAnswers = selectedOption
      ? { ...answers, [current.question]: selectedOption }
      : answers;
    setAnswers(nextAnswers);
    advance(nextAnswers);
  };

  const handleSkipQuestion = () => {
    advance(answers);
  };

  const renderWizard = () => {
    if (stage === 'idle' && !isGenerating && !generationSuccess && !loadingQuestionsSuccess) return null;

    const isLoadingQuestions = stage === 'loading-questions';

    if (isLoadingQuestions || isGenerating || loadingQuestionsSuccess || generationSuccess) {
      let step1Status: 'complete' | 'active' | 'upcoming' = 'complete';
      let step2Status: 'complete' | 'active' | 'upcoming' = 'upcoming';
      let step3Status: 'complete' | 'active' | 'upcoming' = 'upcoming';

      if (generationSuccess) {
        step2Status = 'complete';
        step3Status = 'complete';
      } else if (loadingQuestionsSuccess) {
        step2Status = 'complete';
      } else if (isLoadingQuestions) {
        step2Status = 'active';
      } else if (isGenerating) {
        step2Status = 'complete';
        step3Status = 'active';
      }

      const renderStepIcon = (status: 'complete' | 'active' | 'upcoming') => {
        if (status === 'complete') {
          return (
            <div className="cv-icon-check-wrapper">
              <svg className="cv-icon-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>
          );
        }
        if (status === 'active') {
          return <div className="cv-icon-active" />;
        }
        return <div className="cv-icon-upcoming" />;
      };

      return createPortal(
        <div className="modal-overlay">
          <div className="cv-loading-modal">
            <span className="cv-loading-title">BUILDING YOUR CODEVERSE</span>
            
            <div className="cv-loading-illustration">
              <div className="juggling-dino-loading" />
            </div>

            <p className="cv-loading-subtitle">
              We're turning your world into a personalized Python learning experience.
            </p>

            <div className="cv-loading-steps">
              <div className={`cv-loading-step ${step1Status}`}>
                <span className="cv-step-icon">{renderStepIcon(step1Status)}</span>
                <span className="cv-step-text">Understanding your theme</span>
              </div>
              <div className={`cv-loading-step ${step2Status}`}>
                <span className="cv-step-icon">{renderStepIcon(step2Status)}</span>
                <span className="cv-step-text">
                  {step2Status === 'active' ? 'Designing your questions...' : 'Designing your questions'}
                </span>
              </div>
              <div className={`cv-loading-step ${step3Status}`}>
                <span className="cv-step-icon">{renderStepIcon(step3Status)}</span>
                <span className="cv-step-text">
                  {step3Status === 'active' ? 'Preparing your syntax map...' : 'Preparing your syntax map'}
                </span>
              </div>
            </div>

            <div className="cv-loading-progress-track">
              <div className="cv-loading-progress-fill" style={{ width: `${progressPct}%` }} />
            </div>

            <span className="cv-loading-footer">Usually takes less than 20 seconds</span>
          </div>
        </div>,
        document.body
      );
    }

    const current = questions[questionIndex];
    const wizardProgressPct = ((questionIndex + (selectedOption ? 1 : 0.5)) / questions.length) * 100;

    return createPortal(
      <div className="modal-overlay">
        <div className="wizard-content glass-panel">
          <div className="wizard-progress-track">
            <div className="wizard-progress-fill" style={{ width: `${wizardProgressPct}%` }} />
          </div>

          <div className="wizard-header">
            <button
              type="button"
              onClick={handleBack}
              disabled={questionIndex === 0}
              className="wizard-back-btn"
              title="Previous question"
            >
              <ArrowLeft size={18} />
            </button>
            <span className="wizard-step-label">
              Question {questionIndex + 1} of {questions.length}
            </span>
          </div>

          <p className="wizard-question">{current.question}</p>

          <div className="wizard-options-grid">
            {current.options.map((opt) => (
              <button
                type="button"
                key={opt.label}
                className={`wizard-option-card${selectedOption === opt.label ? ' selected' : ''}`}
                onClick={() => setSelectedOption(opt.label)}
              >
                <span className="wizard-option-icon">{opt.icon}</span>
                <span className="wizard-option-label">{opt.label}</span>
              </button>
            ))}
          </div>

          <div className="wizard-footer">
            <button type="button" onClick={handleSkipQuestion} className="wizard-skip-link">
              Skip this question
            </button>
            <button
              type="button"
              onClick={handleContinue}
              disabled={!selectedOption}
              className="btn-primary"
            >
              {questionIndex + 1 === questions.length ? 'Finish' : 'Continue'}
            </button>
          </div>
        </div>
      </div>,
      document.body
    );
  };

  if (mode === 'hero') {
    return (
      <div className="hero-composer">
        <form onSubmit={startWizard} className="prompt-composer">
          <textarea
            placeholder="describe your world..."
            value={newThemePrompt}
            onChange={(e) => setNewThemePrompt(e.target.value)}
            disabled={isGenerating || stage !== 'idle'}
            required
            rows={4}
          />
          <div className="prompt-actions">
            <select
              value={selectedTheme?.id || ''}
              onChange={(e) => {
                const selected = themes.find((t) => t.id === e.target.value);
                if (selected) onSelectTheme(selected);
              }}
            >
              <option value="">Recent themes</option>
              {themes.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.theme_name}
                </option>
              ))}
            </select>
            <button
              type="submit"
              className="composer-send"
              disabled={isGenerating || stage !== 'idle' || !newThemePrompt.trim()}
              title="Create Personal Python"
            >
              {isGenerating ? <div className="spinner" /> : <ArrowUp size={18} />}
            </button>
          </div>
        </form>

        {isGenerating && (
          <span className="hero-status">Designing concept-aware Python tokens...</span>
        )}

        {errorMsg && <div className="hero-error">{errorMsg}</div>}

        {validationProblems.length > 0 && (
          <div className="hero-error">
            {validationProblems.slice(0, 2).join(' ')}
          </div>
        )}

        {renderWizard()}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-2 text-sm text-secondary">
        <Palette size={16} className="text-primary" />
        <span>Personal Python:</span>
      </div>

      <select
        value={selectedTheme?.id || ''}
        onChange={(e) => {
          const selected = themes.find((t) => t.id === e.target.value);
          if (selected) onSelectTheme(selected);
        }}
        className="min-w-[180px]"
      >
        <option value="" disabled>-- Select a theme --</option>
        {themes.map((t) => (
          <option key={t.id} value={t.id}>
            {t.theme_name}
          </option>
        ))}
      </select>

      <button
        onClick={() => setIsModalOpen(true)}
        className="btn-secondary"
        title="Create Personal Python"
      >
        <Plus size={16} />
        <span>Create</span>
      </button>

      {/* Modal overlays */}
      {isModalOpen && createPortal(
        <div className="modal-overlay">
          <div className="modal-content glass-panel">
            <div className="flex justify-between items-center border-b border-muted pb-3 mb-2">
              <h3 className="modal-title">Create Personal Python</h3>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="text-secondary hover:text-primary transition-colors bg-transparent border-0 p-1 flex items-center justify-center cursor-pointer"
                disabled={isGenerating}
                style={{ outline: 'none' }}
              >
                <X size={20} />
              </button>
            </div>

            <p className="text-secondary text-sm">
              Describe yourself, what you like, and which Python ideas feel confusing. The AI will extract a clean theme, concrete motifs, and short English tokens for Python only.
            </p>

            <form onSubmit={startWizard} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium">Personal prompt:</label>
                <input
                  type="text"
                  placeholder="I love Counter-Strike 2 and loops/functions confuse me..."
                  value={newThemePrompt}
                  onChange={(e) => setNewThemePrompt(e.target.value)}
                  disabled={isGenerating || stage !== 'idle'}
                  required
                />
              </div>

              {isGenerating && (
                <div className="flex items-center gap-2 text-primary text-sm font-medium">
                  <div className="spinner" />
                  <span>AI is designing your personal Python layer...</span>
                </div>
              )}

              {errorMsg && (
                <div className="text-error text-sm bg-error-bg p-3 border border-red-500/20 rounded-md">
                  {errorMsg}
                </div>
              )}

              {validationProblems.length > 0 && (
                <div className="flex flex-col gap-2 bg-error-bg p-3 border border-red-500/20 rounded-md">
                  <div className="flex items-center gap-2 text-error text-sm font-semibold">
                    <AlertTriangle size={16} />
                    <span>The generated dictionary could not be validated:</span>
                  </div>
                  <ul className="problems-list">
                    {validationProblems.map((problem, i) => (
                      <li key={i}>{problem}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="modal-buttons">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="btn-secondary"
                  disabled={isGenerating}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={isGenerating || stage !== 'idle' || !newThemePrompt.trim()}
                >
                  Generate
                </button>
              </div>
            </form>
          </div>
        </div>,
        document.body
      )}

      {renderWizard()}
    </div>
  );
};
