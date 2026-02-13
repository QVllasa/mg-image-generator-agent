'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import {
  Image,
  Clock,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ArrowRight,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { JobCard } from '@/components/JobCard'
import { fetchJobStatistics, fetchJobs, type JobStatistics, type Job } from '@/lib/api'
import { formatDuration } from '@/lib/utils'

export default function DashboardPage() {
  const [stats, setStats] = useState<JobStatistics | null>(null)
  const [recentJobs, setRecentJobs] = useState<Job[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function loadData() {
      try {
        setIsLoading(true)
        const [statsData, jobsData] = await Promise.all([
          fetchJobStatistics(),
          fetchJobs({ limit: 6 }),
        ])
        setStats(statsData)
        setRecentJobs(jobsData.jobs)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load data')
      } finally {
        setIsLoading(false)
      }
    }
    loadData()
  }, [])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <AlertCircle className="h-12 w-12 text-destructive" />
        <p className="text-lg text-muted-foreground">{error}</p>
        <Button onClick={() => window.location.reload()}>Retry</Button>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground">Image generation job monitoring</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Jobs
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_jobs || 0}</div>
            <p className="text-xs text-muted-foreground">
              {stats?.jobs_last_24h || 0} in last 24h
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Loader2 className="h-4 w-4 text-blue-500" />
              Processing
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.processing_jobs || 0}</div>
            <p className="text-xs text-muted-foreground">
              {stats?.pending_jobs || 0} pending
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-green-500" />
              Completed
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.completed_jobs || 0}</div>
            <p className="text-xs text-muted-foreground">
              {stats?.failed_jobs || 0} failed
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Clock className="h-4 w-4" />
              Avg. Time
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {stats?.avg_processing_time_ms
                ? formatDuration(stats.avg_processing_time_ms)
                : '-'}
            </div>
            <p className="text-xs text-muted-foreground">per job</p>
          </CardContent>
        </Card>
      </div>

      {/* Jobs by Mode */}
      {stats?.jobs_by_mode && Object.keys(stats.jobs_by_mode).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Jobs by Mode</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-6">
              {Object.entries(stats.jobs_by_mode).map(([mode, count]) => (
                <div key={mode} className="text-center">
                  <div className="text-2xl font-bold">{count}</div>
                  <div className="text-sm text-muted-foreground capitalize">
                    {mode.replace('-', ' ')}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recent Jobs */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold">Recent Jobs</h2>
          <Link href="/jobs">
            <Button variant="ghost" className="gap-1">
              View all
              <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
        </div>

        {recentJobs.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {recentJobs.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Image className="h-12 w-12 mb-4" />
              <p>No jobs yet</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
