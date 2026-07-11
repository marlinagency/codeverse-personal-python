import type {
  BridgeChallenge,
  BridgeCheckResult,
  CompileResult,
  ExecutionRunResult,
  LearningModule,
  LearningPath,
  LearningProgress,
  MasteryReport,
  PracticeEvaluation,
  PracticeRunResult,
  ProgressProof,
  TargetLanguage,
  ThemeDictionary,
  ThemeDictionaryCatalog,
} from './types'

export const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : JSON.stringify(detail))
    this.status = status
    this.detail = detail
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { token?: string } = {},
): Promise<T> {
  const { token, headers, ...rest } = options
  const res = await fetch(`${BASE_URL}${path}`, {
    ...rest,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  })

  if (!res.ok) {
    let detail: unknown
    try {
      detail = await res.json()
    } catch {
      detail = await res.text()
    }
    throw new ApiError(res.status, (detail as { detail?: unknown })?.detail ?? detail)
  }

  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export async function fetchDevToken(): Promise<{ access_token: string; user_id: string }> {
  return request('/auth/token', { method: 'POST' })
}

export async function generateTheme(
  token: string,
  theme: string,
  outputLanguage?: string,
): Promise<ThemeDictionary> {
  return request('/themes/generate', {
    method: 'POST',
    token,
    body: JSON.stringify({ theme, output_language: outputLanguage ?? null }),
  })
}

export async function listThemes(token: string): Promise<ThemeDictionary[]> {
  return request('/themes', { token })
}

export async function compileSource(
  token: string,
  sourceContent: string,
  themeDictionaryId: string,
): Promise<CompileResult> {
  return request('/compile', {
    method: 'POST',
    token,
    body: JSON.stringify({
      source_content: sourceContent,
      theme_dictionary_id: themeDictionaryId,
    }),
  })
}

export async function executeSource(
  token: string,
  sourceContent: string,
  themeDictionaryId: string,
): Promise<ExecutionRunResult> {
  return request('/execute', {
    method: 'POST',
    token,
    body: JSON.stringify({
      source_content: sourceContent,
      theme_dictionary_id: themeDictionaryId,
    }),
  })
}

export function getLearningPath(token: string, themeId: string): Promise<LearningPath> {
  return request(`/learning/${themeId}/path`, { token })
}

export function getLearningProgress(token: string, themeId: string): Promise<LearningProgress> {
  return request(`/learning/${themeId}/progress`, { token })
}

export function getProgressProof(token: string, themeId: string): Promise<ProgressProof> {
  return request(`/learning/${themeId}/proof`, { token })
}

export function getLearningLesson(
  token: string,
  themeId: string,
  moduleId: string,
): Promise<LearningModule> {
  return request(`/learning/${themeId}/lessons/${moduleId}`, { token })
}

export function checkPracticeAnswer(
  token: string,
  themeId: string,
  taskId: string,
  answer: string,
): Promise<PracticeEvaluation> {
  return request(`/learning/${themeId}/practice/check`, {
    method: 'POST',
    token,
    body: JSON.stringify({ task_id: taskId, answer }),
  })
}

export function runPracticeCode(
  token: string,
  themeId: string,
  taskId: string,
  sourceContent: string,
): Promise<PracticeRunResult> {
  return request(`/learning/${themeId}/practice/run`, {
    method: 'POST',
    token,
    body: JSON.stringify({ task_id: taskId, source_content: sourceContent }),
  })
}

export function gradePractice(
  token: string,
  themeId: string,
  answers: Record<string, string>,
): Promise<MasteryReport> {
  return request(`/learning/${themeId}/practice/grade`, {
    method: 'POST',
    token,
    body: JSON.stringify({ answers }),
  })
}

export function getBridgeChallenge(token: string, themeId: string): Promise<BridgeChallenge> {
  return request(`/learning/${themeId}/bridge`, { token })
}

export function getThemeDictionaryCatalog(
  token: string,
  themeId: string,
): Promise<ThemeDictionaryCatalog> {
  return request(`/themes/${themeId}/dictionary`, { token })
}

export function checkBridge(
  token: string,
  themeId: string,
  sourceContent: string,
): Promise<BridgeCheckResult> {
  return request(`/learning/${themeId}/bridge/check`, {
    method: 'POST',
    token,
    body: JSON.stringify({ source_content: sourceContent }),
  })
}

export function buildCvlHeader(theme: string, language: TargetLanguage): string {
  return `@theme: ${theme}\n@language: ${language}\n@version: 1\n---\n`
}
