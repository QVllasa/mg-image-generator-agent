'use client'

import Link from 'next/link'
import { Clock, Image, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { formatDuration, formatRelativeTime } from '@/lib/utils'
import type { Job } from '@/lib/api'

interface JobCardProps {
  job: Job
}

const statusVariants: Record<string, { variant: 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning' | 'processing'; icon: React.ComponentType<{ className?: string }> }> = {
  pending: { variant: 'secondary', icon: Clock },
  processing: { variant: 'processing', icon: Loader2 },
  completed: { variant: 'success', icon: CheckCircle2 },
  failed: { variant: 'destructive', icon: AlertCircle },
}

const modeLabels: Record<string, string> = {
  'text-prompt': 'Text Prompt',
  'multi-reference': 'Multi-Reference',
  'meilisearch': 'MeiliSearch',
}

export function JobCard({ job }: JobCardProps) {
  const { variant, icon: StatusIcon } = statusVariants[job.status] || statusVariants.pending

  return (
    <Link href={`/jobs/${job.id}`}>
      <Card className="hover:bg-muted/50 transition-colors cursor-pointer">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base font-medium">
              {job.session_id}
            </CardTitle>
            <Badge variant={variant} className="flex items-center gap-1">
              <StatusIcon className={`h-3 w-3 ${job.status === 'processing' ? 'animate-spin' : ''}`} />
              {job.status}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Mode and Style */}
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Badge variant="outline" className="text-xs">
              {modeLabels[job.mode] || job.mode}
            </Badge>
            <span>{job.style}</span>
          </div>

          {/* Progress */}
          {job.status === 'processing' && (
            <div className="space-y-1">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>{job.current_stage}</span>
                <span>{job.progress_percent}%</span>
              </div>
              <Progress value={job.progress_percent} />
            </div>
          )}

          {/* Stats */}
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <div className="flex items-center gap-1">
              <Image className="h-3.5 w-3.5" />
              <span>{job.completed_images}/{job.total_images} images</span>
            </div>
            <span>{formatRelativeTime(job.created_at)}</span>
          </div>

          {/* Processing Time */}
          {job.processing_time_ms && (
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" />
              <span>{formatDuration(job.processing_time_ms)}</span>
            </div>
          )}

          {/* Error */}
          {job.error_message && (
            <div className="text-xs text-destructive truncate">
              {job.error_message}
            </div>
          )}
        </CardContent>
      </Card>
    </Link>
  )
}
