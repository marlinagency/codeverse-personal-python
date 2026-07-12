import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  BookOpen,
  Check,
  Code2,
  Expand,
  GraduationCap,
  Pause,
  Play,
  RefreshCw,
  Sparkles,
  Terminal,
  Volume2,
  VolumeX,
  Zap,
} from 'lucide-react';
import {
  executeSource,
  generateTheme,
  getBridgeChallenge,
  getLearningAssessment,
  getLearningPath,
  getThemeDictionaryCatalog,
  listThemes,
} from '../lib/api';
import type {
  BridgeChallenge,
  ExecutionRunResult,
  LearningEvidence,
  LearningPath,
  ThemeDictionary,
  ThemeDictionaryCatalog,
} from '../lib/types';

const FALLBACK_DEMO_PROMPT = 'I love chess and think in openings, positions, and strategy. Python conditions, loops, and functions still feel abstract, so teach them through a chess training workflow.';
const CACHE_KEY = 'codeverse-director-theme-id';
const PREFERRED_DEMO_THEMES = ['Chess', 'Car Mechanics', 'Counter-Strike 2', 'The Witcher 3', 'GTA San Andreas'];

interface DemoData {
  theme: ThemeDictionary;
  catalog: ThemeDictionaryCatalog;
  path: LearningPath;
  evidence: LearningEvidence;
  bridge: BridgeChallenge;
  source: string;
  execution: ExecutionRunResult;
  learnerPrompt: string;
}

interface DemoDirectorProps {
  token: string;
}

interface SceneDefinition {
  id: string;
  label: string;
  eyebrow: string;
  title: string;
  narration: string;
  duration: number;
}

const SCENES: SceneDefinition[] = [
  {
    id: 'opening',
    label: 'Problem',
    eyebrow: 'CODEVERSE / PERSONAL PYTHON',
    title: 'Python is logical. Its vocabulary is unfamiliar.',
    narration: 'Beginners often understand the idea, but struggle to express it using an unfamiliar programming vocabulary.',
    duration: 6500,
  },
  {
    id: 'prompt',
    label: 'Learner',
    eyebrow: '01 / UNDERSTAND THE LEARNER',
    title: 'Start with how the learner already thinks.',
    narration: 'CodeVerse begins with the learner, their interests, goals, and the Python concepts that feel difficult.',
    duration: 12500,
  },
  {
    id: 'profile',
    label: 'Profile',
    eyebrow: '02 / BUILD A LEARNING PROFILE',
    title: 'Turn free-form context into teaching decisions.',
    narration: 'The personalization brain separates the learner profile from the vocabulary and assigns useful motifs to each concept family.',
    duration: 8500,
  },
  {
    id: 'dictionary',
    label: 'Vocabulary',
    eyebrow: '03 / CONCEPT-AWARE VOCABULARY',
    title: 'Personal words. Canonical Python underneath.',
    narration: 'Every compact token is connected to a real Python concept, validated for meaning, brevity, uniqueness, and safety.',
    duration: 11500,
  },
  {
    id: 'runtime',
    label: 'Runtime',
    eyebrow: '04 / REAL EXECUTION',
    title: 'Not a visual simulation. Real runnable Python.',
    narration: 'The compiler resolves personal tokens, generates standard Python, and executes the result in a restricted runtime.',
    duration: 12500,
  },
  {
    id: 'learning',
    label: 'Curriculum',
    eyebrow: '05 / PROGRESSIVE LEARNING',
    title: 'The personal layer gradually disappears.',
    narration: 'The curriculum moves from personal syntax to bridge lessons, Python-forward practice, and finally standard Python.',
    duration: 11500,
  },
  {
    id: 'graduation',
    label: 'Graduation',
    eyebrow: '06 / REMOVE THE SCAFFOLD',
    title: 'Prove the learner can write real Python.',
    narration: 'The graduation challenge rejects personal tokens and passes only when standard Python produces the required behavior.',
    duration: 10500,
  },
  {
    id: 'evidence',
    label: 'Evidence',
    eyebrow: '07 / MEASURE LEARNING',
    title: 'Personalization must create measurable progress.',
    narration: 'A locked baseline and a final real Python assessment measure overall and concept-level learning gain.',
    duration: 9500,
  },
  {
    id: 'closing',
    label: 'CodeVerse',
    eyebrow: 'PERSONALIZED / RUNNABLE / MEASURABLE',
    title: 'Turn how you think into real Python.',
    narration: 'CodeVerse turns familiar ways of thinking into a temporary bridge toward authentic, independent Python skill.',
    duration: 8000,
  },
];

const token = (theme: ThemeDictionary, conceptId: string, fallback: string) => (
  theme.mappings[conceptId] || fallback
);

function learnerPromptFor(themeName: string): string {
  if (themeName.toLowerCase() === 'chess') return FALLBACK_DEMO_PROMPT;
  return `I care deeply about ${themeName} and naturally think through its roles, actions, and decisions. Python conditions, loops, and functions still feel abstract, so teach them through that world while keeping real Python visible.`;
}

function chooseDemoTheme(themes: ThemeDictionary[], cachedId: string | null): ThemeDictionary | null {
  const cached = themes.find((item) => item.id === cachedId);
  if (cached) return cached;
  for (const preferred of PREFERRED_DEMO_THEMES) {
    const match = themes.find((item) => item.theme_name.toLowerCase() === preferred.toLowerCase());
    if (match) return match;
  }
  return themes.find((item) => (
    item.theme_name.length <= 48
    && item.mappings.py_kw_def
    && item.mappings.py_kw_if
    && item.mappings.py_kw_for
    && item.mappings.py_fn_print
  )) || null;
}

function demoSource(theme: ThemeDictionary): string {
  const fn = token(theme, 'py_kw_def', 'def');
  const loop = token(theme, 'py_kw_for', 'for');
  const inside = token(theme, 'py_kw_in', 'in');
  const condition = token(theme, 'py_kw_if', 'if');
  const output = token(theme, 'py_fn_print', 'print');
  const result = token(theme, 'py_kw_return', 'return');
  const range = token(theme, 'py_fn_range', 'range');
  const truth = token(theme, 'py_kw_true', 'true');
  const label = JSON.stringify(`${theme.theme_name} step`);
  return `@theme: ${theme.theme_name}\n@language: python\n@version: 1\n---\n${fn} build_strategy(steps):\n    ${loop} step ${inside} steps:\n        ${condition} step > 2:\n            ${output}(${label}, step)\n    ${result} ${truth}\n\nbuild_strategy(${range}(1, 5))\n`;
}

function formatSeconds(milliseconds: number): string {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}

function CodeBlock({ children, tone = 'python' }: { children: string; tone?: 'python' | 'personal' | 'terminal' }) {
  return <pre className={`director-code ${tone}`}><code>{children}</code></pre>;
}

export function DemoDirector({ token: authToken }: DemoDirectorProps) {
  const [data, setData] = useState<DemoData | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [prepareStep, setPrepareStep] = useState('Ready for preflight');
  const [error, setError] = useState('');
  const [sceneIndex, setSceneIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [sceneElapsed, setSceneElapsed] = useState(0);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [speed, setSpeed] = useState(1);
  const spokenSceneRef = useRef(-1);
  const scene = SCENES[sceneIndex];

  const totalDuration = useMemo(() => SCENES.reduce((sum, item) => sum + item.duration, 0), []);
  const completedDuration = useMemo(
    () => SCENES.slice(0, sceneIndex).reduce((sum, item) => sum + item.duration, 0) + sceneElapsed,
    [sceneElapsed, sceneIndex],
  );
  const overallProgress = Math.min(100, (completedDuration / totalDuration) * 100);

  const prepare = useCallback(async () => {
    setPreparing(true);
    setError('');
    try {
      setPrepareStep('Finding a clean demo workspace...');
      const themes = await listThemes(authToken);
      const cachedId = window.localStorage.getItem(CACHE_KEY);
      let theme = chooseDemoTheme(themes, cachedId);

      if (!theme) {
        setPrepareStep('Generating the Personal Python vocabulary with the live brain...');
        theme = await generateTheme(authToken, FALLBACK_DEMO_PROMPT, 'en');
      }
      window.localStorage.setItem(CACHE_KEY, theme.id);

      setPrepareStep('Verifying dictionary quality and learning path...');
      const [catalog, path, evidence, bridge] = await Promise.all([
        getThemeDictionaryCatalog(authToken, theme.id),
        getLearningPath(authToken, theme.id),
        getLearningAssessment(authToken, theme.id),
        getBridgeChallenge(authToken, theme.id),
      ]);

      setPrepareStep('Compiling and running the presentation program...');
      const source = demoSource(theme);
      const execution = await executeSource(authToken, source, theme.id);
      if (execution.status !== 'success') {
        throw new Error(execution.error_message_themed || execution.stderr_raw || 'The live runtime check failed.');
      }

      setData({ theme, catalog, path, evidence, bridge, source, execution, learnerPrompt: learnerPromptFor(theme.theme_name) });
      setPrepareStep('Preflight passed. Live APIs and Python runtime are ready.');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Demo preflight failed.');
      setPrepareStep('Preflight needs attention');
    } finally {
      setPreparing(false);
    }
  }, [authToken]);

  const reset = useCallback(() => {
    setPlaying(false);
    setSceneIndex(0);
    setSceneElapsed(0);
    spokenSceneRef.current = -1;
    window.speechSynthesis?.cancel();
  }, []);

  const start = () => {
    if (!data) return;
    if (sceneIndex === SCENES.length - 1 && sceneElapsed >= scene.duration - 100) reset();
    setPlaying(true);
  };

  const moveScene = useCallback((direction: number) => {
    setPlaying(false);
    setSceneIndex((current) => Math.max(0, Math.min(SCENES.length - 1, current + direction)));
    setSceneElapsed(0);
    spokenSceneRef.current = -1;
    window.speechSynthesis?.cancel();
  }, []);

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setSceneElapsed((current) => Math.min(scene.duration, current + 50 * speed));
    }, 50);
    return () => window.clearInterval(timer);
  }, [playing, scene.duration, speed]);

  useEffect(() => {
    if (!playing || sceneElapsed < scene.duration) return;
    const transition = window.setTimeout(() => {
      if (sceneIndex < SCENES.length - 1) {
        setSceneIndex(sceneIndex + 1);
        setSceneElapsed(0);
        spokenSceneRef.current = -1;
      } else {
        setPlaying(false);
      }
    }, 0);
    return () => window.clearTimeout(transition);
  }, [playing, scene.duration, sceneElapsed, sceneIndex]);

  useEffect(() => {
    if (!playing || !voiceEnabled || spokenSceneRef.current === sceneIndex || !('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(scene.narration);
    utterance.lang = 'en-US';
    utterance.rate = 0.95 * speed;
    utterance.pitch = 0.95;
    window.speechSynthesis.speak(utterance);
    spokenSceneRef.current = sceneIndex;
  }, [playing, scene.narration, sceneIndex, speed, voiceEnabled]);

  useEffect(() => () => window.speechSynthesis?.cancel(), []);

  const promptText = data?.learnerPrompt || FALLBACK_DEMO_PROMPT;
  const typedPrompt = promptText.slice(
    0,
    scene.id === 'prompt'
      ? Math.round(Math.min(1, sceneElapsed / (scene.duration * 0.72)) * promptText.length)
      : promptText.length,
  );

  const requestFullscreen = async () => {
    if (!document.fullscreenElement) await document.documentElement.requestFullscreen();
    else await document.exitFullscreen();
  };

  return (
    <div className="director-shell">
      <header className="director-header">
        <div className="director-brand"><strong>CODEVERSE</strong><span>DEMO DIRECTOR</span></div>
        <div className="director-scene-name"><span>{String(sceneIndex + 1).padStart(2, '0')}</span><strong>{scene.label}</strong></div>
        <div className="director-clock"><span>LIVE PRODUCT STORY</span><strong>{formatSeconds(completedDuration)} / {formatSeconds(totalDuration)}</strong></div>
      </header>

      <div className="director-progress" aria-label="Presentation progress"><i style={{ width: `${overallProgress}%` }} /></div>

      {!data ? (
        <main className="director-stage director-preflight">
          <section>
            <span className="director-kicker"><Sparkles /> RECORDING WORKSPACE</span>
            <h1>Prepare one clean, repeatable product story.</h1>
            <p>Preflight loads a dedicated Personal Python dictionary, verifies the learning APIs, and executes the exact program that will appear in the presentation.</p>
            <div className={`director-preflight-status ${error ? 'error' : ''}`}>
              <span>{preparing ? <RefreshCw className="spin" /> : error ? <Zap /> : <Check />}</span>
              <div><strong>{prepareStep}</strong><small>{error || 'No browser history or private learner data will appear in the recording.'}</small></div>
            </div>
            <button className="director-primary" onClick={() => void prepare()} disabled={preparing}>{preparing ? 'Running preflight...' : error ? 'Retry preflight' : 'Prepare live demo'} <ArrowRight /></button>
          </section>
          <aside>
            <div className="director-runbook"><span>01</span><p>Live vocabulary brain</p><span>02</span><p>Compiler and runtime</p><span>03</span><p>Learning evidence APIs</p><span>04</span><p>Recording-safe workspace</p></div>
          </aside>
        </main>
      ) : (
        <main className={`director-stage director-scene scene-${scene.id}`}>
          <div className="director-scene-copy">
            <span>{scene.eyebrow}</span>
            <h1>{scene.title}</h1>
          </div>
          <SceneContent sceneId={scene.id} data={data} typedPrompt={typedPrompt} elapsed={sceneElapsed} duration={scene.duration} />
        </main>
      )}

      <section className="director-caption" aria-live="polite">
        <span><Volume2 /></span><p>{scene.narration}</p><strong>{scene.label.toUpperCase()}</strong>
      </section>

      <footer className="director-controls">
        <div className="director-scene-dots">{SCENES.map((item, index) => <button key={item.id} className={index === sceneIndex ? 'active' : index < sceneIndex ? 'done' : ''} onClick={() => { setPlaying(false); setSceneIndex(index); setSceneElapsed(0); }} title={item.label}><span>{index < sceneIndex ? <Check /> : index + 1}</span><small>{item.label}</small></button>)}</div>
        <div className="director-transport">
          <button onClick={() => moveScene(-1)} disabled={sceneIndex === 0} title="Previous scene"><ArrowLeft /></button>
          <button className="director-play" onClick={() => playing ? setPlaying(false) : start()} disabled={!data} title={playing ? 'Pause presentation' : 'Start presentation'}>{playing ? <Pause /> : <Play />}</button>
          <button onClick={() => moveScene(1)} disabled={sceneIndex === SCENES.length - 1} title="Next scene"><ArrowRight /></button>
        </div>
        <div className="director-tools">
          <button onClick={() => setVoiceEnabled((value) => !value)} className={voiceEnabled ? 'active' : ''} title="Toggle narration">{voiceEnabled ? <Volume2 /> : <VolumeX />}</button>
          <button onClick={() => setSpeed((value) => value === 1 ? 1.25 : value === 1.25 ? 0.75 : 1)} className="director-speed" title="Playback speed">{speed}x</button>
          <button onClick={reset} title="Restart presentation"><RefreshCw /></button>
          <button onClick={() => void requestFullscreen()} title="Fullscreen"><Expand /></button>
        </div>
      </footer>
    </div>
  );
}

function SceneContent({ sceneId, data, typedPrompt, elapsed, duration }: { sceneId: string; data: DemoData; typedPrompt: string; elapsed: number; duration: number }) {
  const reveal = Math.min(1, elapsed / Math.max(duration * 0.55, 1));
  const coreEntries = data.catalog.entries
    .filter((entry) => ['py_kw_def', 'py_kw_if', 'py_kw_for', 'py_kw_return', 'py_fn_print', 'py_fn_range'].includes(entry.concept_id))
    .slice(0, 6);
  const generated = data.execution.generated_code || '';

  if (sceneId === 'opening') return (
    <section className="director-opening-visual">
      <div className="director-python-cloud"><code>def</code><code>for</code><code>range()</code><code>return</code><code>if</code><code>print()</code></div>
      <div className="director-opening-line"><span /><strong>THE GAP IS VOCABULARY</strong><span /></div>
    </section>
  );

  if (sceneId === 'prompt') return (
    <section className="director-prompt-visual">
      <div className="director-prompt-box"><span>&gt;</span><p>{typedPrompt}<i /></p></div>
      <div className="director-prompt-tags"><span>INTEREST / {data.theme.theme_name.toUpperCase()}</span><span>CONTEXT / PERSONAL MENTAL MODEL</span><span>FRICTION / CONDITIONS · LOOPS · FUNCTIONS</span></div>
    </section>
  );

  if (sceneId === 'profile') return (
    <section className="director-profile-visual">
      <div className="director-profile-flow"><div><small>LEARNER INPUT</small><strong>Free-form context</strong><p>Goals, interests, experience, and pain points</p></div><i><ArrowRight /></i><div><small>PERSONALIZATION BRAIN</small><strong>Structured learning profile</strong><p>Concept roles, motifs, teaching priorities</p></div><i><ArrowRight /></i><div><small>QUALITY GATES</small><strong>Compact and teachable</strong><p>Meaning, brevity, uniqueness, Python validity</p></div></div>
      <div className="director-profile-proof"><span><Check /> English tokens</span><span><Check /> Two words maximum</span><span><Check /> Concept-aware mapping</span><span><Check /> Canonical Python visible</span></div>
    </section>
  );

  if (sceneId === 'dictionary') return (
    <section className="director-dictionary-visual">
      <header><span>YOUR TOKEN</span><span>REAL PYTHON</span><span>ROLE</span></header>
      {coreEntries.map((entry, index) => <div key={entry.concept_id} style={{ '--delay': `${index * 90}ms` } as React.CSSProperties}><code>{entry.personal_token}</code><ArrowRight /><code>{entry.python_name}</code><span>{entry.category.replaceAll('_', ' ')}</span></div>)}
      <footer><strong>{data.catalog.total}</strong><span>Python concepts mapped</span><strong>{data.catalog.quality.grade}</strong><span>dictionary quality</span><strong>{data.catalog.quality.max_token_parts}</strong><span>maximum token parts</span></footer>
    </section>
  );

  if (sceneId === 'runtime') return (
    <section className="director-runtime-visual">
      <div><header><Code2 /><strong>personal_python.cvl</strong><span>PERSONAL LAYER</span></header><CodeBlock tone="personal">{data.source}</CodeBlock></div>
      <i className="director-runtime-arrow"><ArrowRight /></i>
      <div><header><Terminal /><strong>generated.py</strong><span>STANDARD PYTHON</span></header><CodeBlock>{generated}</CodeBlock></div>
      <aside><small>LIVE RUNTIME OUTPUT</small><CodeBlock tone="terminal">{data.execution.stdout || '(no output)'}</CodeBlock><span><Check /> EXECUTION STATUS / {data.execution.status.toUpperCase()}</span></aside>
    </section>
  );

  if (sceneId === 'learning') return (
    <section className="director-learning-visual">
      <div className="director-learning-stages"><span><strong>100%</strong><small>PERSONAL</small></span><i /><span><strong>70%</strong><small>BRIDGE</small></span><i /><span><strong>35%</strong><small>PYTHON FORWARD</small></span><i /><span><strong>0%</strong><small>REAL PYTHON</small></span></div>
      <div className="director-module-ribbon">{data.path.modules.slice(0, 8).map((module, index) => <div key={module.module_id} className={index < Math.ceil(reveal * 8) ? 'visible' : ''}><span>{String(module.order).padStart(2, '0')}</span><strong>{module.title}</strong><small>{module.scaffold_stage.replaceAll('_', ' ')}</small></div>)}</div>
      <footer><BookOpen /><span><strong>{data.path.modules.length} progressive modules</strong><small>Practice, runtime checks, and mastery records are verified by the learning API.</small></span></footer>
    </section>
  );

  if (sceneId === 'graduation') return (
    <section className="director-graduation-visual">
      <div><header><strong>PERSONAL REFERENCE</strong><span>TRANSLATE THIS</span></header><CodeBlock tone="personal">{data.bridge.personal_reference}</CodeBlock></div>
      <i><ArrowRight /></i>
      <div><header><strong>GRADUATION CONTRACT</strong><span>BEHAVIORAL PROOF</span></header><ul><li><Check /> Runs as standard Python</li><li><Check /> Prints the required output</li><li><Check /> Contains zero personal tokens</li></ul><p><small>EXPECTED STDOUT</small><code>{data.bridge.expected_stdout}</code></p></div>
      <footer><GraduationCap /><strong>THE SCAFFOLD IS TEMPORARY</strong><span>The destination is independent Python skill.</span></footer>
    </section>
  );

  if (sceneId === 'evidence') return (
    <section className="director-evidence-visual">
      <div className="director-score"><small>BASELINE</small><strong>{data.evidence.pre_score === null ? 'NOT TAKEN' : `${data.evidence.pre_score}%`}</strong><span>Locked first attempt</span></div><i><ArrowRight /></i><div className="director-score final"><small>FINAL</small><strong>{data.evidence.post_score === null ? 'NOT TAKEN' : `${data.evidence.post_score}%`}</strong><span>Real Python assessment</span></div><div className="director-gain"><BarChart3 /><small>LEARNING GAIN</small><strong>{data.evidence.gain === null ? 'MEASURED AFTER COURSE' : `${data.evidence.gain >= 0 ? '+' : ''}${data.evidence.gain} pts`}</strong></div>
      <footer>{data.evidence.questions.map((question) => <span key={question.id}>{question.concept}</span>)}</footer>
    </section>
  );

  return (
    <section className="director-closing-visual">
      <div className="director-mark">CV</div><strong>CODEVERSE</strong><p>Turn how you think into a bridge toward how Python works.</p><div><span>PERSONALIZED</span><i /><span>RUNNABLE</span><i /><span>MEASURABLE</span></div>
    </section>
  );
}
