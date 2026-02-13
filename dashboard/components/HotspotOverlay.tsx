'use client'

import { useState } from 'react'
import type { ProductHotspot } from '@/lib/api'

interface HotspotOverlayProps {
  imageUrl: string
  hotspots: ProductHotspot[]
  onHotspotClick?: (hotspot: ProductHotspot) => void
}

export function HotspotOverlay({ imageUrl, hotspots, onHotspotClick }: HotspotOverlayProps) {
  const [activeHotspot, setActiveHotspot] = useState<string | null>(null)

  return (
    <div className="relative w-full aspect-video bg-muted rounded-lg overflow-hidden">
      {/* Image */}
      <img
        src={imageUrl}
        alt="Staged room"
        className="w-full h-full object-contain"
      />

      {/* Hotspots */}
      {hotspots.map((hotspot, index) => (
        <div key={index}>
          {/* Hotspot Marker */}
          <button
            className="absolute w-6 h-6 -ml-3 -mt-3 rounded-full bg-primary text-primary-foreground
                       flex items-center justify-center text-xs font-bold
                       hover:scale-110 transition-transform cursor-pointer
                       shadow-lg border-2 border-white"
            style={{
              left: `${hotspot.hotspot_x}%`,
              top: `${hotspot.hotspot_y}%`,
            }}
            onClick={() => {
              setActiveHotspot(activeHotspot === hotspot.product_name ? null : hotspot.product_name)
              onHotspotClick?.(hotspot)
            }}
            onMouseEnter={() => setActiveHotspot(hotspot.product_name)}
            onMouseLeave={() => setActiveHotspot(null)}
          >
            {index + 1}
          </button>

          {/* Bounding Box (shown on hover) */}
          {activeHotspot === hotspot.product_name && (
            <>
              <div
                className="absolute border-2 border-primary rounded pointer-events-none"
                style={{
                  left: `${hotspot.x}%`,
                  top: `${hotspot.y}%`,
                  width: `${hotspot.width}%`,
                  height: `${hotspot.height}%`,
                }}
              />
              {/* Tooltip */}
              <div
                className="absolute z-10 px-3 py-2 bg-popover text-popover-foreground
                           rounded-lg shadow-lg text-sm whitespace-nowrap
                           transform -translate-x-1/2"
                style={{
                  left: `${hotspot.hotspot_x}%`,
                  top: `${hotspot.hotspot_y - 15}%`,
                }}
              >
                <p className="font-medium">{hotspot.product_name}</p>
                {hotspot.product_id && (
                  <p className="text-xs text-muted-foreground">ID: {hotspot.product_id}</p>
                )}
                <p className="text-xs text-muted-foreground">
                  Confidence: {(hotspot.confidence * 100).toFixed(0)}%
                </p>
              </div>
            </>
          )}
        </div>
      ))}

      {/* Legend */}
      {hotspots.length > 0 && (
        <div className="absolute bottom-2 left-2 right-2 bg-background/90 backdrop-blur rounded-lg p-2">
          <div className="flex flex-wrap gap-2 text-xs">
            {hotspots.map((hotspot, index) => (
              <button
                key={index}
                className="flex items-center gap-1 hover:text-primary transition-colors"
                onMouseEnter={() => setActiveHotspot(hotspot.product_name)}
                onMouseLeave={() => setActiveHotspot(null)}
                onClick={() => onHotspotClick?.(hotspot)}
              >
                <span className="w-4 h-4 rounded-full bg-primary text-primary-foreground
                               flex items-center justify-center text-[10px] font-bold">
                  {index + 1}
                </span>
                <span className="truncate max-w-[120px]">{hotspot.product_name}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
