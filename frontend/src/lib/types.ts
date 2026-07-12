export type TargetLanguage = 'python' | 'sql'

export interface ThemeDictionary {
  id: string
  theme_name: string
  mappings: Record<string, string>
  rationale: Record<string, string> | null
  llm_provider: string
  llm_model: string
  version: number
  is_active: boolean
  created_at: string
}

export interface Diagnostic {
  message: string
  themed_message: string | null
  line: number
  col: number
  severity: 'error' | 'warning'
  stage: string
  personal_source: string | null
  python_source: string | null
  personal_token: string | null
  python_token: string | null
}

export interface TokenReplacement {
  personal_token: string
  python_token: string
  col: number
}

export interface TranslationTraceLine {
  line: number
  personal_source: string
  python_source: string
  replacements: TokenReplacement[]
}

export interface CompileResult {
  success: boolean
  generated_code: string | null
  target_language: TargetLanguage | null
  warnings: Diagnostic[]
  error: Diagnostic | null
  translation_trace: TranslationTraceLine[]
}

export interface ExecutionRunResult {
  id: string
  status:
    | 'success'
    | 'runtime_error'
    | 'parse_error'
    | 'codegen_error'
    | 'timeout'
    | 'sandbox_error'
  stdout: string | null
  stderr_raw: string | null
  error_message_themed: string | null
  duration_ms: number | null
  created_at: string
  generated_code: string | null
  diagnostic_error: Diagnostic | null
  translation_trace: TranslationTraceLine[]
}

/** Concept keys mirrored from codeverse_core.concepts.UniversalConcept — kept
 * in sync manually since there is no shared codegen between backend/frontend
 * for Phase 1+2. */
export const UNIVERSAL_CONCEPTS = [
  'function_def',
  'return',
  'if',
  'elif',
  'else',
  'for',
  'in',
  'while',
  'break',
  'continue',
  'class_def',
  'import',
  'try',
  'except',
  'finally',
  'and',
  'or',
  'not',
  'true',
  'false',
  'none',
  'print',
  'range',
  'len',
  'list_append',
  'list_remove',
  'contains',
  'dict_get',
  'dict_set',
  'dict_keys',
  'dict_values',
  'dict_delete',
] as const

export type ConceptKey = (typeof UNIVERSAL_CONCEPTS)[number]

export interface LearnerDiagnosis {
  level: string
  learner_summary: string
  interests: string[]
  goals: string[]
  pain_points: string[]
  preferred_examples: string[]
  recommended_start: string
  confidence_score: number
  evidence: string[]
}

export interface LearningConcept {
  concept_id: string
  python_concept: string
  personal_token: string
  title: string
  mental_model: string
  real_python: string
}

export interface PracticeTask {
  id: string
  kind: string
  concept_id: string
  prompt: string
  choices: string[]
  starter_source: string | null
  hint: string
  explanation: string
  syntax_mode: 'personal' | 'python'
}

export interface LessonSection {
  section_id: string
  title: string
  objective: string
  explanation: string
  key_points: string[]
  personal_example: string
  real_python_example: string
  expected_output: string
}

export interface LearningModule {
  module_id: string
  title: string
  goal: string
  why_it_matters: string
  concepts: LearningConcept[]
  bridge_steps: string[]
  lesson_steps: string[]
  lesson_sections: LessonSection[]
  misconception_checks: string[]
  success_criteria: string[]
  source_content: string
  real_python_preview: string
  expected_stdout: string
  practice_tasks: PracticeTask[]
  order: number
  scaffold_stage: 'personal' | 'bridge' | 'python_forward' | 'real_python'
  personal_support_percent: number
  practice_syntax: 'personal' | 'python'
  generated_code: string | null
  stdout: string | null
  compile_error: string | null
}

export interface LearningPath {
  theme_dictionary_id: string
  title: string
  diagnosis: LearnerDiagnosis
  modules: LearningModule[]
  proof_points: string[]
}

export interface ModuleProgress {
  module_id: string
  best_score: number
  passed: boolean
}

export interface LearningProgress {
  theme_dictionary_id: string
  completed_count: number
  modules: ModuleProgress[]
}

export interface AssessmentQuestion {
  id: string
  concept: string
  prompt: string
  choices: string[]
}

export interface AssessmentConceptScore {
  concept: string
  correct: number
  total: number
  score: number
}

export interface AssessmentResult {
  phase: 'pre' | 'post'
  score: number
  correct: number
  total: number
  concept_scores: AssessmentConceptScore[]
  feedback: string[]
  baseline_locked: boolean
}

export interface LearningEvidence {
  theme_dictionary_id: string
  questions: AssessmentQuestion[]
  pre_score: number | null
  post_score: number | null
  gain: number | null
  concept_gain: Record<string, number>
  readiness: 'take_baseline' | 'learning_in_progress' | 'ready_for_posttest' | 'evidence_ready'
}

export interface ProgressProof {
  theme_dictionary_id: string
  headline: string
  total_modules: number
  total_concepts: number
  runnable_programs: number
  bridge_modes: string[]
  concept_coverage: Record<string, string[]>
}

export interface PracticeEvaluation {
  correct: boolean
  score: number
  feedback: string
  expected_answer: string
  next_step: string
}

export interface PracticeRunResult {
  correct: boolean
  status: string
  stdout: string | null
  stderr: string | null
  expected_stdout: string
  feedback: string
  compile_error: string | null
}

export interface MasteryModule {
  module_id: string
  score: number
  passed: boolean
  correct: number
  total: number
  feedback: string
}

export interface MasteryReport {
  overall_score: number
  passed: boolean
  modules: MasteryModule[]
  strengths: string[]
  next_steps: string[]
}

export interface BridgeChallenge {
  theme_dictionary_id: string
  prompt: string
  personal_reference: string
  expected_stdout: string
  real_keywords: string[]
}

export interface BridgeCheckResult {
  passed: boolean
  status: 'graduated' | 'used_personal_tokens' | 'wrong_output' | 'runtime_error'
  stdout: string | null
  stderr: string | null
  expected_stdout: string
  used_personal_tokens: string[]
  feedback: string
}

export interface ThemeDictionaryEntry {
  concept_id: string
  personal_token: string
  python_name: string
  real_syntax: string
  category: string
  tier: 'core' | 'builtin' | 'method' | 'type' | 'exception' | 'library' | string
  description: string
  rationale: string | null
  sandbox_safe: boolean
}

export interface ThemeDictionaryCatalog {
  theme_dictionary_id: string
  theme_name: string
  total: number
  category_counts: Record<string, number>
  tier_counts: Record<string, number>
  quality: ThemeDictionaryQuality
  entries: ThemeDictionaryEntry[]
}

export interface ThemeDictionaryQuality {
  overall_score: number
  grade: 'A' | 'B' | 'C' | 'D' | 'F'
  brevity_score: number
  uniqueness_score: number
  diversity_score: number
  semantic_score: number
  max_token_length: number
  max_token_parts: number
  dominant_root_share: number
  upgrade_recommended: boolean
  issues: string[]
}
