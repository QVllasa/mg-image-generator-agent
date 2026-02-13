'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import {
  ArrowLeft,
  Loader2,
  AlertCircle,
  Clock,
  Image as ImageIcon,
  ExternalLink,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { JobProgress } from '@/components/JobProgress'
import { HotspotOverlay } from '@/components/HotspotOverlay'
import { fetchJob, type Job, type ProductHotspot } from '@/lib/api'
import { formatDuration, formatRelativeTime } from '@/lib/utils'

const modeLabels: Record<string, string> = {
  'text-prompt': 'Text Prompt',
  'multi-reference': 'Multi-Reference',
  'meilisearch': 'MeiliSearch',
}

export default function JobDetailPage() {
  const params = useParams()
  const jobId = params.id as string

  const [job, setJob] = useState<Job | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedImage, setSelectedImage] = useState(0)

  useEffect(() => {
    async function loadJob() {
      try {
        setIsLoading(true)
        const data = await fetchJob(jobId)
        setJob(data)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load job')
      } finally {
        setIsLoading(false)
      }
    }
    loadJob()

    // Poll for updates if job is processing
    const interval = setInterval(async () => {
      const data = await fetchJob(jobId).catch(() => null)
      if (data) {
        setJob(data)
        if (data.status !== 'processing' && data.status !== 'pending') {
          clearInterval(interval)
        }
      }
    }, 3000)

    return () => clearInterval(interval)
  }, [jobId])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error || !job) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4">
        <AlertCircle className="h-12 w-12 text-destructive" />
        <p className="text-lg text-muted-foreground">{error || 'Job not found'}</p>
        <Link href="/jobs">
          <Button>Back to Jobs</Button>
        </Link>
      </div>
    )
  }

  const currentImage = job.images?.[selectedImage]

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <Link
            href="/jobs"
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Jobs
          </Link>
          <h1 className="text-2xl font-bold">{job.session_id}</h1>
          <div className="flex items-center gap-2">
            <Badge variant="outline">{modeLabels[job.mode] || job.mode}</Badge>
            <span className="text-sm text-muted-foreground">{job.style}</span>
            {job.room_type && (
              <span className="text-sm text-muted-foreground">| {job.room_type}</span>
            )}
          </div>
        </div>
        <div className="text-right text-sm text-muted-foreground">
          <p>Created {formatRelativeTime(job.created_at)}</p>
          {job.processing_time_ms && (
            <p className="flex items-center gap-1 justify-end">
              <Clock className="h-3 w-3" />
              {formatDuration(job.processing_time_ms)}
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Progress */}
          <JobProgress jobId={jobId} initialJob={job} />

          {/* Image Viewer */}
          {job.images && job.images.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ImageIcon className="h-5 w-5" />
                  Staged Images
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Image selector */}
                {job.images.length > 1 && (
                  <div className="flex gap-2 overflow-x-auto pb-2">
                    {job.images.map((img, i) => (
                      <button
                        key={img.id}
                        onClick={() => setSelectedImage(i)}
                        className={`relative w-20 h-20 rounded-lg overflow-hidden border-2 flex-shrink-0
                          ${i === selectedImage ? 'border-primary' : 'border-transparent'}`}
                      >
                        {img.staged_image_url ? (
                          <img
                            src={img.staged_image_url}
                            alt={img.original_filename}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="w-full h-full bg-muted flex items-center justify-center">
                            <Loader2 className="h-4 w-4 animate-spin" />
                          </div>
                        )}
                      </button>
                    ))}
                  </div>
                )}

                {/* Selected image with hotspots */}
                {currentImage && (
                  <div className="space-y-4">
                    {currentImage.staged_image_url ? (
                      <HotspotOverlay
                        imageUrl={currentImage.staged_image_url}
                        hotspots={currentImage.product_hotspots || []}
                      />
                    ) : (
                      <div className="aspect-video bg-muted rounded-lg flex items-center justify-center">
                        {currentImage.status === 'pending' ? (
                          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                        ) : (
                          <p className="text-muted-foreground">Image not available</p>
                        )}
                      </div>
                    )}

                    {/* Image info */}
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">
                        {currentImage.original_filename}
                      </span>
                      <div className="flex items-center gap-4">
                        {currentImage.furniture_added && currentImage.furniture_added.length > 0 && (
                          <span className="text-muted-foreground">
                            {currentImage.furniture_added.length} items added
                          </span>
                        )}
                        {currentImage.staged_image_url && (
                          <a
                            href={currentImage.staged_image_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1 text-primary hover:underline"
                          >
                            Open full size
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Request Details */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Request Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div>
                <p className="text-muted-foreground">Job ID</p>
                <p className="font-mono text-xs break-all">{job.id}</p>
              </div>
              {job.color_preferences && job.color_preferences.length > 0 && (
                <div>
                  <p className="text-muted-foreground">Colors</p>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {job.color_preferences.map((color) => (
                      <Badge key={color} variant="outline" className="text-xs">
                        {color}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
              {job.budget_range && (
                <div>
                  <p className="text-muted-foreground">Budget</p>
                  <p>{job.budget_range.min} - {job.budget_range.max}</p>
                </div>
              )}
              {job.furniture_types && job.furniture_types.length > 0 && (
                <div>
                  <p className="text-muted-foreground">Furniture Types</p>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {job.furniture_types.map((type) => (
                      <Badge key={type} variant="outline" className="text-xs">
                        {type}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Selected Products */}
          {job.selected_products && job.selected_products.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Selected Products</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {job.selected_products.map((product) => (
                  <div
                    key={product.id}
                    className="flex gap-3 p-2 rounded-lg hover:bg-muted"
                  >
                    {product.image_url && (
                      <img
                        src={product.image_url}
                        alt={product.name}
                        className="w-16 h-16 object-cover rounded"
                      />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm truncate">{product.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {product.furniture_type}
                      </p>
                      {product.price && (
                        <p className="text-sm font-medium">
                          {product.price.toFixed(2)}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Room Analysis */}
          {currentImage?.room_analysis && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Room Analysis</CardTitle>
              </CardHeader>
              <CardContent className="text-sm space-y-2">
                {Object.entries(currentImage.room_analysis).map(([key, value]) => (
                  <div key={key}>
                    <p className="text-muted-foreground capitalize">
                      {key.replace(/_/g, ' ')}
                    </p>
                    <p>{Array.isArray(value) ? value.join(', ') : String(value)}</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
