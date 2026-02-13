'use client'

import { useEffect, useState } from 'react'
import { Loader2, AlertCircle, TrendingUp, Clock, CheckCircle2, XCircle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { fetchJobStatistics, fetchJobs, type JobStatistics, type Job } from '@/lib/api'
import { formatDuration } from '@/lib/utils'

export default function AnalyticsPage() {
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
          fetchJobs({ limit: 100 }),
        ])
        setStats(statsData)
        setRecentJobs(jobsData.jobs)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load analytics')
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

  // Calculate success rate
  const totalCompleted = stats?.completed_jobs || 0
  const totalFailed = stats?.failed_jobs || 0
  const successRate = totalCompleted + totalFailed > 0
    ? ((totalCompleted / (totalCompleted + totalFailed)) * 100).toFixed(1)
    : '0'

  // Group jobs by day for chart
  const jobsByDay = recentJobs.reduce((acc, job) => {
    const day = new Date(job.created_at).toLocaleDateString()
    acc[day] = (acc[day] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  // Calculate average processing time by mode
  const timeByMode = recentJobs.reduce((acc, job) => {
    if (job.processing_time_ms && job.status === 'completed') {
      if (!acc[job.mode]) {
        acc[job.mode] = { total: 0, count: 0 }
      }
      acc[job.mode].total += job.processing_time_ms
      acc[job.mode].count += 1
    }
    return acc
  }, {} as Record<string, { total: number; count: number }>)

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Analytics</h1>
        <p className="text-muted-foreground">Performance metrics and insights</p>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <TrendingUp className="h-4 w-4" />
              Success Rate
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{successRate}%</div>
            <p className="text-xs text-muted-foreground">
              {totalCompleted} completed, {totalFailed} failed
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Clock className="h-4 w-4" />
              Avg. Processing Time
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {stats?.avg_processing_time_ms
                ? formatDuration(stats.avg_processing_time_ms)
                : '-'}
            </div>
            <p className="text-xs text-muted-foreground">per job</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Last 24 Hours
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{stats?.jobs_last_24h || 0}</div>
            <p className="text-xs text-muted-foreground">jobs processed</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Last 7 Days
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{stats?.jobs_last_7d || 0}</div>
            <p className="text-xs text-muted-foreground">jobs processed</p>
          </CardContent>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Jobs by Mode */}
        <Card>
          <CardHeader>
            <CardTitle>Jobs by Mode</CardTitle>
          </CardHeader>
          <CardContent>
            {stats?.jobs_by_mode && Object.keys(stats.jobs_by_mode).length > 0 ? (
              <div className="space-y-4">
                {Object.entries(stats.jobs_by_mode).map(([mode, count]) => {
                  const percentage = stats.total_jobs > 0
                    ? ((count / stats.total_jobs) * 100).toFixed(1)
                    : 0
                  return (
                    <div key={mode} className="space-y-1">
                      <div className="flex justify-between text-sm">
                        <span className="capitalize">{mode.replace('-', ' ')}</span>
                        <span className="text-muted-foreground">
                          {count} ({percentage}%)
                        </span>
                      </div>
                      <div className="h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary transition-all"
                          style={{ width: `${percentage}%` }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : (
              <p className="text-muted-foreground text-center py-8">No data available</p>
            )}
          </CardContent>
        </Card>

        {/* Processing Time by Mode */}
        <Card>
          <CardHeader>
            <CardTitle>Avg. Processing Time by Mode</CardTitle>
          </CardHeader>
          <CardContent>
            {Object.keys(timeByMode).length > 0 ? (
              <div className="space-y-4">
                {Object.entries(timeByMode).map(([mode, data]) => {
                  const avgTime = data.total / data.count
                  return (
                    <div key={mode} className="flex justify-between items-center">
                      <span className="capitalize">{mode.replace('-', ' ')}</span>
                      <div className="text-right">
                        <span className="font-medium">{formatDuration(avgTime)}</span>
                        <span className="text-xs text-muted-foreground ml-2">
                          ({data.count} jobs)
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : (
              <p className="text-muted-foreground text-center py-8">No data available</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Jobs by Day */}
      <Card>
        <CardHeader>
          <CardTitle>Jobs per Day (Last 7 Days)</CardTitle>
        </CardHeader>
        <CardContent>
          {Object.keys(jobsByDay).length > 0 ? (
            <div className="flex items-end justify-between h-32 gap-2">
              {Object.entries(jobsByDay).slice(-7).map(([day, count]) => {
                const maxCount = Math.max(...Object.values(jobsByDay))
                const height = maxCount > 0 ? (count / maxCount) * 100 : 0
                return (
                  <div key={day} className="flex-1 flex flex-col items-center gap-1">
                    <span className="text-xs font-medium">{count}</span>
                    <div
                      className="w-full bg-primary rounded-t transition-all"
                      style={{ height: `${height}%`, minHeight: count > 0 ? '4px' : '0' }}
                    />
                    <span className="text-xs text-muted-foreground">
                      {new Date(day).toLocaleDateString(undefined, { weekday: 'short' })}
                    </span>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-muted-foreground text-center py-8">No data available</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
