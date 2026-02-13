'use client'

import { useEffect, useState } from 'react'
import { Loader2, CheckCircle2, AlertCircle, Radio } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { useJobEvents } from '@/lib/hooks/useJobEvents'
import { fetchJob, type Job, type JobEvent } from '@/lib/api'
import { formatDuration } from '@/lib/utils'

interface JobProgressProps {
  jobId: string
  initialJob?: Job
}

const stageLabels: Record<string, string> = {
  receive: 'Receiving images',
  analyze: 'Analyzing room',
  build_filter: 'Building filters',
  fetch_products: 'Fetching products',
  select_products: 'Selecting products',
  generate: 'Generating image',
  validate: 'Validating result',
  finalize: 'Finalizing',
  done: 'Complete',
}

export function JobProgress({ jobId, initialJob }: JobProgressProps) {
  const [job, setJob] = useState<Job | null>(initialJob || null)
  const { events, isConnected } = useJobEvents(
    job?.status === 'processing' || job?.status === 'pending' ? jobId : null
  )

  // Poll for job updates when receiving events
  useEffect(() => {
    if (events.length > 0) {
      fetchJob(jobId).then(setJob).catch(console.error)
    }
  }, [events, jobId])

  // Initial fetch
  useEffect(() => {
    if (!initialJob) {
      fetchJob(jobId).then(setJob).catch(console.error)
    }
  }, [jobId, initialJob])

  if (!job) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    )
  }

  const isActive = job.status === 'processing' || job.status === 'pending'

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">Progress</CardTitle>
          <div className="flex items-center gap-2">
            {isConnected && (
              <Badge variant="outline" className="text-xs flex items-center gap-1">
                <Radio className="h-3 w-3 text-green-500 animate-pulse" />
                Live
              </Badge>
            )}
            {job.status === 'completed' && (
              <Badge variant="success" className="flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" />
                Completed
              </Badge>
            )}
            {job.status === 'failed' && (
              <Badge variant="destructive" className="flex items-center gap-1">
                <AlertCircle className="h-3 w-3" />
                Failed
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Progress Bar */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">
              {stageLabels[job.current_stage || 'receive'] || job.current_stage}
            </span>
            <span className="font-medium">{job.progress_percent}%</span>
          </div>
          <Progress value={job.progress_percent} className="h-2" />
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-muted-foreground">Images</p>
            <p className="font-medium">{job.completed_images} / {job.total_images}</p>
          </div>
          {job.processing_time_ms && (
            <div>
              <p className="text-muted-foreground">Processing Time</p>
              <p className="font-medium">{formatDuration(job.processing_time_ms)}</p>
            </div>
          )}
        </div>

        {/* Event Log */}
        {isActive && events.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm font-medium">Recent Events</p>
            <div className="max-h-32 overflow-y-auto space-y-1">
              {events.slice(-5).map((event, i) => (
                <div
                  key={event.id || i}
                  className="text-xs text-muted-foreground flex items-center gap-2"
                >
                  {event.event_type === 'completed' ? (
                    <CheckCircle2 className="h-3 w-3 text-green-500" />
                  ) : event.event_type === 'failed' ? (
                    <AlertCircle className="h-3 w-3 text-destructive" />
                  ) : (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  )}
                  <span>{stageLabels[event.event_type] || event.event_type}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Error Message */}
        {job.error_message && (
          <div className="p-3 bg-destructive/10 text-destructive text-sm rounded-lg">
            {job.error_message}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
