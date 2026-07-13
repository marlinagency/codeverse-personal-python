import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  Circle,
  GraduationCap,
  Lightbulb,
  Library,
  LockKeyhole,
  Play,
  RefreshCw,
  Search,
  Sparkles,
  Target,
  Trophy,
  X,
  Zap,
} from 'lucide-react';
import {
  checkBridge,
  checkPracticeAnswer,
  compileSource,
  executeSource,
  getBridgeChallenge,
  getLearningLesson,
  getLearningAssessment,
  getLearningPath,
  getLearningProgress,
  getProgressProof,
  getThemeDictionaryCatalog,
  gradePractice,
  regenerateTheme,
  runPracticeCode,
  submitLearningAssessment,
} from '../lib/api';
import type {
  AssessmentResult,
  BridgeChallenge,
  BridgeCheckResult,
  ExecutionRunResult,
  LearningModule,
  LearningEvidence,
  LearningPath,
  LearningProgress,
  MasteryReport,
  ModuleProgress,
  PracticeEvaluation,
  PracticeRunResult,
  ProgressProof,
  ThemeDictionaryCatalog,
  ThemeDictionary,
} from '../lib/types';

export type EducationView = 'learn' | 'lesson' | 'challenge' | 'assessment' | 'graduation' | 'dictionary' | 'playground';

interface EducationTheme {
  id: string;
  theme_name: string;
  mappings: Record<string, string>;
  llm_provider?: string;
  llm_model?: string;
}

interface EducationPagesProps {
  view: Exclude<EducationView, 'playground'>;
  theme: EducationTheme;
  token: string;
  onNavigate: (view: EducationView) => void;
  onThemeRegenerated: (theme: ThemeDictionary) => void;
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

function ProductHeader({ onNavigate, active = 'learn' }: { onNavigate: (view: EducationView) => void; active?: 'learn' | 'dictionary' | 'playground' }) {
  return (
    <header className="edu-header">
      <button className="edu-wordmark" onClick={() => onNavigate('learn')}>CODEVERSE</button>
      <nav aria-label="Primary navigation">
        <button className={active === 'learn' ? 'active' : ''} onClick={() => onNavigate('learn')}>Learn</button>
        <button className={active === 'dictionary' ? 'active' : ''} onClick={() => onNavigate('dictionary')}>Dictionary</button>
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
  theme: EducationTheme;
  path: LearningPath;
  progress: LearningProgress;
  proof: ProgressProof;
  evidence: LearningEvidence;
  onOpenLesson: (moduleId: string) => void;
  onNavigate: (view: EducationView) => void;
}

function LearnDashboard({ theme, path, progress, proof, evidence, onOpenLesson, onNavigate }: LearnDashboardProps) {
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

        {theme.llm_model === 'codeverse-student' && (
          <section className="edu-provenance amd edu-dashboard-provenance" aria-label="AMD model provenance">
            <span className="edu-provenance-dot" />
            <span><strong>Live AMD result</strong> · semantic profile generated by <code>codeverse-student</code>, our Gemma model fine-tuned with LoRA on AMD Instinct</span>
          </section>
        )}

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
                <div className="edu-module-top"><span className="edu-module-state">{graduation?.passed ? <Check /> : <GraduationCap />}</span><strong>{String(path.modules.length + 1).padStart(2, '0')}</strong><h2>Graduation Bridge</h2><span className="edu-state-label">{graduation?.passed ? 'Graduated' : 'Capstone'}</span></div>
                <p>Remove the personal scaffold and prove you can write standard Python.</p>
                <div className="edu-module-progress"><i style={{ width: graduation?.passed ? '100%' : '0%' }} /><span>{graduation?.passed ? 100 : 0}%</span></div>
              </button>
            </div>
            {previewModule && <DashboardCodePair module={previewModule} compact />}
          </section>

          <aside className="edu-dashboard-side">
            <Dino />
            <section className="edu-side-card edu-evidence-card">
              <h3><BarChart3 /> Learning evidence</h3>
              <div className="edu-evidence-scores">
                <span><small>Baseline</small><strong>{evidence.pre_score ?? '--'}%</strong></span>
                <span><small>Final</small><strong>{evidence.post_score ?? '--'}%</strong></span>
                <span><small>Gain</small><strong>{evidence.gain === null ? '--' : `${evidence.gain >= 0 ? '+' : ''}${evidence.gain}`} pts</strong></span>
              </div>
              <button onClick={() => onNavigate('assessment')}>{evidence.pre_score === null ? 'Take baseline' : evidence.post_score === null ? 'Measure final skill' : 'View evidence'} <ArrowRight /></button>
            </section>
            <section className="edu-side-card">
              <h3><BookOpen /> Current concepts</h3>
              {(previewModule?.concepts || []).slice(0, 4).map((concept) => <div className="edu-map-row" key={concept.concept_id}><code>{concept.personal_token}</code><span>-&gt;</span><code>{concept.python_concept}</code></div>)}
            </section>
            <section className="edu-side-card edu-next-card">
              <h3><Library /> Full Python Dictionary</h3><p>Explore every generated Python token and its canonical counterpart.</p>
              <button onClick={() => onNavigate('dictionary')}>Open dictionary <ArrowRight /></button>
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
        <section className={`edu-scaffold-status ${lesson.scaffold_stage}`}>
          <div><small>Learning stage</small><strong>{scaffoldStageLabel(lesson.scaffold_stage)}</strong><span>{lesson.practice_syntax === 'python' ? 'Practice uses standard Python' : 'Practice uses your personal syntax'}</span></div>
          <div><small>Personal support</small><strong>{lesson.personal_support_percent}%</strong><div><i style={{ width: `${lesson.personal_support_percent}%` }} /></div></div>
          <p>{scaffoldStageCopy(lesson.scaffold_stage)}</p>
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
            {tab === 'example' && <div className="edu-lesson-copy">
              <h3>{lesson.lesson_sections.length ? `${lesson.lesson_sections.length} lesson chapters` : 'Build the mental model'}</h3>
              {lesson.lesson_sections.length ? <div className="edu-section-list">{lesson.lesson_sections.map((section, index) => <article className="edu-lesson-section" key={section.section_id}>
                <header><span>{index + 1}</span><div><small>{section.objective}</small><h4>{section.title}</h4></div></header>
                <p>{section.explanation}</p>
                <ul>{section.key_points.map((point) => <li key={point}>{point}</li>)}</ul>
                <div className="edu-section-code"><div><small>Personal Python</small><pre>{section.personal_example}</pre></div><div><small>Real Python</small><pre>{section.real_python_example}</pre></div></div>
                <div className="edu-section-output"><small>Expected output</small><pre>{section.expected_output}</pre></div>
              </article>)}</div> : <div className="edu-lesson-steps">{lesson.lesson_steps.map((step, index) => <div key={step}><span>{index + 1}</span><p>{step}</p></div>)}</div>}
              <h3>Common misconceptions</h3>{lesson.misconception_checks.map((item) => <p className="misconception" key={item}><X />{item}</p>)}
            </div>}
            {tab === 'try' && <div className="edu-practice-preview"><h3>{lesson.practice_tasks.length} backend-checked exercises</h3>{lesson.practice_tasks.map((task) => <div key={task.id}><span>{task.kind.replace('_', ' ')}</span><p>{task.prompt}</p></div>)}<button onClick={onStartPractice}><Play /> Start practice</button></div>}
          </section>

          <aside className="edu-lesson-right">
            <section className="edu-side-card"><h3><Lightbulb /> Hints</h3><p>{lesson.why_it_matters}</p><button onClick={() => setHintOpen((open) => !open)}>Show hint <ChevronDown /></button>{hintOpen && <p className="edu-hint">{lesson.bridge_steps[0]}</p>}</section>
            <section className="edu-side-card"><h3><BookOpen /> Vocabulary</h3>{lesson.concepts.map((concept) => <div className="edu-map-row" key={concept.concept_id}><code>{concept.personal_token}</code><span>-&gt;</span><code>{concept.python_concept}</code></div>)}</section>
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
  const [compiledPreview, setCompiledPreview] = useState('');
  const [previewStatus, setPreviewStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [previewMessage, setPreviewMessage] = useState('');
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
    setCompiledPreview('');
    setPreviewStatus('loading');
    setPreviewMessage('');
  }, [lesson.module_id, codeTask?.starter_source, lesson.source_content]);

  useEffect(() => {
    if (!source.trim()) {
      setCompiledPreview('');
      setPreviewStatus('error');
      setPreviewMessage('Write Personal Python to generate its matching preview.');
      return;
    }

    if (codeTask?.syntax_mode === 'python') {
      setCompiledPreview(source);
      setPreviewStatus('ready');
      setPreviewMessage('This advanced exercise runs as standard Python without the personal compiler.');
      return;
    }

    let cancelled = false;
    setPreviewStatus('loading');
    setPreviewMessage('Compiling the code on the left...');
    const timeoutId = window.setTimeout(() => {
      compileSource(token, source, theme.id)
        .then((result) => {
          if (cancelled) return;
          if (result.success && result.generated_code) {
            setCompiledPreview(result.generated_code);
            setPreviewStatus('ready');
            setPreviewMessage('Live preview of the current Personal Python source.');
            return;
          }
          setCompiledPreview('');
          setPreviewStatus('error');
          setPreviewMessage(result.error?.themed_message || result.error?.message || 'The current source does not compile yet.');
        })
        .catch((reason: Error) => {
          if (cancelled) return;
          setCompiledPreview('');
          setPreviewStatus('error');
          setPreviewMessage(reason.message || 'Could not compile the current source.');
        });
    }, 300);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [source, theme.id, token, codeTask?.syntax_mode]);

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
    { label: codeTask?.syntax_mode === 'python' ? 'Standard Python runs' : 'Personal syntax compiles and runs', pass: runResult?.status === 'success' },
    { label: 'Program prints the target output', pass: Boolean(runResult?.correct) },
    { label: codeTask?.syntax_mode === 'python' ? 'Personal scaffold is removed' : 'Knowledge checks are correct', pass: codeTask?.syntax_mode === 'python' ? runResult?.status === 'success' : knowledgeTasks.length === 0 || knowledgeTasks.every((task) => evaluations[task.id]?.correct) },
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
              <div><header><strong>{codeTask?.syntax_mode === 'python' ? 'standard python' : 'your personal syntax'}</strong><span>{codeTask?.syntax_mode === 'python' ? 'The scaffold is now removed' : 'Edit and run through the real backend'}</span></header><textarea value={source} onChange={(event) => { setSource(event.target.value); setRunResult(null); }} spellCheck={false} /></div>
              <div><header><strong>matching real python</strong><span>{previewStatus === 'ready' ? 'Live from the code on the left' : 'Waiting for valid Personal Python'}</span></header><pre className={previewStatus === 'error' ? 'compile-preview-error' : ''}>{compiledPreview || previewMessage}</pre></div>
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

const DICTIONARY_BATCH_SIZE = 96;

function prettyCategory(value: string) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function scaffoldStageLabel(stage: LearningModule['scaffold_stage']) {
  if (stage === 'personal') return 'Personal Foundation';
  if (stage === 'bridge') return 'Concept Bridge';
  if (stage === 'python_forward') return 'Python Forward';
  return 'Real Python';
}

function scaffoldStageCopy(stage: LearningModule['scaffold_stage']) {
  if (stage === 'personal') return 'Build the mental model with memorable personal cues while canonical Python stays visible.';
  if (stage === 'bridge') return 'Compare both vocabularies and begin recalling the canonical Python names yourself.';
  if (stage === 'python_forward') return 'Write standard Python in practice while personal tokens remain available only as reference.';
  return 'Work directly in standard Python and prove that the temporary syntax layer is no longer required.';
}

function DictionaryPage({ theme, token, onNavigate, onThemeRegenerated }: { theme: EducationTheme; token: string; onNavigate: (view: EducationView) => void; onThemeRegenerated: (theme: ThemeDictionary) => void }) {
  const [catalog, setCatalog] = useState<ThemeDictionaryCatalog | null>(null);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');
  const [tier, setTier] = useState('all');
  const [visibleLimit, setVisibleLimit] = useState(DICTIONARY_BATCH_SIZE);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [upgrading, setUpgrading] = useState(false);
  const [trySource, setTrySource] = useState(() => {
    const printToken = theme.mappings.py_fn_print || 'print';
    return `@theme: ${theme.theme_name}\n@language: python\n@version: 1\n---\n${printToken}("Hello from ${theme.theme_name}!")`;
  });
  const [tryResult, setTryResult] = useState<Partial<ExecutionRunResult> | null>(null);
  const [tryRunning, setTryRunning] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    getThemeDictionaryCatalog(token, theme.id)
      .then((data) => { if (!cancelled) setCatalog(data); })
      .catch((reason: Error) => { if (!cancelled) setError(reason.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [theme.id, token]);

  useEffect(() => { setVisibleLimit(DICTIONARY_BATCH_SIZE); }, [query, category, tier]);

  const filteredEntries = useMemo(() => {
    if (!catalog) return [];
    const folded = query.trim().toLowerCase();
    return catalog.entries.filter((entry) => {
      if (category !== 'all' && entry.category !== category) return false;
      if (tier !== 'all' && entry.tier !== tier) return false;
      if (!folded) return true;
      return [entry.personal_token, entry.python_name, entry.real_syntax, entry.concept_id, entry.description]
        .some((value) => value.toLowerCase().includes(folded));
    });
  }, [catalog, category, query, tier]);

  const visibleEntries = filteredEntries.slice(0, visibleLimit);
  const categories = catalog ? Object.entries(catalog.category_counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])) : [];
  const safeCount = catalog?.entries.filter((entry) => entry.sandbox_safe).length || 0;

  const upgradeVocabulary = async () => {
    setUpgrading(true);
    setError('');
    try {
      const upgraded = await regenerateTheme(token, theme.id);
      onThemeRegenerated(upgraded);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Vocabulary upgrade failed.');
    } finally {
      setUpgrading(false);
    }
  };

  const runTry = async () => {
    if (!trySource.trim()) return;
    setTryRunning(true);
    try {
      const result = await executeSource(token, trySource, theme.id);
      setTryResult(result);
    } catch (reason) {
      setTryResult({
        status: 'runtime_error',
        stderr_raw: reason instanceof Error ? reason.message : 'Could not run this code.',
      });
    } finally {
      setTryRunning(false);
    }
  };

  return (
    <div className="edu-page">
      <ProductHeader onNavigate={onNavigate} active="dictionary" />
      <main className="edu-main edu-dictionary">
        <div className="edu-breadcrumb"><button onClick={() => onNavigate('learn')}>Learn</button><span>/</span><strong>Full Python Dictionary</strong></div>
        <section className="edu-dictionary-heading">
          <div><span><Library /></span><h1>{theme.theme_name} Python Dictionary</h1><p>Every generated personal token, connected back to canonical Python.</p></div>
          <Dino />
        </section>

        <section className="edu-dictionary-tryit">
          <h3><Zap /> Try it</h3>
          <p>Write personal syntax and run it against the real backend — no lesson required. Keep the <code>@theme</code>/<code>@language</code>/<code>@version</code> header and <code>---</code> separator; edit the code below it.</p>
          <div className="edu-challenge-editor">
            <div>
              <header><strong>your personal syntax</strong><span>Edit freely</span></header>
              <textarea
                value={trySource}
                onChange={(event) => { setTrySource(event.target.value); setTryResult(null); }}
                placeholder="Write personal-syntax Python here..."
                spellCheck={false}
              />
            </div>
            <div>
              <header><strong>output</strong><span>{tryResult ? tryResult.status : 'Not run yet'}</span></header>
              <pre className={tryResult && tryResult.status !== 'success' ? 'compile-preview-error' : ''}>
                {tryResult ? (tryResult.stderr_raw || tryResult.error_message_themed || tryResult.stdout || '(no output)') : 'Run your code to see output here.'}
              </pre>
            </div>
          </div>
          <button className="edu-run-button" onClick={() => void runTry()} disabled={tryRunning || !trySource.trim()}>
            <Play /> {tryRunning ? 'Running...' : 'Run code'}
          </button>
        </section>

        {loading ? <div className="edu-inline-loading"><div className="spinner" /> Loading the complete Python dictionary...</div> : error ? <div className="edu-inline-error">{error}</div> : catalog && <>
          <section className={`edu-provenance${catalog.llm_model === 'codeverse-student' ? ' amd' : ''}`}>
            <span className="edu-provenance-dot" />
            {catalog.llm_model === 'codeverse-student'
              ? <span>Generated on <strong>AMD Instinct</strong> by <code>codeverse-student</code> — our Gemma student fine-tuned with LoRA</span>
              : <span>Generated by <code>{catalog.llm_model}</code> · {catalog.llm_provider}</span>}
          </section>
          <section className="edu-quality-band">
            <div className="edu-quality-score"><small>Vocabulary quality</small><strong>{catalog.quality.overall_score}</strong><span>Grade {catalog.quality.grade}</span></div>
            <div><small>Brevity</small><strong>{catalog.quality.brevity_score}%</strong></div>
            <div><small>Python meaning</small><strong>{catalog.quality.semantic_score}%</strong></div>
            <div><small>Root diversity</small><strong>{catalog.quality.diversity_score}%</strong></div>
            {catalog.quality.upgrade_recommended ? <button onClick={() => void upgradeVocabulary()} disabled={upgrading}><RefreshCw />{upgrading ? 'Upgrading...' : 'Upgrade vocabulary'}</button> : <span className="edu-quality-ready"><CheckCircle2 />Brain V2 ready</span>}
          </section>
          {catalog.quality.issues.length > 0 && <div className="edu-quality-issues">{catalog.quality.issues.join(' ')}</div>}
          <section className="edu-dictionary-stats">
            <div><small>Total mappings</small><strong>{catalog.total}</strong><span>Python only</span></div>
            <div><small>Categories</small><strong>{Object.keys(catalog.category_counts).length}</strong><span>Grouped for learning</span></div>
            <div><small>Sandbox safe</small><strong>{safeCount}</strong><span>Runnable without external libraries</span></div>
            <div><small>Theme</small><strong>{catalog.theme_name}</strong><span>Personal syntax layer</span></div>
          </section>

          <section className="edu-dictionary-toolbar" aria-label="Dictionary filters">
            <label><Search /><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search a personal token or Python concept" /></label>
            <select aria-label="Filter by category" value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="all">All categories ({catalog.total})</option>
              {categories.map(([name, count]) => <option key={name} value={name}>{prettyCategory(name)} ({count})</option>)}
            </select>
            <select aria-label="Filter by tier" value={tier} onChange={(event) => setTier(event.target.value)}>
              <option value="all">All tiers</option>
              {Object.entries(catalog.tier_counts).map(([name, count]) => <option key={name} value={name}>{prettyCategory(name)} ({count})</option>)}
            </select>
          </section>

          <div className="edu-dictionary-summary"><span>Showing {Math.min(visibleEntries.length, filteredEntries.length)} of {filteredEntries.length}</span><span>Personal token <strong>-&gt;</strong> real Python</span></div>

          {visibleEntries.length ? <section className="edu-dictionary-grid">
            {visibleEntries.map((entry) => <article className="edu-dictionary-entry" key={entry.concept_id}>
              <div className="edu-dictionary-map">
                <div><small>Your token</small><code>{entry.personal_token}</code></div>
                <span>-&gt;</span>
                <div><small>Real Python</small><strong>{entry.python_name}</strong></div>
              </div>
              <div className="edu-dictionary-badges"><span>{prettyCategory(entry.category)}</span><span>{entry.tier}</span><span className={entry.sandbox_safe ? 'safe' : 'reference'}>{entry.sandbox_safe ? 'sandbox safe' : 'reference only'}</span></div>
              <pre>{entry.real_syntax}</pre>
              <p>{entry.description}</p>
              {entry.rationale && <small className="edu-dictionary-rationale">{entry.rationale}</small>}
              <code className="edu-concept-id">{entry.concept_id}</code>
            </article>)}
          </section> : <div className="edu-dictionary-empty">No Python mappings match these filters.</div>}

          {visibleEntries.length < filteredEntries.length && <button className="edu-dictionary-more" onClick={() => setVisibleLimit((current) => current + DICTIONARY_BATCH_SIZE)}>Load more mappings <ArrowRight /></button>}
        </>}
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

interface AssessmentPageProps {
  theme: EducationTheme;
  token: string;
  evidence: LearningEvidence;
  onEvidenceChanged: () => Promise<LearningEvidence>;
  onNavigate: (view: EducationView) => void;
}

function AssessmentPage({ theme, token, evidence, onEvidenceChanged, onNavigate }: AssessmentPageProps) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<AssessmentResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const phase: 'pre' | 'post' = evidence.pre_score === null ? 'pre' : 'post';
  const finalLocked = phase === 'post' && evidence.readiness === 'learning_in_progress';
  const allAnswered = evidence.questions.every((question) => Boolean(answers[question.id]));

  const submit = async () => {
    if (!allAnswered || finalLocked) return;
    setSubmitting(true);
    setError('');
    try {
      const checked = await submitLearningAssessment(token, theme.id, phase, answers);
      setResult(checked);
      await onEvidenceChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Assessment could not be checked.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="edu-page">
      <ProductHeader onNavigate={onNavigate} />
      <main className="edu-main edu-assessment">
        <div className="edu-breadcrumb"><button onClick={() => onNavigate('learn')}>Learn</button><span>/</span><strong>Learning Evidence</strong></div>
        <section className="edu-assessment-heading">
          <div><span><BarChart3 /></span><h1>{evidence.post_score !== null ? 'Your Python learning evidence' : phase === 'pre' ? 'Set your Python baseline' : 'Measure what you learned'}</h1><p>The same eight real Python concepts are measured before and after the course. Personal tokens never appear in this test.</p></div>
          <Dino />
        </section>

        <section className="edu-assessment-summary">
          <div><small>Baseline</small><strong>{evidence.pre_score ?? '--'}%</strong></div>
          <div><small>Final</small><strong>{evidence.post_score ?? '--'}%</strong></div>
          <div><small>Learning gain</small><strong>{evidence.gain === null ? '--' : `${evidence.gain >= 0 ? '+' : ''}${evidence.gain} pts`}</strong></div>
          <div><small>Evidence status</small><strong>{evidence.readiness.replaceAll('_', ' ')}</strong></div>
        </section>

        {evidence.post_score !== null && !result ? (
          <section className="edu-gain-report">
            <h2>Concept-level gain</h2>
            <div>{Object.entries(evidence.concept_gain).map(([concept, gain]) => <span key={concept}><strong>{concept}</strong><i className={gain >= 0 ? 'positive' : 'negative'}>{gain >= 0 ? '+' : ''}{gain} pts</i></span>)}</div>
            <button onClick={() => onNavigate('learn')}>Return to learning path <ArrowRight /></button>
          </section>
        ) : finalLocked ? (
          <section className="edu-assessment-locked"><GraduationCap /><div><h2>Final test unlocks after graduation</h2><p>Complete the learning modules and the real-Python graduation bridge first. Your baseline is safely locked.</p></div><button onClick={() => onNavigate('graduation')}>Open graduation bridge <ArrowRight /></button></section>
        ) : (
          <>
            <div className="edu-question-grid">
              {evidence.questions.map((question, index) => (
                <fieldset key={question.id} className="edu-question">
                  <legend><span>{String(index + 1).padStart(2, '0')}</span><strong>{question.concept}</strong></legend>
                  <pre>{question.prompt}</pre>
                  <div>{question.choices.map((choice) => <label key={choice} className={answers[question.id] === choice ? 'selected' : ''}><input type="radio" name={question.id} value={choice} checked={answers[question.id] === choice} onChange={() => setAnswers((current) => ({ ...current, [question.id]: choice }))} /><span>{choice}</span></label>)}</div>
                </fieldset>
              ))}
            </div>
            <div className="edu-assessment-actions"><p>{Object.keys(answers).length} / {evidence.questions.length} answered</p><button disabled={!allAnswered || submitting} onClick={submit}><BarChart3 /> {submitting ? 'Scoring...' : phase === 'pre' ? 'Lock baseline' : 'Calculate learning gain'}</button></div>
          </>
        )}

        {error && <div className="edu-inline-error">{error}</div>}
        {result && <section className="edu-assessment-result"><div><span>{result.score}%</span><h2>{result.correct} of {result.total} correct</h2><p>{result.phase === 'pre' ? 'Baseline saved. This score will not change on a retry.' : 'Final score saved. Your learning gain is now measurable.'}</p></div><div>{result.concept_scores.map((item) => <span key={item.concept} className={item.score === 100 ? 'pass' : ''}>{item.score === 100 ? <Check /> : <X />} {item.concept}</span>)}</div><button onClick={() => onNavigate('learn')}>Continue learning <ArrowRight /></button></section>}
      </main>
      <PageFooter />
    </div>
  );
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

export function EducationPages({ view, theme, token, onNavigate, onThemeRegenerated }: EducationPagesProps) {
  const [path, setPath] = useState<LearningPath | null>(null);
  const [progress, setProgress] = useState<LearningProgress | null>(null);
  const [proof, setProof] = useState<ProgressProof | null>(null);
  const [evidence, setEvidence] = useState<LearningEvidence | null>(null);
  const [selectedModuleId, setSelectedModuleId] = useState('');
  const [lesson, setLesson] = useState<LearningModule | null>(null);
  const [loading, setLoading] = useState(true);
  const [lessonLoading, setLessonLoading] = useState(false);
  const [error, setError] = useState('');

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [pathData, progressData, proofData, evidenceData] = await Promise.all([
        getLearningPath(token, theme.id),
        getLearningProgress(token, theme.id),
        getProgressProof(token, theme.id),
        getLearningAssessment(token, theme.id),
      ]);
      setPath(pathData);
      setProgress(progressData);
      setProof(proofData);
      setEvidence(evidenceData);
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

  const refreshEvidence = useCallback(async () => {
    const data = await getLearningAssessment(token, theme.id);
    setEvidence(data);
    return data;
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

  if (loading || !path || !progress || !proof || !evidence) {
    if (error) return <ErrorScreen message={error} onRetry={() => void loadOverview()} onNavigate={onNavigate} />;
    return <LoadingScreen onNavigate={onNavigate} />;
  }
  if (view === 'dictionary') return <DictionaryPage theme={theme} token={token} onNavigate={onNavigate} onThemeRegenerated={onThemeRegenerated} />;
  if (view === 'assessment') return <AssessmentPage theme={theme} token={token} evidence={evidence} onEvidenceChanged={refreshEvidence} onNavigate={onNavigate} />;
  if (view === 'graduation') return <GraduationPage theme={theme} token={token} progress={progress} onProgressChanged={refreshProgress} onNavigate={onNavigate} />;
  if (view === 'lesson' || view === 'challenge') {
    if (lessonLoading || !lesson) return <LoadingScreen onNavigate={onNavigate} />;
    if (view === 'challenge') return <ChallengePage lesson={lesson} theme={theme} token={token} onProgressChanged={refreshProgress} onNavigate={onNavigate} />;
    return <LessonPage path={path} lesson={lesson} progress={progress} onSelectModule={selectLesson} onStartPractice={() => onNavigate('challenge')} onNavigate={onNavigate} />;
  }
  return <LearnDashboard theme={theme} path={path} progress={progress} proof={proof} evidence={evidence} onOpenLesson={openLesson} onNavigate={onNavigate} />;
}
