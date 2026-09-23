/**
 * API Client for Room Stager Backend
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export interface Job {
  id: string
  session_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  mode: 'text-prompt' | 'multi-reference' | 'meilisearch'
  style: string
  room_type?: string
  color_preferences?: string[]
  budget_range?: { min: number; max: number }
  furniture_types?: string[]
  total_images: number
  completed_images: number
  current_stage?: string
  progress_percent: number
  created_at: string
  started_at?: string
  completed_at?: string
  processing_time_ms?: number
  error_message?: string
  images?: JobImage[]
  selected_products?: SelectedProduct[]
}

export interface JobImage {
  id: string
  original_filename: string
  image_index: number
  original_image_url?: string
  staged_image_url?: string
  staged_image_with_markers_url?: string
  room_analysis?: Record<string, unknown>
  product_hotspots?: ProductHotspot[]
  furniture_added?: string[]
  status: string
  processing_time_ms?: number
  error_message?: string
}

export interface ProductHotspot {
  product_name: string
  product_id?: string
  x: number
  y: number
  width: number
  height: number
  confidence: number
  hotspot_x: number
  hotspot_y: number
}

export interface SelectedProduct {
  id: string
  product_id: string
  ean?: string
  name: string
  furniture_type: string
  price?: number
  image_url?: string
  images?: string[]
  selection_reason?: string
}

export interface JobListResponse {
  jobs: Job[]
  total: number
  limit: number
  offset: number
}

export interface JobStatistics {
  total_jobs: number
  pending_jobs: number
  processing_jobs: number
  completed_jobs: number
  failed_jobs: number
  avg_processing_time_ms: number
  jobs_last_24h: number
  jobs_last_7d: number
  jobs_by_mode: Record<string, number>
}

export interface JobEvent {
  id: number
  job_id: string
  event_type: string
  event_data?: Record<string, unknown>
  created_at: string
}

// ═══════════════════════════════════════════════════════════════════════════════
// API FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export async function fetchJobs(params?: {
  status?: string
  mode?: string
  limit?: number
  offset?: number
}): Promise<JobListResponse> {
  const searchParams = new URLSearchParams()
  if (params?.status) searchParams.set('status', params.status)
  if (params?.mode) searchParams.set('mode', params.mode)
  if (params?.limit) searchParams.set('limit', String(params.limit))
  if (params?.offset) searchParams.set('offset', String(params.offset))

  const response = await fetch(`${API_URL}/api/v1/jobs?${searchParams}`)
  if (!response.ok) {
    throw new Error(`Failed to fetch jobs: ${response.statusText}`)
  }
  return response.json()
}

export async function fetchJob(jobId: string): Promise<Job> {
  const response = await fetch(`${API_URL}/api/v1/jobs/${jobId}`)
  if (!response.ok) {
    throw new Error(`Failed to fetch job: ${response.statusText}`)
  }
  return response.json()
}

export async function fetchJobStatistics(): Promise<JobStatistics> {
  const response = await fetch(`${API_URL}/api/v1/jobs/stats/overview`)
  if (!response.ok) {
    throw new Error(`Failed to fetch statistics: ${response.statusText}`)
  }
  return response.json()
}

export function subscribeToJobEvents(
  jobId: string,
  onEvent: (event: JobEvent) => void,
  onError?: (error: Error) => void
): () => void {
  const eventSource = new EventSource(`${API_URL}/api/v1/jobs/${jobId}/events`)

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      onEvent(data)
    } catch (e) {
      console.error('Failed to parse event:', e)
    }
  }

  eventSource.onerror = (error) => {
    console.error('SSE error:', error)
    onError?.(new Error('Connection lost'))
    eventSource.close()
  }

  // Return cleanup function
  return () => {
    eventSource.close()
  }
}

export async function createJob(request: {
  images: { data: string; filename: string }[]
  style?: string
  room_type?: string
  furniture_types?: string[]
  product_images?: { name: string; data: string; ean?: string }[]
  color_preferences?: string[]
  budget_range?: { min: number; max: number }
  products_per_type?: number
}): Promise<{ id: string; session_id: string; status: string }> {
  const response = await fetch(`${API_URL}/api/v1/jobs`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || 'Failed to create job')
  }

  return response.json()
}
