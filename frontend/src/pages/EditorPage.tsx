import React, { useEffect, useRef, useState } from 'react';
import { Sparkles } from 'lucide-react';
import { ThemePicker } from '../components/ThemePicker';
import { MonacoEditor } from '../components/MonacoEditor';
import { OutputPanel } from '../components/OutputPanel';
import { TranslationPanel } from '../components/TranslationPanel';
import { RunButton } from '../components/RunButton';
import { AnimatedLandingDemo, EducationPages, type EducationView } from '../components/EducationPages';
import rocketImage from '../assets/codeverse-rocket.png';
import { BASE_URL } from '../lib/api';
import type { TranslationTraceLine } from '../lib/types';

interface ThemeMapping {
  id: string;
  theme_name: string;
  mappings: Record<string, string>;
  rationale?: Record<string, string>;
  llm_provider: string;
  llm_model: string;
  version: number;
}

interface LearningConcept {
  concept_id: string;
  python_concept: string;
  personal_token: string;
  title: string;
  mental_model: string;
  real_python: string;
}

interface PracticeTask {
  id: string;
  kind: string;
  concept_id: string;
  prompt: string;
  choices: string[];
  starter_source: string | null;
  hint: string;
  explanation: string;
}

interface CodeRunResult {
  correct: boolean;
  status: string;
  stdout: string | null;
  stderr: string | null;
  expected_stdout: string;
  feedback: string;
  compile_error: string | null;
}

interface PracticeResult {
  correct: boolean;
  score: number;
  feedback: string;
  expected_answer: string;
  next_step: string;
}

interface ModuleMastery {
  module_id: string;
  score: number;
  passed: boolean;
  correct: number;
  total: number;
  feedback: string;
}

interface MasteryReport {
  overall_score: number;
  passed: boolean;
  modules: ModuleMastery[];
  strengths: string[];
  next_steps: string[];
}

interface ModuleProgress {
  module_id: string;
  best_score: number;
  passed: boolean;
}

interface LearningModule {
  module_id: string;
  title: string;
  goal: string;
  concepts: LearningConcept[];
  bridge_steps: string[];
  source_content: string;
  practice_tasks: PracticeTask[];
  order: number;
  generated_code?: string | null;
  stdout?: string | null;
  compile_error?: string | null;
}

interface LearningPath {
  theme_dictionary_id: string;
  title: string;
  diagnosis: {
    level: string;
    learner_summary: string;
    interests: string[];
    goals: string[];
    pain_points: string[];
    preferred_examples: string[];
    recommended_start: string;
    confidence_score: number;
    evidence: string[];
  };
  modules: LearningModule[];
  proof_points: string[];
}

interface EditorPageProps {
  token: string;
  user: { email: string; display_name?: string } | null;
}

const conceptFamilyLabel = (key: string) => {
  if (/_kw_(if|elif|else|while|break|continue|and|or|not|true|false|none)/.test(key)) return 'Condition';
  if (/_kw_for|_kw_in|_fn_(iter|next|range|enumerate|zip|map|filter)/.test(key)) return 'Iteration';
  if (/_kw_(def|return|lambda)|_fn_(callable)/.test(key)) return 'Function';
  if (/_fn_(print|input)/.test(key)) return 'Input/Output';
  if (/_fn_(list|dict|set|tuple|len)|_list_|_dict_|_set_/.test(key)) return 'Data';
  if (/_kw_class|_fn_(isinstance|issubclass|type|super)/.test(key)) return 'Objects';
  if (/_kw_(try|except|finally|raise|assert)|_file_|_exc_/.test(key)) return 'Files/Errors';
  return 'Other';
};

const conceptFamilyPriority = (key: string) => {
  const order: Record<string, number> = {
    Condition: 1,
    Iteration: 2,
    Function: 3,
    'Input/Output': 4,
    Data: 5,
    Objects: 6,
    'Files/Errors': 7,
    Other: 8,
  };
  return order[conceptFamilyLabel(key)] || 99;
};

const coreLearningKeys = [
  'py_kw_if', 'py_kw_elif', 'py_kw_else',
  'py_kw_for', 'py_fn_iter', 'py_fn_range',
  'py_kw_def', 'py_kw_return',
  'py_fn_print', 'py_fn_input',
  'py_fn_list', 'py_fn_dict',
  'py_kw_class', 'py_kw_try', 'py_kw_except',
];

const rocketTrailTokens = ['def', 'for', 'if', 'print()', 'return', 'range()', 'lambda', 'True'];

interface RocketParticle {
  id: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  maxLife: number;
  token: string;
  spin: number;
}

const FloatingRocket: React.FC = () => {
  const pointerRef = useRef({ x: -9999, y: -9999 });
  const stateRef = useRef({
    x: 0,
    y: 0,
    vx: 46,
    vy: 14,
    angle: -24,
    boost: false,
    initialized: false,
    lastTime: 0,
    lastSpawn: 0,
  });
  const particleIdRef = useRef(0);
  const particlesRef = useRef<RocketParticle[]>([]);
  const [frame, setFrame] = useState({
    x: 0,
    y: 0,
    angle: -24,
    boost: false,
    particles: [] as RocketParticle[],
  });

  useEffect(() => {
    const onPointerMove = (event: PointerEvent) => {
      pointerRef.current = { x: event.clientX, y: event.clientY };
    };
    const onPointerLeave = () => {
      pointerRef.current = { x: -9999, y: -9999 };
    };

    let rafId = 0;
    const step = (time: number) => {
      const state = stateRef.current;
      const width = window.innerWidth || 1280;
      const height = window.innerHeight || 720;
      const rocketWidth = 150;
      const rocketHeight = 165;
      const margin = 70;

      if (!state.initialized) {
        state.x = Math.max(280, width - 360);
        state.y = Math.max(92, height * 0.16);
        state.initialized = true;
        state.lastTime = time;
      }

      const dt = Math.min(0.034, Math.max(0.001, (time - state.lastTime) / 1000));
      state.lastTime = time;

      const centerX = state.x + rocketWidth / 2;
      const centerY = state.y + rocketHeight / 2;
      const dx = centerX - pointerRef.current.x;
      const dy = centerY - pointerRef.current.y;
      const distance = Math.hypot(dx, dy);
      const triggerDistance = 260;
      state.boost = distance < triggerDistance;

      if (state.boost) {
        const safe = distance || 1;
        const force = (1 - distance / triggerDistance) ** 1.35;
        state.vx += (dx / safe) * force * 1120 * dt;
        state.vy += (dy / safe) * force * 820 * dt;
      } else {
        state.vx += Math.cos(time / 1500) * 10 * dt;
        state.vy += Math.sin(time / 1800) * 8 * dt;
      }

      state.vx *= 0.996;
      state.vy *= 0.996;
      const speed = Math.hypot(state.vx, state.vy);
      const maxSpeed = state.boost ? 310 : 92;
      if (speed > maxSpeed) {
        state.vx = (state.vx / speed) * maxSpeed;
        state.vy = (state.vy / speed) * maxSpeed;
      }

      state.x += state.vx * dt;
      state.y += state.vy * dt;

      if (state.x < margin || state.x > width - rocketWidth - margin) {
        state.x = Math.max(margin, Math.min(width - rocketWidth - margin, state.x));
        state.vx *= -0.78;
      }
      if (state.y < margin || state.y > height - rocketHeight - margin) {
        state.y = Math.max(margin, Math.min(height - rocketHeight - margin, state.y));
        state.vy *= -0.78;
      }

      if (speed > 8) {
        const targetAngle = Math.atan2(state.vy, state.vx) * 180 / Math.PI + 42;
        state.angle += (targetAngle - state.angle) * 0.12;
      }

      const rad = (state.angle - 42) * Math.PI / 180;
      const dirX = Math.cos(rad);
      const dirY = Math.sin(rad);
      if (time - state.lastSpawn > (state.boost ? 46 : 130)) {
        state.lastSpawn = time;
        const id = particleIdRef.current++;
        particlesRef.current.push({
          id,
          x: centerX - dirX * 76 + (Math.random() - 0.5) * 20,
          y: centerY - dirY * 76 + (Math.random() - 0.5) * 20,
          vx: -dirX * (state.boost ? 90 : 42) + (Math.random() - 0.5) * 26,
          vy: -dirY * (state.boost ? 90 : 42) + (Math.random() - 0.5) * 26,
          life: state.boost ? 0.8 : 1.05,
          maxLife: state.boost ? 0.8 : 1.05,
          token: rocketTrailTokens[id % rocketTrailTokens.length],
          spin: (Math.random() - 0.5) * 18,
        });
      }

      particlesRef.current = particlesRef.current
        .map((particle) => ({
          ...particle,
          x: particle.x + particle.vx * dt,
          y: particle.y + particle.vy * dt,
          life: particle.life - dt,
        }))
        .filter((particle) => particle.life > 0)
        .slice(-22);

      setFrame({
        x: state.x,
        y: state.y,
        angle: state.angle,
        boost: state.boost,
        particles: particlesRef.current,
      });

      rafId = window.requestAnimationFrame(step);
    };

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerleave', onPointerLeave);
    rafId = window.requestAnimationFrame(step);
    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerleave', onPointerLeave);
      window.cancelAnimationFrame(rafId);
    };
  }, []);

  return (
    <div className={`cv-floating-rocket-layer${frame.boost ? ' is-boosting' : ''}`} aria-hidden="true">
      <div className="cv-floating-code-trail">
        {frame.particles.map((particle) => {
          const opacity = Math.max(0, particle.life / particle.maxLife);
          return (
            <span
              key={particle.id}
              style={{
                left: particle.x,
                top: particle.y,
                opacity: opacity * 0.45,
                transform: `rotate(${particle.spin}deg) scale(${0.75 + opacity * 0.2})`,
              }}
            >
              {particle.token}
            </span>
          );
        })}
      </div>
      <div
        className="cv-floating-rocket"
        style={{
          ['--rocket-mask' as string]: `url(${rocketImage})`,
          transform: `translate3d(${frame.x}px, ${frame.y}px, 0) rotate(${frame.angle}deg)`,
        }}
      />
    </div>
  );
};

export const EditorPage: React.FC<EditorPageProps> = ({ token, user }) => {
  const [themes, setThemes] = useState<ThemeMapping[]>([]);
  const [selectedTheme, setSelectedTheme] = useState<ThemeMapping | null>(null);
  const [sourceCode, setSourceCode] = useState('');
  const [compiledCode, setCompiledCode] = useState('');
  const [translationTrace, setTranslationTrace] = useState<TranslationTraceLine[]>([]);
  const [isCompiling, setIsCompiling] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [runResult, setRunResult] = useState<any | null>(null);
  const [activeRightTab, setActiveRightTab] = useState<'output' | 'dictionary' | 'learning'>('output');
  const [searchQuery, setSearchQuery] = useState('');
  const [learningPath, setLearningPath] = useState<LearningPath | null>(null);
  const [selectedLearningModuleId, setSelectedLearningModuleId] = useState<string>('');
  const [learningLesson, setLearningLesson] = useState<LearningModule | null>(null);
  const [isLearningLoading, setIsLearningLoading] = useState(false);
  const [learningError, setLearningError] = useState('');
  const [practiceInputs, setPracticeInputs] = useState<Record<string, string>>({});
  const [practiceResults, setPracticeResults] = useState<Record<string, PracticeResult>>({});
  const [practiceCheckingId, setPracticeCheckingId] = useState<string | null>(null);
  const [codeRunResults, setCodeRunResults] = useState<Record<string, CodeRunResult>>({});
  const [codeRunningId, setCodeRunningId] = useState<string | null>(null);
  const [hintsShown, setHintsShown] = useState<Record<string, boolean>>({});
  const [masteryReport, setMasteryReport] = useState<MasteryReport | null>(null);
  const [isGrading, setIsGrading] = useState(false);
  const [moduleProgress, setModuleProgress] = useState<Record<string, ModuleProgress>>({});
  const [productView, setProductView] = useState<EducationView>('learn');
  const selectedLanguage = 'python' as const;

  const fetchThemes = async () => {
    try {
      const response = await fetch(`${BASE_URL}/themes`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setThemes(data);
      }
    } catch (err) {
      console.error('Themes could not be loaded:', err);
    }
  };

  useEffect(() => {
    fetchThemes();
  }, [token]);

  useEffect(() => {
    if (!selectedTheme) return;
    setActiveRightTab('learning');

    const maps = selectedTheme.mappings;
    const pick = (fallback: string, ...keys: string[]) => (
      keys.map((key) => maps[key]).find(Boolean) || fallback
    );

    const functionDef = pick('def', 'py_kw_def', 'function_def');
    const ret = pick('return', 'py_kw_return', 'return');
    const condIf = pick('if', 'py_kw_if', 'if');
    const condElse = pick('else', 'py_kw_else', 'else');
    const prnt = pick('print', 'py_fn_print', 'print');
    const loopFor = pick('for', 'py_kw_for', 'for');
    const loopIn = pick('in', 'py_kw_in', 'in');
    const loopRange = pick('range', 'py_fn_range', 'range');
    const listMake = pick('list', 'py_fn_list', 'py_type_list', 'list');
    const dictMake = pick('dict', 'py_fn_dict', 'py_type_dict', 'dict');

    let code = `@theme: ${selectedTheme.theme_name}\n`;
    code += `@language: python\n`;
    code += `@version: 1\n`;
    code += `---\n`;
    code += `# Personal Python sample for ${selectedTheme.theme_name}\n`;
    code += `${functionDef} calculate_power(levels):\n`;
    code += `    cv_record = ${dictMake}({"base": 100})\n`;
    code += `    cv_rewards = ${listMake}([])\n`;
    code += `    ${loopFor} cv_level ${loopIn} levels:\n`;
    code += `        ${condIf} cv_level <= 1:\n`;
    code += `            cv_rewards.append(cv_record["base"])\n`;
    code += `        ${condElse}:\n`;
    code += `            cv_rewards.append(cv_level * 50)\n`;
    code += `    ${ret} cv_rewards\n\n`;
    code += `${loopFor} cv_value ${loopIn} calculate_power(${loopRange}(1, 4)):\n`;
    code += `    ${prnt}(cv_value)\n`;

    const fallbackCode = code;
    let cancelled = false;

    const loadBackendLesson = async () => {
      try {
        const response = await fetch(`${BASE_URL}/themes/${selectedTheme.id}/lesson`, {
          headers: { 'Authorization': `Bearer ${token}` },
        });
        if (!response.ok) throw new Error('Lesson endpoint failed.');
        const data = await response.json();
        if (cancelled) return;
        setSourceCode(data.source_content || fallbackCode);
        setCompiledCode(data.generated_code || '');
        setRunResult(null);
      } catch (err) {
        console.error('Backend lesson could not be loaded:', err);
        if (cancelled) return;
        setSourceCode(fallbackCode);
        setCompiledCode('');
        setRunResult(null);
      }
    };

    loadBackendLesson();
    return () => {
      cancelled = true;
    };
  }, [selectedTheme, token]);

  useEffect(() => {
    if (!selectedTheme) return;
    let cancelled = false;

    const loadLearningPath = async () => {
      setIsLearningLoading(true);
      setLearningError('');
      setLearningPath(null);
      setLearningLesson(null);
      setModuleProgress({});
      try {
        const [pathResp, progressResp] = await Promise.all([
          fetch(`${BASE_URL}/learning/${selectedTheme.id}/path`, {
            headers: { 'Authorization': `Bearer ${token}` },
          }),
          fetch(`${BASE_URL}/learning/${selectedTheme.id}/progress`, {
            headers: { 'Authorization': `Bearer ${token}` },
          }),
        ]);
        if (!pathResp.ok) throw new Error('Learning path endpoint failed.');
        const data: LearningPath = await pathResp.json();
        if (cancelled) return;
        setLearningPath(data);

        const progressMap: Record<string, ModuleProgress> = {};
        if (progressResp.ok) {
          const progressData = await progressResp.json();
          for (const item of progressData.modules as ModuleProgress[]) {
            progressMap[item.module_id] = item;
          }
          if (!cancelled) setModuleProgress(progressMap);
        }

        // Resume at the first not-yet-passed module; fall back to the
        // diagnosis's recommended start, then the first module.
        const firstIncomplete = data.modules.find((m) => !progressMap[m.module_id]?.passed);
        const recommended = data.diagnosis.recommended_start;
        const resumeId =
          firstIncomplete?.module_id
          || data.modules.find((module) => module.module_id === recommended)?.module_id
          || data.modules[0]?.module_id
          || '';
        setSelectedLearningModuleId(resumeId);
      } catch (err: any) {
        if (!cancelled) setLearningError(err.message || 'Learning path could not be loaded.');
      } finally {
        if (!cancelled) setIsLearningLoading(false);
      }
    };

    loadLearningPath();
    return () => {
      cancelled = true;
    };
  }, [selectedTheme, token]);

  useEffect(() => {
    if (!selectedTheme || !selectedLearningModuleId) return;
    let cancelled = false;

    const loadLearningLesson = async () => {
      setLearningError('');
      // A new module means a fresh practice session — clear previous
      // answers, feedback, hints, and mastery so scores never leak across
      // modules.
      setPracticeInputs({});
      setPracticeResults({});
      setCodeRunResults({});
      setHintsShown({});
      setMasteryReport(null);
      try {
        const response = await fetch(
          `${BASE_URL}/learning/${selectedTheme.id}/lessons/${selectedLearningModuleId}`,
          { headers: { 'Authorization': `Bearer ${token}` } },
        );
        if (!response.ok) throw new Error('Learning lesson endpoint failed.');
        const data: LearningModule = await response.json();
        if (!cancelled) setLearningLesson(data);
      } catch (err: any) {
        if (!cancelled) setLearningError(err.message || 'Learning lesson could not be loaded.');
      }
    };

    loadLearningLesson();
    return () => {
      cancelled = true;
    };
  }, [selectedTheme, selectedLearningModuleId, token]);

  const checkPracticeAnswer = async (taskId: string) => {
    if (!selectedTheme) return;
    const answer = (practiceInputs[taskId] || '').trim();
    if (!answer) return;

    setPracticeCheckingId(taskId);
    try {
      const response = await fetch(
        `${BASE_URL}/learning/${selectedTheme.id}/practice/check`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
          body: JSON.stringify({ task_id: taskId, answer }),
        },
      );
      if (!response.ok) throw new Error('Practice check failed.');
      const data: PracticeResult = await response.json();
      setPracticeResults((prev) => ({ ...prev, [taskId]: data }));
      setMasteryReport(null); // answers changed, previous grade is stale
    } catch (err: any) {
      setLearningError(err.message || 'Practice check failed.');
    } finally {
      setPracticeCheckingId(null);
    }
  };

  const refreshProgress = async () => {
    if (!selectedTheme) return;
    try {
      const response = await fetch(
        `${BASE_URL}/learning/${selectedTheme.id}/progress`,
        { headers: { 'Authorization': `Bearer ${token}` } },
      );
      if (!response.ok) return;
      const data = await response.json();
      const map: Record<string, ModuleProgress> = {};
      for (const item of data.modules as ModuleProgress[]) {
        map[item.module_id] = item;
      }
      setModuleProgress(map);
    } catch {
      // progress is a non-critical enhancement; ignore transient failures
    }
  };

  const runPracticeCode = async (task: PracticeTask) => {
    if (!selectedTheme) return;
    const source = practiceInputs[task.id] ?? task.starter_source ?? '';
    if (!source.trim()) return;

    setCodeRunningId(task.id);
    try {
      const response = await fetch(
        `${BASE_URL}/learning/${selectedTheme.id}/practice/run`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
          body: JSON.stringify({ task_id: task.id, source_content: source }),
        },
      );
      if (!response.ok) throw new Error('Code run failed.');
      const data: CodeRunResult = await response.json();
      setCodeRunResults((prev) => ({ ...prev, [task.id]: data }));
      if (data.correct) refreshProgress();
    } catch (err: any) {
      setLearningError(err.message || 'Code run failed.');
    } finally {
      setCodeRunningId(null);
    }
  };

  const gradeCurrentModule = async () => {
    if (!selectedTheme || !learningLesson) return;
    const answers: Record<string, string> = {};
    for (const task of learningLesson.practice_tasks) {
      if (task.kind === 'write_code') continue; // graded behaviorally via /practice/run
      const value = (practiceInputs[task.id] || '').trim();
      if (value) answers[task.id] = value;
    }
    if (Object.keys(answers).length === 0) return;

    setIsGrading(true);
    try {
      const response = await fetch(
        `${BASE_URL}/learning/${selectedTheme.id}/practice/grade`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
          body: JSON.stringify({ answers }),
        },
      );
      if (!response.ok) throw new Error('Practice grading failed.');
      const data: MasteryReport = await response.json();
      setMasteryReport(data);
      refreshProgress();
    } catch (err: any) {
      setLearningError(err.message || 'Practice grading failed.');
    } finally {
      setIsGrading(false);
    }
  };

  const handleCompile = async () => {
    if (!selectedTheme || !sourceCode.trim()) return;

    setIsCompiling(true);
    setRunResult(null);
    setTranslationTrace([]);
    setActiveRightTab('output');

    try {
      const response = await fetch(`${BASE_URL}/compile`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          source_content: sourceCode,
          theme_dictionary_id: selectedTheme.id,
        }),
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Compile failed.');

      setTranslationTrace(data.translation_trace || []);
      if (data.success) {
        setCompiledCode(data.generated_code);
        setRunResult({
          status: 'success',
          stdout: '[Compiler: Code compiled to Python successfully.]',
          duration_ms: 0,
        });
      } else {
        setCompiledCode('');
        setRunResult({
          status: data.error?.stage === 'codegen' ? 'codegen_error' : 'parse_error',
          diagnostic_error: data.error,
          stdout: null,
          stderr_raw: data.error?.message,
        });
      }
    } catch (err: any) {
      setRunResult({
        status: 'sandbox_error',
        stdout: null,
        stderr_raw: err.message || 'Could not reach compile server.',
      });
    } finally {
      setIsCompiling(false);
    }
  };

  // Keep the latest run/compile handlers in refs so the global keyboard
  // shortcut always calls the current closure without re-binding the listener
  // on every keystroke.
  const compileRef = useRef<() => void>(() => {});
  const executeRef = useRef<() => void>(() => {});
  const canRunRef = useRef(false);

  const handleExecute = async () => {
    if (!selectedTheme || !sourceCode.trim()) return;

    setIsRunning(true);
    setRunResult(null);
    setTranslationTrace([]);
    setActiveRightTab('output');

    try {
      const response = await fetch(`${BASE_URL}/execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          source_content: sourceCode,
          theme_dictionary_id: selectedTheme.id,
        }),
      });

      const data = await response.json();
      if (!response.ok) {
        if (response.status === 503) {
          setRunResult({
            status: 'sandbox_error',
            stdout: null,
            stderr_raw: data.detail || 'Docker sandbox is not available.',
          });
          return;
        }
        throw new Error(data.detail || 'Execution failed.');
      }

      setRunResult(data);
      setTranslationTrace(data.translation_trace || []);
      if (data.generated_code) setCompiledCode(data.generated_code);
    } catch (err: any) {
      setRunResult({
        status: 'sandbox_error',
        stdout: null,
        stderr_raw: err.message || 'Could not reach execution server.',
      });
    } finally {
      setIsRunning(false);
    }
  };

  const canRun = Boolean(selectedTheme) && sourceCode.trim().length > 0 && !isCompiling && !isRunning;
  compileRef.current = handleCompile;
  executeRef.current = handleExecute;
  canRunRef.current = canRun;

  // Ctrl/Cmd+Enter runs, Ctrl/Cmd+B compiles — standard editor shortcuts.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      if (e.key === 'Enter') {
        e.preventDefault();
        if (canRunRef.current) executeRef.current();
      } else if (e.key.toLowerCase() === 'b') {
        e.preventDefault();
        if (canRunRef.current) compileRef.current();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const filteredMappings = selectedTheme
    ? Object.entries(selectedTheme.mappings).filter(([key, val]) => {
        if (!key.startsWith('py_')) return false;
        if (!searchQuery.trim()) return true;
        const query = searchQuery.toLowerCase();
        const rationale = selectedTheme.rationale?.[key]?.toLowerCase() || '';
        return (
          key.toLowerCase().includes(query) ||
          val.toLowerCase().includes(query) ||
          rationale.includes(query)
        );
      }).sort(([a], [b]) => conceptFamilyPriority(a) - conceptFamilyPriority(b) || a.localeCompare(b))
    : [];

  const maxRenderCount = 80;
  const renderedMappings = filteredMappings.slice(0, maxRenderCount);
  const coreLearningMappings = selectedTheme
    ? coreLearningKeys
        .filter((key) => selectedTheme.mappings[key])
        .map((key) => [key, selectedTheme.mappings[key]] as [string, string])
    : [];

  const handleThemeRegenerated = (upgraded: ThemeMapping) => {
    setThemes((current) => [
      upgraded,
      ...current.filter((item) => item.id !== upgraded.id && item.id !== selectedTheme?.id),
    ]);
    setSelectedTheme(upgraded);
  };

  if (selectedTheme && productView !== 'playground') {
    return (
      <EducationPages
        view={productView}
        theme={selectedTheme}
        token={token}
        onNavigate={setProductView}
        onThemeRegenerated={(upgraded) => handleThemeRegenerated({
          ...upgraded,
          rationale: upgraded.rationale ?? undefined,
        })}
      />
    );
  }

  if (!selectedTheme) {
    return (
      <div className="cv-shell cv-landing-shell">
        <header className="cv-topbar">
          <div className="logo-container">
            <h1 className="logo-text">CodeVerse</h1>
            <span className="logo-badge">&gt;&gt;&gt;</span>
          </div>

        </header>

        <main className="cv-hero-stage">
          <aside className="cv-side-rail">CODE IS A LANGUAGE · YOU DEFINE THE WORLD</aside>

          <section className="cv-hero-copy">
            <h2>Write real Python. Shape a language around how you think.</h2>
            <p>CodeVerse remaps syntax while keeping authentic Python visible side by side.</p>
            <div className="cv-how-it-works" aria-label="How CodeVerse works">
              <div><span>1</span><strong>Write Python</strong><small>Start with the real language.</small></div>
              <i>-&gt;</i>
              <div><span>2</span><strong>Describe yourself</strong><small>Interests, goals, and hard concepts.</small></div>
              <i>-&gt;</i>
              <div><span>3</span><strong>Learn the mapping</strong><small>Same logic, personal vocabulary.</small></div>
            </div>
          </section>
          <FloatingRocket />

          <div className="cv-landing-demo-grid">
          <section className="cv-compare-window" aria-label="Python remap example">
            <div className="landing-dino-mascot pixel-dino-mascot" aria-hidden="true" />
            <div className="cv-window-chrome">
              <span />
              <span />
              <span />
              <strong>real python</strong>
              <strong>AMD, in your words</strong>
            </div>
            <AnimatedLandingDemo />
            <div className="cv-code-compare cv-static-code" aria-hidden="true">
              <pre>{`1   def greet(name):
2       for i in range(3):
3           if name:
4               print("hello", name)
5
6       return True`}</pre>
              <div className="cv-arrows">
                <span>→</span><span>→</span><span>→</span><span>→</span><span>→</span><span>→</span>
              </div>
              <pre>{`1   recipe greet(crew):
2       orbit i in range(3):
3           if crew:
4               announce("hello", crew)
5
6       return True`}</pre>
            </div>
          </section>
          <aside className="cv-remap-examples" aria-label="AMD remapping examples">
            <h3>Examples of remapping</h3>
            <div><code>def</code><span>-&gt;</span><code>kernel</code></div>
            <div><code>for</code><span>-&gt;</span><code>dispatch</code></div>
            <div><code>if</code><span>-&gt;</span><code>ready_when</code></div>
            <div><code>print</code><span>-&gt;</span><code>telemetry</code></div>
            <p><Sparkles size={18} /> You still learn real Python underneath.</p>
          </aside>
          </div>

          <ThemePicker
            themes={themes}
            selectedTheme={selectedTheme}
            onSelectTheme={setSelectedTheme}
            token={token}
            onRefreshThemes={fetchThemes}
            mode="hero"
          />
        </main>

        <footer className="cv-footer-line">
          <span>BUILT FOR / BEGINNERS</span>
          <span>FOCUS / PYTHON REMAPPED</span>
          <span>INDEX / 2026</span>
        </footer>
      </div>
    );
  }

  return (
    <div className="cv-shell app-container">
      <FloatingRocket />
      <header className="header glass-panel cv-app-header">
        <div className="logo-container">
          <h1 className="logo-text">CodeVerse</h1>
          <span className="logo-badge">&gt;&gt;&gt;</span>
        </div>

        <nav className="edu-playground-nav" aria-label="Workspace navigation">
          <button onClick={() => setProductView('learn')}>Learn</button>
          <button className="active">Playground</button>
        </nav>

        {user && (
          <div className="user-status">
            <div className="status-dot" />
            <span>{user.display_name || user.email} (Dev)</span>
          </div>
        )}
      </header>

      <div className="control-bar glass-panel">
        <div className="controls-left">
          <ThemePicker
            themes={themes}
            selectedTheme={selectedTheme}
            onSelectTheme={setSelectedTheme}
            token={token}
            onRefreshThemes={fetchThemes}
          />
        </div>

        <div className="controls-right">
          <RunButton
            onCompile={handleCompile}
            onExecute={handleExecute}
            isCompiling={isCompiling}
            isRunning={isRunning}
            disabled={!selectedTheme || !sourceCode.trim()}
          />
        </div>
      </div>

      <main className="main-workspace">
        <div className="editor-pane glass-panel">
          <div className="pane-header">
            <span className="pane-title">Editor (codeverse.cvl)</span>
            <span className="text-xs text-secondary font-mono">
              Personal Python syntax layer
            </span>
          </div>
          <div className="pixel-dino-mascot" aria-hidden="true" />
          <div className="editor-container">
            <MonacoEditor
              value={sourceCode}
              onChange={setSourceCode}
              mappings={selectedTheme ? selectedTheme.mappings : null}
            />
          </div>
        </div>

        <div className="right-pane glass-panel">
          <div className="tab-header border-b border-muted flex justify-between items-center px-4">
            <div className="flex gap-2 py-2">
              <button
                onClick={() => setActiveRightTab('learning')}
                className={`px-4 py-2 text-sm font-semibold rounded-md transition-colors border-0 cursor-pointer ${
                  activeRightTab === 'learning'
                    ? 'bg-primary-glow text-primary'
                    : 'bg-transparent text-secondary hover:text-primary'
                }`}
              >
                Learning
              </button>
              <button
                onClick={() => setActiveRightTab('output')}
                className={`px-4 py-2 text-sm font-semibold rounded-md transition-colors border-0 cursor-pointer ${
                  activeRightTab === 'output'
                    ? 'bg-primary-glow text-primary'
                    : 'bg-transparent text-secondary hover:text-primary'
                }`}
              >
                Translate & Run
              </button>
              <button
                onClick={() => setActiveRightTab('dictionary')}
                className={`px-4 py-2 text-sm font-semibold rounded-md transition-colors border-0 cursor-pointer ${
                  activeRightTab === 'dictionary'
                    ? 'bg-primary-glow text-primary'
                    : 'bg-transparent text-secondary hover:text-primary'
                }`}
              >
                Dictionary
              </button>
            </div>

            {activeRightTab === 'dictionary' && (
              <span className="text-xs text-muted font-mono">
                {filteredMappings.length} Python terms
              </span>
            )}
            {activeRightTab === 'learning' && learningPath && (
              <span className="text-xs text-muted font-mono">
                {learningPath.modules.length} modules
              </span>
            )}
          </div>

          <div className="flex-grow min-h-0 flex flex-col p-4">
            {activeRightTab === 'learning' ? (
              <div className="learning-workbench">
                {isLearningLoading ? (
                  <div className="learning-empty">Building your learning path...</div>
                ) : learningError ? (
                  <div className="learning-error">{learningError}</div>
                ) : learningPath ? (
                  <>
                    <section className="learning-summary">
                      <div>
                        <span className="learning-eyebrow">Personal diagnosis</span>
                        <h3>{learningPath.diagnosis.level} path</h3>
                        <p>{learningPath.diagnosis.learner_summary}</p>
                      </div>
                      <div className="learning-score">
                        <strong>{learningPath.diagnosis.confidence_score}%</strong>
                        <span>confidence</span>
                      </div>
                    </section>

                    <div className="learning-chips">
                      {learningPath.diagnosis.interests.map((item) => (
                        <span key={item}>{item}</span>
                      ))}
                      {learningPath.diagnosis.pain_points.map((item) => (
                        <span key={item}>{item}</span>
                      ))}
                    </div>

                    <div className="module-strip">
                      {learningPath.modules.map((module) => {
                        const done = moduleProgress[module.module_id]?.passed;
                        const classes = [
                          module.module_id === selectedLearningModuleId ? 'selected' : '',
                          done ? 'completed' : '',
                        ].filter(Boolean).join(' ');
                        return (
                          <button
                            key={module.module_id}
                            onClick={() => setSelectedLearningModuleId(module.module_id)}
                            className={classes}
                          >
                            <span>{done ? '✓' : module.order}</span>
                            {module.title}
                          </button>
                        );
                      })}
                    </div>

                    <div className="module-progress-summary">
                      {learningPath.modules.filter((m) => moduleProgress[m.module_id]?.passed).length}
                      {' / '}
                      {learningPath.modules.length} modules mastered
                    </div>

                    {learningLesson && (
                      <section className="lesson-detail">
                        <div className="lesson-head">
                          <div>
                            <span className="learning-eyebrow">Current lesson</span>
                            <h3>{learningLesson.title}</h3>
                            <p>{learningLesson.goal}</p>
                          </div>
                          {learningLesson.compile_error ? (
                            <span className="error-badge">Compile issue</span>
                          ) : (
                            <span className="success-badge">Runnable</span>
                          )}
                        </div>

                        <div className="concept-bridge-grid">
                          {learningLesson.concepts.map((concept) => (
                            <article key={concept.concept_id} className="bridge-card">
                              <span>{concept.title}</span>
                              <strong>{concept.personal_token}</strong>
                              <code>{concept.python_concept}</code>
                              <p>{concept.mental_model}</p>
                            </article>
                          ))}
                        </div>

                        <div className="lesson-columns">
                          <div>
                            <span className="learning-eyebrow">Personal Python source</span>
                            <pre>{learningLesson.source_content}</pre>
                          </div>
                          <div>
                            <span className="learning-eyebrow">Real output</span>
                            <pre>{learningLesson.stdout || learningLesson.compile_error || 'Run data is loading...'}</pre>
                          </div>
                        </div>

                        <div className="practice-box">
                          <span className="learning-eyebrow">Practice</span>
                          {learningLesson.practice_tasks.map((task) => {
                            if (task.kind === 'write_code') {
                              const runResult = codeRunResults[task.id];
                              const codeSolved = Boolean(runResult?.correct);
                              const source = practiceInputs[task.id] ?? task.starter_source ?? '';
                              return (
                                <div key={task.id} className="practice-row">
                                  <p>{task.prompt}</p>
                                  <textarea
                                    className="practice-code-editor"
                                    spellCheck={false}
                                    rows={Math.min(14, Math.max(7, source.split('\n').length + 1))}
                                    value={source}
                                    onChange={(e) =>
                                      setPracticeInputs((prev) => ({ ...prev, [task.id]: e.target.value }))
                                    }
                                    disabled={codeSolved}
                                  />
                                  <div className="practice-actions">
                                    <button
                                      type="button"
                                      className="btn-secondary practice-check-btn"
                                      onClick={() => runPracticeCode(task)}
                                      disabled={codeSolved || codeRunningId === task.id || !source.trim()}
                                    >
                                      {codeRunningId === task.id ? <div className="spinner" /> : 'Run & check'}
                                    </button>
                                    {task.hint && !codeSolved && (
                                      <button
                                        type="button"
                                        className="practice-hint-toggle"
                                        onClick={() =>
                                          setHintsShown((prev) => ({ ...prev, [task.id]: !prev[task.id] }))
                                        }
                                      >
                                        {hintsShown[task.id] ? 'Hide hint' : 'Show hint'}
                                      </button>
                                    )}
                                  </div>

                                  {hintsShown[task.id] && !codeSolved && (
                                    <p className="practice-hint">{task.hint}</p>
                                  )}

                                  {runResult && (
                                    <>
                                      <div className="code-compare">
                                        <div>
                                          <span className="learning-eyebrow">Your output</span>
                                          <pre>
                                            {runResult.compile_error ||
                                              runResult.stderr ||
                                              runResult.stdout ||
                                              '(no output)'}
                                          </pre>
                                        </div>
                                        <div>
                                          <span className="learning-eyebrow">Goal output</span>
                                          <pre>{runResult.expected_stdout}</pre>
                                        </div>
                                      </div>
                                      <div
                                        className={`practice-feedback ${runResult.correct ? 'correct' : 'incorrect'}`}
                                      >
                                        <strong>{runResult.correct ? 'Correct!' : 'Not yet.'}</strong>
                                        <span>{runResult.feedback}</span>
                                        {runResult.correct && task.explanation && (
                                          <span>{task.explanation}</span>
                                        )}
                                      </div>
                                    </>
                                  )}
                                </div>
                              );
                            }

                            const result = practiceResults[task.id];
                            const solved = Boolean(result?.correct);
                            const currentInput = practiceInputs[task.id] || '';
                            return (
                              <div key={task.id} className="practice-row">
                                <p>{task.prompt}</p>

                                {task.choices.length > 0 ? (
                                  <div className="practice-choices">
                                    {task.choices.map((choice) => (
                                      <button
                                        type="button"
                                        key={choice}
                                        className={`practice-choice${currentInput === choice ? ' selected' : ''}`}
                                        onClick={() =>
                                          setPracticeInputs((prev) => ({ ...prev, [task.id]: choice }))
                                        }
                                        disabled={solved}
                                      >
                                        {choice}
                                      </button>
                                    ))}
                                  </div>
                                ) : (
                                  <input
                                    type="text"
                                    className="practice-input"
                                    placeholder="Type your answer..."
                                    value={currentInput}
                                    onChange={(e) =>
                                      setPracticeInputs((prev) => ({ ...prev, [task.id]: e.target.value }))
                                    }
                                    onKeyDown={(e) => {
                                      if (e.key === 'Enter' && !solved) checkPracticeAnswer(task.id);
                                    }}
                                    disabled={solved}
                                  />
                                )}

                                <div className="practice-actions">
                                  <button
                                    type="button"
                                    className="btn-secondary practice-check-btn"
                                    onClick={() => checkPracticeAnswer(task.id)}
                                    disabled={!currentInput.trim() || solved || practiceCheckingId === task.id}
                                  >
                                    {practiceCheckingId === task.id ? <div className="spinner" /> : 'Check'}
                                  </button>
                                  {task.hint && !solved && (
                                    <button
                                      type="button"
                                      className="practice-hint-toggle"
                                      onClick={() =>
                                        setHintsShown((prev) => ({ ...prev, [task.id]: !prev[task.id] }))
                                      }
                                    >
                                      {hintsShown[task.id] ? 'Hide hint' : 'Show hint'}
                                    </button>
                                  )}
                                </div>

                                {hintsShown[task.id] && !solved && (
                                  <p className="practice-hint">{task.hint}</p>
                                )}

                                {result && (
                                  <div className={`practice-feedback ${result.correct ? 'correct' : 'incorrect'}`}>
                                    <strong>{result.correct ? 'Correct!' : 'Not yet.'}</strong>
                                    <span>{result.feedback}</span>
                                    <span>{result.correct && task.explanation ? task.explanation : result.next_step}</span>
                                  </div>
                                )}
                              </div>
                            );
                          })}

                          <div className="practice-grade-bar">
                            <span className="practice-progress-note">
                              {
                                learningLesson.practice_tasks.filter(
                                  (task) =>
                                    practiceResults[task.id]?.correct || codeRunResults[task.id]?.correct,
                                ).length
                              }{' '}
                              / {learningLesson.practice_tasks.length} solved
                            </span>
                            <button
                              type="button"
                              className="btn-primary"
                              onClick={gradeCurrentModule}
                              disabled={
                                isGrading ||
                                !learningLesson.practice_tasks.some(
                                  (task) =>
                                    task.kind !== 'write_code' && (practiceInputs[task.id] || '').trim(),
                                )
                              }
                            >
                              {isGrading ? <div className="spinner" /> : 'Grade this module'}
                            </button>
                          </div>

                          {masteryReport && (
                            <div className={`mastery-report ${masteryReport.passed ? 'passed' : 'failed'}`}>
                              <div className="mastery-score">
                                <strong>{masteryReport.overall_score}%</strong>
                                <span>{masteryReport.passed ? 'Module mastered' : 'Keep practicing'}</span>
                              </div>
                              <ul>
                                {masteryReport.next_steps.map((step) => (
                                  <li key={step}>{step}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      </section>
                    )}
                  </>
                ) : (
                  <div className="learning-empty">Create Personal Python first to see the learning path.</div>
                )}
              </div>
            ) : activeRightTab === 'output' ? (
              <div className="flex flex-col gap-4 flex-1 min-h-0">
                <div className="flex-1 min-h-0 flex flex-col">
                  <TranslationPanel
                    generatedCode={compiledCode}
                    language={selectedLanguage}
                    isLoading={isCompiling}
                    trace={translationTrace}
                  />
                </div>
                <div className="flex-1.2 min-h-0 flex flex-col">
                  <OutputPanel result={runResult} isLoading={isRunning} />
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-4 flex-grow min-h-0">
                {coreLearningMappings.length > 0 && (
                  <section className="learning-map">
                    <div className="learning-map-header">
                      <div>
                        <span className="learning-eyebrow">Learning map</span>
                        <h3>Core Python bridge</h3>
                      </div>
                      <span>{coreLearningMappings.length} essentials</span>
                    </div>
                    <div className="learning-grid">
                      {coreLearningMappings.map(([key, val]) => (
                        <div key={key} className="learning-card">
                          <span className="concept-family-pill">{conceptFamilyLabel(key)}</span>
                          <strong>{val}</strong>
                          <code>{key}</code>
                          {selectedTheme?.rationale?.[key] && (
                            <p>{selectedTheme.rationale[key]}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                <input
                  type="text"
                  placeholder="Search theme token, Python concept, or explanation..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="flex-grow bg-black/40 border border-muted text-primary px-3 py-2 rounded-md outline-none focus:border-primary text-sm"
                />

                <div className="flex-1 overflow-y-auto min-h-0 pr-1">
                  {renderedMappings.length > 0 ? (
                    <div className="grid grid-cols-1 gap-3">
                      {renderedMappings.map(([key, val]) => (
                        <div key={key} className="dict-row-card flex flex-col gap-2 p-3 rounded-lg border border-muted bg-black/30 hover:border-primary-glow/40 transition-colors">
                          <div className="flex flex-col gap-2 sm:flex-row sm:justify-between sm:items-center">
                            <div className="flex flex-col gap-1 min-w-0">
                              <span className="text-[10px] uppercase tracking-wide text-muted">Theme token</span>
                              <span className="font-mono text-sm font-semibold text-primary break-all">{val}</span>
                            </div>
                            <div className="flex flex-col gap-1 sm:items-end min-w-0">
                              <span className="text-[10px] uppercase tracking-wide text-muted">Python concept</span>
                              <span className="concept-family-pill">{conceptFamilyLabel(key)}</span>
                              <span className="font-mono text-xs text-secondary-cyan px-2 py-0.5 rounded bg-cyan-950/40 border border-cyan-800/20 break-all">{key}</span>
                            </div>
                          </div>
                          {selectedTheme?.rationale?.[key] && (
                            <span className="text-xs text-muted leading-relaxed">
                              {selectedTheme.rationale[key]}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="flex items-center justify-center h-40 text-muted text-sm italic">
                      No Python terms match this search.
                    </div>
                  )}

                  {filteredMappings.length > maxRenderCount && (
                    <div className="text-center text-xs text-muted py-3 border-t border-muted mt-3">
                      Showing first {maxRenderCount} of {filteredMappings.length} Python terms. Search to narrow it down.
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};
