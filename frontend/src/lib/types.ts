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
}

export interface CompileResult {
  success: boolean
  generated_code: string | null
  target_language: TargetLanguage | null
  warnings: Diagnostic[]
  error: Diagnostic | null
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
}

export interface LearningModule {
  module_id: string
  title: string
  goal: string
  why_it_matters: string
  concepts: LearningConcept[]
  bridge_steps: string[]
  lesson_steps: string[]
  misconception_checks: string[]
  success_criteria: string[]
  source_content: string
  real_python_preview: string
  expected_stdout: string
  practice_tasks: PracticeTask[]
  order: number
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
