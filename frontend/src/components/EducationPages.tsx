import { useCallback, useEffect, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  Circle,
  GraduationCap,
  Lightbulb,
  LockKeyhole,
  Play,
  Sparkles,
  Target,
  Trophy,
  X,
  Zap,
} from 'lucide-react';
import {
  checkBridge,
  checkPracticeAnswer,
  getBridgeChallenge,
  getLearningLesson,
  getLearningPath,
  getLearningProgress,
  getProgressProof,
  gradePractice,
  runPracticeCode,
} from '../lib/api';
import type {
  BridgeChallenge,
  BridgeCheckResult,
  LearningModule,
  LearningPath,
  LearningProgress,
  MasteryReport,
  ModuleProgress,
  PracticeEvaluation,
  PracticeRunResult,
  ProgressProof,
} from '../lib/types';

export type EducationView = 'learn' | 'lesson' | 'challenge' | 'graduation' | 'playground';

interface EducationTheme {
  id: string;
  theme_name: string;
  mappings: Record<string, string>;
}

interface EducationPagesProps {
  view: Exclude<EducationView, 'playground'>;
  theme: EducationTheme;
  token: string;
  onNavigate: (view: EducationView) => void;
}

const realAmdCode = `from amd import RyzenAI

def optimize_model(model):
    for layer in model:
        if layer.ready:
            print("Ryzen AI active")
    return model`;

const mappedAmdCode = `from amd import RyzenAI

kernel optimize_model(model):
    dispatch layer across model:
        ready_when layer.ready:
            telemetry("Ryzen AI active")
    result model`;

export function AnimatedLandingDemo() {
  const [cursor, setCursor] = useState(0);
  const maxLength = Math.max(realAmdCode.length, mappedAmdCode.length);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setCursor((current) => current >= maxLength + 80 ? 0 : current + 1);
    }, 24);
    return () => window.clearInterval(timer);
  }, [maxLength]);

  const visibleCount = Math.min(cursor, maxLength);
  const leftCount = Math.round((visibleCount / maxLength) * realAmdCode.length);
  const rightCount = Math.round((visibleCount / maxLength) * mappedAmdCode.length);

  return (
    <div className="cv-code-compare cv-animated-code" aria-live="polite">
      <pre><code>{realAmdCode.slice(0, leftCount)}</code>{visibleCount < maxLength && <span className="typing-caret" />}</pre>
      <div className="cv-arrows" aria-hidden="true">{Array.from({ length: 8 }, (_, index) => <span key={index}>-&gt;</span>)}</div>
      <pre><code>{mappedAmdCode.slice(0, rightCount)}</code>{visibleCount < maxLength && <span className="typing-caret mapped" />}</pre>
    </div>
  );
}

function ProductHeader({ onNavigate, active = 'learn' }: { onNavigate: (view: EducationView) => void; active?: 'learn' | 'playground' }) {
  return (
    <header className="edu-header">
      <button className="edu-wordmark" onClick={() => onNavigate('learn')}>CODEVERSE</button>
      <nav aria-label="Primary navigation">
        <button className={active === 'learn' ? 'active' : ''} onClick={() => onNavigate('learn')}>Learn</button>
        <button className={active === 'playground' ? 'active' : ''} onClick={() => onNavigate('playground')}>Playground</button>
      </nav>
      <button className="edu-avatar" title="Profile">A</button>
    </header>
  );
}

function PageFooter() {
  return <footer className="edu-footer"><span>BUILT FOR / BEGINNERS</span><span>STACK / PYTHON</span><span>2026</span></footer>;
}

function Dino({ className = '' }: { className?: string }) {
  return <div className={`edu-dino ${className}`} role="img" aria-label="CodeVerse yellow pixel dinosaur" />;
}

function ProgressRing({ value }: { value: number }) {
  return <div className="edu-progress-ring" style={{ '--progress': `${value * 3.6}deg` } as React.CSSProperties}><span>{value}%</span></div>;
}

function LoadingScreen({ onNavigate }: { onNavigate: (view: EducationView) => void }) {
  return (
    <div className="edu-page">
      <ProductHeader onNavigate={onNavigate} />
      <main className="edu-main edu-loading"><Dino /><div className="spinner" /><p>Loading your Python learning path...</p></main>
      <PageFooter />
    </div>
  );
}

function ErrorScreen({ message, onRetry, onNavigate }: { message: string; onRetry: () => void; onNavigate: (view: EducationView) => void }) {
  return (
    <div className="edu-page">
      <ProductHeader onNavigate={onNavigate} />
      <main className="edu-main edu-error-state"><h1>Learning path could not load</h1><p>{message}</p><button onClick={onRetry}>Try again</button></main>
      <PageFooter />
    </div>
  );
}

function progressMap(progress: LearningProgress): Record<string, ModuleProgress> {
  return Object.fromEntries(progress.modules.map((item) => [item.module_id, item]));
}

function DashboardCodePair({ module, compact = false }: { module: LearningModule; compact?: boolean }) {
  return (
    <div className={`edu-code-pair${compact ? ' compact' : ''}`}>
      <div className="edu-code-head">
        <div><strong>personal syntax</strong><span>Your familiar learning layer</span></div>
        <div className="edu-swap">-&gt;</div>
        <div><strong>real python</strong><span>The language underneath</span></div>
      </div>
      <div className="edu-code-body">
        <pre>{module.source_content}</pre>
        <div className="edu-line-arrows" aria-hidden="true">{Array.from({ length: 7 }, (_, index) => <span key={index}>-&gt;</span>)}</div>
        <pre>{module.real_python_preview}</pre>
      </div>
    </div>
  );
}

interface LearnDashboardProps {
  path: LearningPath;
  progress: LearningProgress;
  proof: ProgressProof;
  onOpenLesson: (moduleId: string) => void;
  onNavigate: (view: EducationView) => void;
}

function LearnDashboard({ path, progress, proof, onOpenLesson, onNavigate }: LearnDashboardProps) {
  const byModule = progressMap(progress);
  const graduation = byModule.graduation;
  const completedModules = path.modules.filter((module) => byModule[module.module_id]?.passed).length;
  const completion = Math.round((completedModules / Math.max(path.modules.length, 1)) * 100);
  const nextModule = path.modules.find((module) => !byModule[module.module_id]?.passed) || path.modules[path.modules.length - 1];
  const previewModule = nextModule || path.modules[0];

  return (
    <div className="edu-page">
      <ProductHeader onNavigate={onNavigate} />
      <main className="edu-main edu-dashboard">
        <section className="edu-title-row">
          <div><h1>Learn</h1><p>{path.diagnosis.learner_summary}</p></div>
        </section>

        <section className="edu-stats-panel">
          <div className="edu-stat"><span className="edu-stat-icon blue"><BookOpen /></span><div><small>Current track</small><strong>{path.title.replace('Personal Python Path: ', '')}</strong><span>{proof.total_modules} modules</span></div></div>
          <div className="edu-stat"><ProgressRing value={completion} /><div><small>Progress</small><strong>{completedModules} / {path.modules.length} modules</strong><span>Backend verified</span></div></div>
          <div className="edu-stat"><span className="edu-stat-icon red"><Target /></span><div><small>Concepts</small><strong className="red-text">{proof.total_concepts} covered</strong><span>{proof.runnable_programs} runnable lessons</span></div></div>
          <div className="edu-stat"><span className="edu-stat-icon green">{graduation?.passed ? <Trophy /> : <GraduationCap />}</span><div><small>Graduation</small><strong className="green-text">{graduation?.passed ? 'Graduated' : 'Capstone ready'}</strong><span>Plain Python proof</span></div></div>
        </section>

        <div className="edu-dashboard-grid">
          <section className="edu-module-area">
            <div className="edu-module-grid">
              {path.modules.map((module, index) => {
                const saved = byModule[module.module_id];
                const previous = index === 0 ? null : byModule[path.modules[index - 1].module_id];
                const state = saved?.passed ? 'complete' : index === 0 || previous?.passed || module.module_id === path.diagnosis.recommended_start ? 'active' : 'locked';
                const score = saved?.best_score || 0;
                return (
                  <button key={module.module_id} className={`edu-module-card ${state}`} onClick={() => onOpenLesson(module.module_id)}>
                    <div className="edu-module-top">
                      <span className="edu-module-state">{state === 'complete' ? <Check /> : state === 'locked' ? <LockKeyhole /> : <Circle />}</span>
                      <strong>{String(module.order).padStart(2, '0')}</strong><h2>{module.title}</h2>
                      <span className="edu-state-label">{state === 'complete' ? 'Completed' : state === 'active' ? 'Continue' : 'Preview'}</span>
                    </div>
                    <p>{module.goal}</p>
                    <div className="edu-module-progress"><i style={{ width: `${score}%` }} /><span>{score}%</span></div>
                  </button>
                );
              })}
              <button className={`edu-module-card graduation-card ${graduation?.passed ? 'complete' : 'active'}`} onClick={() => onNavigate('graduation')}>
                <div className="edu-module-top"><span className="edu-module-state">{graduation?.passed ? <Check /> : <GraduationCap />}</span><strong>10</strong><h2>Graduation Bridge</h2><span className="edu-state-label">{graduation?.passed ? 'Graduated' : 'Capstone'}</span></div>
                <p>Remove the personal scaffold and prove you can write standard Python.</p>
                <div className="edu-module-progress"><i style={{ width: graduation?.passed ? '100%' : '0%' }} /><span>{graduation?.passed ? 100 : 0}%</span></div>
              </button>
            </div>
            {previewModule && <DashboardCodePair module={previewModule} compact />}
          </section>

          <aside className="edu-dashboard-side">
            <Dino />
            <section className="edu-side-card">
              <h3><BookOpen /> Current concepts</h3>
              {(previewModule?.concepts || []).slice(0, 4).map((concept) => <div className="edu-map-row" key={concept.concept_id}><code>{concept.personal_token}</code><span>-&gt;</span><code>{concept.python_concept}</code></div>)}
            </section>
            <section className="edu-side-card edu-next-card">
              <h3><Zap /> Next lesson</h3><p>{nextModule?.goal}</p>
              <button onClick={() => nextModule && onOpenLesson(nextModule.module_id)}>Open {nextModule?.title} <ArrowRight /></button>
            </section>
            <section className="edu-side-card edu-next-card">
              <h3><GraduationCap /> Graduation lab</h3><p>Translate personal syntax back into real Python and earn a persistent graduation record.</p>
              <button onClick={() => onNavigate('graduation')}>Open capstone <ArrowRight /></button>
            </section>
          </aside>
        </div>
      </main>
      <PageFooter />
    </div>
  );
}

interface LessonPageProps {
  path: LearningPath;
  lesson: LearningModule;
  progress: LearningProgress;
  onSelectModule: (moduleId: string) => void;
  onStartPractice: () => void;
  onNavigate: (view: EducationView) => void;
}

function LessonPage({ path, lesson, progress, onSelectModule, onStartPractice, onNavigate }: LessonPageProps) {
  const [tab, setTab] = useState<'concept' | 'example' | 'try'>('concept');
  const [hintOpen, setHintOpen] = useState(false);
  const firstConcept = lesson.concepts[0];
  const currentIndex = path.modules.findIndex((module) => module.module_id === lesson.module_id);
  const saved = progress.modules.find((module) => module.module_id === lesson.module_id);
  const goRelative = (offset: number) => {
    const target = path.modules[currentIndex + offset];
    if (target) onSelectModule(target.module_id);
  };

  return (
    <div className="edu-page">
      <ProductHeader onNavigate={onNavigate} />
      <main className="edu-main edu-lesson">
        <div className="edu-breadcrumb"><button onClick={() => onNavigate('learn')}>Learn</button><span>/</span><strong>Python Path</strong><span>/</span><span>{lesson.title}</span></div>
        <section className="edu-lesson-heading">
          <div><h1>Lesson {String(lesson.order).padStart(2, '0')} - {lesson.title}</h1><p>{lesson.goal}</p></div>
          <div className="edu-lesson-progress"><span>Lesson {lesson.order} of {path.modules.length}</span><div><i style={{ width: `${Math.round((lesson.order / path.modules.length) * 100)}%` }} /></div><strong>{saved?.best_score || 0}%</strong><button onClick={() => goRelative(-1)} disabled={currentIndex <= 0}><ArrowLeft /></button><button onClick={() => goRelative(1)} disabled={currentIndex >= path.modules.length - 1}><ArrowRight /></button></div>
        </section>

        <div className="edu-lesson-layout">
          <aside className="edu-lesson-left">
            <section className="edu-side-card edu-concept-card">
              <h3><span>1</span> {firstConcept?.title || 'Concept'}</h3>
              <p>{firstConcept?.mental_model || lesson.why_it_matters}</p>
              {firstConcept && <div className="edu-concept-bridge"><code>{firstConcept.personal_token}</code><span>-&gt;</span><code>{firstConcept.python_concept}</code></div>}
            </section>
            <section className="edu-side-card">
              <h3><Target /> Success criteria</h3>
              {lesson.success_criteria.map((goal, index) => <p className={`edu-goal${index < (saved?.passed ? lesson.success_criteria.length : 1) ? ' done' : ''}`} key={goal}>{index < (saved?.passed ? lesson.success_criteria.length : 1) ? <CheckCircle2 /> : <Circle />}{goal}</p>)}
            </section>
          </aside>

          <section className="edu-lesson-center">
            <Dino className="lesson-dino" />
            <div className="edu-tabs">
              {(['concept', 'example', 'try'] as const).map((name) => <button className={tab === name ? 'active' : ''} onClick={() => setTab(name)} key={name}>{name === 'try' ? 'Practice' : name[0].toUpperCase() + name.slice(1)}</button>)}
            </div>
            {tab === 'concept' && <div className="edu-condition-example"><DashboardCodePair module={lesson} /><p><Sparkles /> The backend compiled this personal syntax into real Python and verified its output.</p></div>}
            {tab === 'example' && <div className="edu-lesson-copy"><h3>Build the mental model</h3>{lesson.lesson_steps.map((step, index) => <div key={step}><span>{index + 1}</span><p>{step}</p></div>)}<h3>Common misconceptions</h3>{lesson.misconception_checks.map((item) => <p className="misconception" key={item}><X />{item}</p>)}</div>}
            {tab === 'try' && <div className="edu-practice-preview"><h3>{lesson.practice_tasks.length} backend-checked exercises</h3>{lesson.practice_tasks.map((task) => <div key={task.id}><span>{task.kind.replace('_', ' ')}</span><p>{task.prompt}</p></div>)}<button onClick={onStartPractice}><Play /> Start practice</button></div>}
          </section>

          <aside className="edu-lesson-right">
            <section className="edu-side-card"><h3><Lightbulb /> Hints</h3><p>{lesson.why_it_matters}</p><button onClick={() => setHintOpen((open) => !open)}>Show hint <ChevronDown /></button>{hintOpen && <p className="edu-hint">{lesson.bridge_steps[0]}</p>}</section>
            <section className="edu-side-card"><h3><BookOpen /> Vocabulary</h3>{lesson.concepts.slice(0, 5).map((concept) => <div className="edu-map-row" key={concept.concept_id}><code>{concept.personal_token}</code><span>-&gt;</span><code>{concept.python_concept}</code></div>)}</section>
            <section className="edu-side-card edu-next-card"><h3><Zap /> Practice</h3><p>Run a real Personal Python exercise and receive backend feedback.</p><button onClick={onStartPractice}>Start exercises <ArrowRight /></button></section>
          </aside>
        </div>
        <section className="edu-output-strip"><pre>Verified output\n\n{lesson.stdout || lesson.expected_stdout || lesson.compile_error}</pre><p><Sparkles /><span><strong>{lesson.compile_error ? 'This lesson needs attention.' : 'Compiled and verified by CodeVerse.'}</strong><span>{lesson.compile_error || 'The personalized source and real Python preview produce the same behavior.'}</span></span></p></section>
      </main>
      <PageFooter />
    </div>
  );
}

interface ChallengePageProps {
  lesson: LearningModule;
  theme: EducationTheme;
  token: string;
  onProgressChanged: () => Promise<void>;
  onNavigate: (view: EducationView) => void;
}

function ChallengePage({ lesson, theme, token, onProgressChanged, onNavigate }: ChallengePageProps) {
  const codeTask = lesson.practice_tasks.find((task) => task.kind === 'write_code');
  const knowledgeTasks = lesson.practice_tasks.filter((task) => task.kind !== 'write_code');
  const [source, setSource] = useState(codeTask?.starter_source || lesson.source_content);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [evaluations, setEvaluations] = useState<Record<string, PracticeEvaluation>>({});
  const [runResult, setRunResult] = useState<PracticeRunResult | null>(null);
  const [mastery, setMastery] = useState<MasteryReport | null>(null);
  const [hintOpen, setHintOpen] = useState(false);
  const [running, setRunning] = useState(false);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    setSource(codeTask?.starter_source || lesson.source_content);
    setAnswers({});
    setEvaluations({});
    setRunResult(null);
    setMastery(null);
  }, [lesson.module_id, codeTask?.starter_source, lesson.source_content]);

  const runCode = async () => {
    if (!codeTask || !source.trim()) return null;
    setRunning(true);
    try {
      const result = await runPracticeCode(token, theme.id, codeTask.id, source);
      setRunResult(result);
      if (result.correct) await onProgressChanged();
      return result;
    } finally {
      setRunning(false);
    }
  };

  const checkAll = async () => {
    setChecking(true);
    try {
      const pairs = knowledgeTasks.filter((task) => answers[task.id]?.trim());
      const results = await Promise.all(pairs.map(async (task) => [task.id, await checkPracticeAnswer(token, theme.id, task.id, answers[task.id])] as const));
      setEvaluations(Object.fromEntries(results));
      const report = pairs.length ? await gradePractice(token, theme.id, Object.fromEntries(pairs.map((task) => [task.id, answers[task.id]]))) : null;
      if (report) setMastery(report);
      await runCode();
      await onProgressChanged();
    } finally {
      setChecking(false);
    }
  };

  const tests = [
    { label: 'Personal syntax compiles and runs', pass: runResult?.status === 'success' },
    { label: 'Program prints the target output', pass: Boolean(runResult?.correct) },
    { label: 'Knowledge checks are correct', pass: knowledgeTasks.length === 0 || knowledgeTasks.every((task) => evaluations[task.id]?.correct) },
  ];
  const passed = tests.filter((test) => test.pass).length;

  return (
    <div className="edu-page">
      <ProductHeader onNavigate={onNavigate} />
      <main className="edu-main edu-challenge">
        <div className="edu-breadcrumb"><button onClick={() => onNavigate('learn')}>Practice</button><span>/</span><strong>{lesson.title}</strong></div>
        <div className="edu-challenge-heading"><div><h1>Practice: {lesson.title}</h1><p>{codeTask?.prompt || lesson.goal}</p></div><span>Backend checked</span><section><small>Module mastery</small><strong>{mastery ? `${mastery.overall_score}%` : 'Not graded yet'}</strong><div><i style={{ width: `${mastery?.overall_score || 0}%` }} /></div></section><section><Zap /><div><small>Runtime</small><strong>{runResult?.status || 'Ready'}</strong><span>Real Python execution</span></div><ProgressRing value={runResult?.correct ? 100 : 0} /></section></div>

        <div className="edu-challenge-layout">
          <section className="edu-challenge-main">
            <div className="edu-mission"><Dino /><div><h2>Your mission</h2><p>{codeTask?.prompt || lesson.goal}</p><span>Goal output: <code>{codeTask ? 'hidden until run' : lesson.expected_stdout.trim()}</code></span></div></div>
            <div className="edu-challenge-editor">
              <div><header><strong>your personal syntax</strong><span>Edit and run through the real backend</span></header><textarea value={source} onChange={(event) => { setSource(event.target.value); setRunResult(null); }} spellCheck={false} /></div>
              <div><header><strong>real python preview</strong><span>What the lesson compiles toward</span></header><pre>{lesson.real_python_preview}</pre></div>
            </div>
            <p className="edu-stuck"><Sparkles /> This is not a visual simulation. Your code is compiled and executed by the learning API.</p>

            {knowledgeTasks.length > 0 && <section className="edu-knowledge-checks"><h2>Knowledge checks</h2>{knowledgeTasks.map((task) => <article key={task.id}><p>{task.prompt}</p>{task.choices.length ? <div>{task.choices.map((choice) => <button className={answers[task.id] === choice ? 'selected' : ''} key={choice} onClick={() => setAnswers((current) => ({ ...current, [task.id]: choice }))}>{choice}</button>)}</div> : <input value={answers[task.id] || ''} onChange={(event) => setAnswers((current) => ({ ...current, [task.id]: event.target.value }))} placeholder="Type your answer" />}{evaluations[task.id] && <span className={evaluations[task.id].correct ? 'correct' : 'incorrect'}>{evaluations[task.id].feedback}</span>}</article>)}</section>}
          </section>

          <aside className="edu-challenge-side">
            <section className="edu-side-card edu-tests"><h3>Verified tests <span>{passed} / 3</span></h3>{tests.map((test) => <div key={test.label} className={runResult || Object.keys(evaluations).length ? (test.pass ? 'pass' : 'fail') : ''}>{runResult || Object.keys(evaluations).length ? (test.pass ? <Check /> : <X />) : <Circle />}<span>{test.label}</span></div>)}</section>
            <section className="edu-side-card"><h3><Lightbulb /> Hint</h3><p>{codeTask?.hint || lesson.bridge_steps[0]}</p><button onClick={() => setHintOpen((open) => !open)}>{hintOpen ? 'Hide hint' : 'Show hint'}</button>{hintOpen && <p className="edu-hint">{codeTask?.explanation || lesson.lesson_steps[0]}</p>}</section>
            <button className="edu-run-button" onClick={runCode} disabled={running || !codeTask}><Play /> {running ? 'Running...' : 'Run code'}</button>
            <button className="edu-check-button" onClick={checkAll} disabled={checking || knowledgeTasks.some((task) => !answers[task.id]?.trim())}>{checking ? 'Checking...' : 'Check module'} <ArrowRight /></button>
            {runResult && <section className={`edu-result-card ${runResult.correct ? 'pass' : 'fail'}`}><strong>{runResult.correct ? 'Behavior verified' : 'Keep working'}</strong><p>{runResult.feedback}</p><pre>{runResult.compile_error || runResult.stderr || runResult.stdout || '(no output)'}</pre><small>Expected: {runResult.expected_stdout}</small></section>}
            {mastery && <section className={`edu-result-card ${mastery.passed ? 'pass' : 'fail'}`}><strong>{mastery.overall_score}% mastery</strong><p>{mastery.modules[0]?.feedback}</p></section>}
          </aside>
        </div>
      </main>
      <PageFooter />
    </div>
  );
}

interface GraduationPageProps {
  theme: EducationTheme;
  token: string;
  progress: LearningProgress;
  onProgressChanged: () => Promise<void>;
  onNavigate: (view: EducationView) => void;
}

function GraduationPage({ theme, token, progress, onProgressChanged, onNavigate }: GraduationPageProps) {
  const [challenge, setChallenge] = useState<BridgeChallenge | null>(null);
  const [source, setSource] = useState('# Rewrite the personal program using standard Python.\n');
  const [result, setResult] = useState<BridgeCheckResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState('');
  const alreadyGraduated = progress.modules.some((module) => module.module_id === 'graduation' && module.passed);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getBridgeChallenge(token, theme.id)
      .then((data) => { if (!cancelled) setChallenge(data); })
      .catch((reason: Error) => { if (!cancelled) setError(reason.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [theme.id, token]);

  const submit = async () => {
    setChecking(true);
    setError('');
    try {
      const checked = await checkBridge(token, theme.id, source);
      setResult(checked);
      if (checked.passed) await onProgressChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Graduation check failed.');
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="edu-page">
      <ProductHeader onNavigate={onNavigate} />
      <main className="edu-main edu-graduation">
        <div className="edu-breadcrumb"><button onClick={() => onNavigate('learn')}>Learn</button><span>/</span><strong>Graduation Bridge</strong></div>
        <section className="edu-graduation-heading"><div><span><GraduationCap /></span><h1>{alreadyGraduated ? 'You graduated from the scaffold.' : 'Prove the bridge worked.'}</h1><p>Translate your personal syntax into standard Python. The backend runs it directly and rejects every personal token.</p></div><Dino /></section>

        {loading ? <div className="edu-inline-loading"><div className="spinner" /> Loading graduation challenge...</div> : error && !challenge ? <div className="edu-inline-error">{error}</div> : challenge && <>
          <section className="edu-graduation-brief"><div><small>Your task</small><p>{challenge.prompt}</p></div><div><small>Expected output</small><pre>{challenge.expected_stdout}</pre></div><div><small>Use real Python</small><p>{challenge.real_keywords.join(', ')}</p></div></section>
          <div className="edu-graduation-editor">
            <section><header><strong>personal reference</strong><span>Translate this - do not paste it</span></header><pre>{challenge.personal_reference}</pre></section>
            <section><header><strong>standard python submission</strong><span>No personal tokens allowed</span></header><textarea value={source} onChange={(event) => { setSource(event.target.value); setResult(null); }} spellCheck={false} /></section>
          </div>
          <div className="edu-graduation-actions"><p><Sparkles /> Checked behaviorally: valid Python, exact output, zero personal tokens.</p><button onClick={submit} disabled={checking || !source.trim()}><GraduationCap /> {checking ? 'Checking...' : 'Check graduation'}</button></div>
          {result && <section className={`edu-graduation-result ${result.passed ? 'graduated' : result.status}`}><span>{result.passed ? <Trophy /> : <Lightbulb />}</span><div><h2>{result.passed ? 'Graduated' : result.status.replaceAll('_', ' ')}</h2><p>{result.feedback}</p>{result.used_personal_tokens.length > 0 && <div className="edu-token-list">{result.used_personal_tokens.map((item) => <code key={item}>{item}</code>)}</div>}<div className="edu-result-output"><pre>Your output\n{result.stdout || result.stderr || '(no output)'}</pre><pre>Expected\n{result.expected_stdout}</pre></div></div></section>}
        </>}
      </main>
      <PageFooter />
    </div>
  );
}

export function EducationPages({ view, theme, token, onNavigate }: EducationPagesProps) {
  const [path, setPath] = useState<LearningPath | null>(null);
  const [progress, setProgress] = useState<LearningProgress | null>(null);
  const [proof, setProof] = useState<ProgressProof | null>(null);
  const [selectedModuleId, setSelectedModuleId] = useState('');
  const [lesson, setLesson] = useState<LearningModule | null>(null);
  const [loading, setLoading] = useState(true);
  const [lessonLoading, setLessonLoading] = useState(false);
  const [error, setError] = useState('');

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [pathData, progressData, proofData] = await Promise.all([
        getLearningPath(token, theme.id),
        getLearningProgress(token, theme.id),
        getProgressProof(token, theme.id),
      ]);
      setPath(pathData);
      setProgress(progressData);
      setProof(proofData);
      setSelectedModuleId((current) => current || pathData.diagnosis.recommended_start || pathData.modules[0]?.module_id || '');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Learning path could not load.');
    } finally {
      setLoading(false);
    }
  }, [theme.id, token]);

  const refreshProgress = useCallback(async () => {
    const data = await getLearningProgress(token, theme.id);
    setProgress(data);
  }, [theme.id, token]);

  useEffect(() => { void loadOverview(); }, [loadOverview]);
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'smooth' }); }, [view, selectedModuleId]);

  useEffect(() => {
    if (!selectedModuleId || (view !== 'lesson' && view !== 'challenge')) return;
    let cancelled = false;
    setLessonLoading(true);
    setError('');
    getLearningLesson(token, theme.id, selectedModuleId)
      .then((data) => { if (!cancelled) setLesson(data); })
      .catch((reason: Error) => { if (!cancelled) setError(reason.message); })
      .finally(() => { if (!cancelled) setLessonLoading(false); });
    return () => { cancelled = true; };
  }, [selectedModuleId, theme.id, token, view]);

  const openLesson = (moduleId: string) => { setSelectedModuleId(moduleId); onNavigate('lesson'); };
  const selectLesson = (moduleId: string) => { setSelectedModuleId(moduleId); setLesson(null); };

  if (loading || !path || !progress || !proof) {
    if (error) return <ErrorScreen message={error} onRetry={() => void loadOverview()} onNavigate={onNavigate} />;
    return <LoadingScreen onNavigate={onNavigate} />;
  }
  if (view === 'graduation') return <GraduationPage theme={theme} token={token} progress={progress} onProgressChanged={refreshProgress} onNavigate={onNavigate} />;
  if (view === 'lesson' || view === 'challenge') {
    if (lessonLoading || !lesson) return <LoadingScreen onNavigate={onNavigate} />;
    if (view === 'challenge') return <ChallengePage lesson={lesson} theme={theme} token={token} onProgressChanged={refreshProgress} onNavigate={onNavigate} />;
    return <LessonPage path={path} lesson={lesson} progress={progress} onSelectModule={selectLesson} onStartPractice={() => onNavigate('challenge')} onNavigate={onNavigate} />;
  }
  return <LearnDashboard path={path} progress={progress} proof={proof} onOpenLesson={openLesson} onNavigate={onNavigate} />;
}
