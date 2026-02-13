'use client'

import { useEffect, useState, useCallback } from 'react'
import { Loader2, AlertCircle, RefreshCw, Filter } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { JobCard } from '@/components/JobCard'
import { fetchJobs, type Job, type JobListResponse } from '@/lib/api'
import { cn } from '@/lib/utils'

const statusFilters = [
  { value: '', label: 'All' },
  { value: 'pending', label: 'Pending' },
  { value: 'processing', label: 'Processing' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
]

const modeFilters = [
  { value: '', label: 'All Modes' },
  { value: 'text-prompt', label: 'Text Prompt' },
  { value: 'multi-reference', label: 'Multi-Reference' },
  { value: 'meilisearch', label: 'MeiliSearch' },
]

const JOBS_PER_PAGE = 12

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [total, setTotal] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [statusFilter, setStatusFilter] = useState('')
  const [modeFilter, setModeFilter] = useState('')
  const [page, setPage] = useState(0)

  const loadJobs = useCallback(async () => {
    try {
      setIsLoading(true)
      setError(null)
      const data = await fetchJobs({
        status: statusFilter || undefined,
        mode: modeFilter || undefined,
        limit: JOBS_PER_PAGE,
        offset: page * JOBS_PER_PAGE,
      })
      setJobs(data.jobs)
      setTotal(data.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load jobs')
    } finally {
      setIsLoading(false)
    }
  }, [statusFilter, modeFilter, page])

  useEffect(() => {
    loadJobs()
  }, [loadJobs])

  // Reset page when filters change
  useEffect(() => {
    setPage(0)
  }, [statusFilter, modeFilter])

  const totalPages = Math.ceil(total / JOBS_PER_PAGE)

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Jobs</h1>
          <p className="text-muted-foreground">
            {total} total jobs
          </p>
        </div>
        <Button onClick={loadJobs} variant="outline" className="gap-2">
          <RefreshCw className={cn('h-4 w-4', isLoading && 'animate-spin')} />
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">Status:</span>
              <div className="flex gap-1">
                {statusFilters.map((filter) => (
                  <Button
                    key={filter.value}
                    variant={statusFilter === filter.value ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setStatusFilter(filter.value)}
                  >
                    {filter.label}
                  </Button>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">Mode:</span>
              <div className="flex gap-1">
                {modeFilters.map((filter) => (
                  <Button
                    key={filter.value}
                    variant={modeFilter === filter.value ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setModeFilter(filter.value)}
                  >
                    {filter.label}
                  </Button>
                ))}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Jobs Grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : error ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 gap-4">
            <AlertCircle className="h-12 w-12 text-destructive" />
            <p className="text-muted-foreground">{error}</p>
            <Button onClick={loadJobs}>Retry</Button>
          </CardContent>
        </Card>
      ) : jobs.length > 0 ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {jobs.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
              >
                Previous
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {page + 1} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
              >
                Next
              </Button>
            </div>
          )}
        </>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <p>No jobs found</p>
            {(statusFilter || modeFilter) && (
              <Button
                variant="link"
                onClick={() => {
                  setStatusFilter('')
                  setModeFilter('')
                }}
              >
                Clear filters
              </Button>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
