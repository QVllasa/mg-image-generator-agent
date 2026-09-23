'use client'

import { useEffect, useState, useCallback } from 'react'
import { subscribeToJobEvents, type JobEvent } from '@/lib/api'

export function useJobEvents(jobId: string | null) {
  const [events, setEvents] = useState<JobEvent[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const addEvent = useCallback((event: JobEvent) => {
    setEvents((prev) => [...prev, event])
  }, [])

  useEffect(() => {
    if (!jobId) return

    setIsConnected(true)
    setError(null)
    setEvents([])

    const cleanup = subscribeToJobEvents(
      jobId,
      (event) => {
        addEvent(event)
        // Close connection when job is done
        if (event.event_type === 'completed' || event.event_type === 'failed') {
          setIsConnected(false)
        }
      },
      (err) => {
        setError(err)
        setIsConnected(false)
      }
    )

    return cleanup
  }, [jobId, addEvent])

  return { events, isConnected, error }
}
