'use client'

import { useEffect, useState } from 'react'
import { Loader2, AlertCircle, Image as ImageIcon } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { HotspotOverlay } from '@/components/HotspotOverlay'
import { fetchJobs, type Job } from '@/lib/api'

export default function GalleryPage() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedImage, setSelectedImage] = useState<{
    jobId: string
    imageIndex: number
    url: string
    hotspots: any[]
  } | null>(null)

  useEffect(() => {
    async function loadJobs() {
      try {
        setIsLoading(true)
        const data = await fetchJobs({ status: 'completed', limit: 50 })
        setJobs(data.jobs)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load gallery')
      } finally {
        setIsLoading(false)
      }
    }
    loadJobs()
  }, [])

  // Flatten all images from all jobs
  const allImages = jobs.flatMap((job) =>
    (job.images || [])
      .filter((img) => img.staged_image_url)
      .map((img) => ({
        jobId: job.id,
        sessionId: job.session_id,
        imageIndex: img.image_index,
        url: img.staged_image_url!,
        markersUrl: img.staged_image_with_markers_url,
        hotspots: img.product_hotspots || [],
        filename: img.original_filename,
        style: job.style,
      }))
  )

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
        <h1 className="text-3xl font-bold">Gallery</h1>
        <p className="text-muted-foreground">
          {allImages.length} staged images
        </p>
      </div>

      {/* Selected Image Modal */}
      {selectedImage && (
        <div
          className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setSelectedImage(null)}
        >
          <div
            className="bg-background rounded-lg shadow-lg max-w-4xl w-full max-h-[90vh] overflow-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-4">
              <HotspotOverlay
                imageUrl={selectedImage.url}
                hotspots={selectedImage.hotspots}
              />
            </div>
          </div>
        </div>
      )}

      {/* Gallery Grid */}
      {allImages.length > 0 ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {allImages.map((image, i) => (
            <button
              key={`${image.jobId}-${image.imageIndex}`}
              onClick={() =>
                setSelectedImage({
                  jobId: image.jobId,
                  imageIndex: image.imageIndex,
                  url: image.url,
                  hotspots: image.hotspots,
                })
              }
              className="group relative aspect-video bg-muted rounded-lg overflow-hidden hover:ring-2 hover:ring-primary transition-all"
            >
              <img
                src={image.url}
                alt={image.filename}
                className="w-full h-full object-cover"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
                <div className="absolute bottom-2 left-2 right-2 text-white text-sm">
                  <p className="font-medium truncate">{image.sessionId}</p>
                  <p className="text-xs opacity-80">{image.style}</p>
                </div>
              </div>
              {image.hotspots.length > 0 && (
                <div className="absolute top-2 right-2 bg-primary text-primary-foreground text-xs px-2 py-0.5 rounded-full">
                  {image.hotspots.length} hotspots
                </div>
              )}
            </button>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <ImageIcon className="h-12 w-12 mb-4" />
            <p>No images yet</p>
            <p className="text-sm">Complete some staging jobs to see them here</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
