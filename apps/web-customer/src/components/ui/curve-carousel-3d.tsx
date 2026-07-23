"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { motion } from "framer-motion"
import {
  Camera,
  Gamepad2,
  Headphones,
  Laptop,
  ShoppingBag,
  Smartphone,
  Sparkles,
  Store,
  Watch,
  type LucideIcon,
} from "lucide-react"
import { cn } from "@/lib/utils"

export interface CarouselMediaItem {
  id: string | number
  title: string
  description?: string
  href?: string
  type: "image" | "video"
  src: string
  poster?: string
}

interface CurveCarousel3DProps {
  items: CarouselMediaItem[]
  autoplay?: boolean
  autoplaySpeed?: number
  direction?: 1 | -1
  cardWidth?: number
  cardHeight?: number
  perspective?: number
  anglePerCard?: number
  showControls?: boolean
  showLabels?: boolean
  showCardLabels?: boolean
  className?: string
}

const FRICTION = 0.94
const MIN_VELOCITY = 0.02

const CATEGORY_ICONS: Record<string, LucideIcon> = {
  Shopping: ShoppingBag,
  Smartphones: Smartphone,
  Laptops: Laptop,
  Watches: Watch,
  Cameras: Camera,
  Audio: Headphones,
  Gaming: Gamepad2,
  Fashion: Sparkles,
  Lifestyle: Sparkles,
  Accessories: Watch,
  Electronics: Laptop,
  "Instant Approval": Store,
}

function wrapOffset(offset: number, count: number): number {
  let o = offset % count
  if (o > count / 2) o -= count
  if (o < -count / 2) o += count
  return o
}

function CarouselImage({
  item,
  width,
  height,
}: {
  item: CarouselMediaItem
  width: number
  height: number
}) {
  const [src, setSrc] = useState(item.src)
  const fallback = `https://images.unsplash.com/photo-1556742049-0cfed4f6a5d8?auto=format&fit=crop&w=${width}&h=${height}&q=80`

  useEffect(() => {
    setSrc(item.src)
  }, [item.src])

  return (
    <img
      src={src}
      alt={item.title}
      width={width}
      height={height}
      loading="lazy"
      decoding="async"
      draggable={false}
      className="h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-108"
      onError={() => {
        if (src !== fallback) setSrc(fallback)
      }}
    />
  )
}

export function CurveCarousel3D({
  items,
  autoplay = true,
  autoplaySpeed = 0.004,
  direction = 1,
  cardWidth = 168,
  cardHeight = 224,
  perspective = 1100,
  anglePerCard = 14,
  showControls = false,
  showLabels = false,
  showCardLabels = false,
  className,
}: CurveCarousel3DProps) {
  const count = items.length
  const [rotation, setRotation] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const [isHovered, setIsHovered] = useState(false)
  const [wasDragging, setWasDragging] = useState(false)
  const [dims, setDims] = useState({ w: cardWidth, h: cardHeight, angle: anglePerCard })

  const rotationRef = useRef(0)
  const velocityRef = useRef(0)
  const dragStartRef = useRef({ x: 0, rotation: 0 })
  const rafRef = useRef(0)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const update = () => {
      const mobile = window.innerWidth < 768
      setDims({
        w: mobile ? cardWidth * 0.78 : cardWidth,
        h: mobile ? cardHeight * 0.78 : cardHeight,
        angle: mobile ? anglePerCard * 1.1 : anglePerCard,
      })
    }
    update()
    window.addEventListener("resize", update)
    return () => window.removeEventListener("resize", update)
  }, [cardWidth, cardHeight, anglePerCard])

  useEffect(() => {
    const tick = () => {
      if (!isDragging && autoplay && !isHovered) {
        if (Math.abs(velocityRef.current) < MIN_VELOCITY) {
          velocityRef.current = autoplaySpeed * direction
        }
      }
      if (!isDragging && Math.abs(velocityRef.current) >= MIN_VELOCITY) {
        rotationRef.current += velocityRef.current
        velocityRef.current *= FRICTION
        if (Math.abs(velocityRef.current) < MIN_VELOCITY) velocityRef.current = 0
        setRotation(rotationRef.current)
      } else if (!isDragging && autoplay && !isHovered && Math.abs(velocityRef.current) < MIN_VELOCITY) {
        rotationRef.current += autoplaySpeed * direction
        setRotation(rotationRef.current)
      }
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [isDragging, isHovered, autoplay, autoplaySpeed, direction])

  const handlePointerDown = (e: React.PointerEvent) => {
    setIsDragging(true)
    setWasDragging(false)
    velocityRef.current = 0
    dragStartRef.current = { x: e.clientX, rotation: rotationRef.current }
    containerRef.current?.setPointerCapture(e.pointerId)
  }

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDragging) return
    if (Math.abs(e.movementX) > 2) setWasDragging(true)
    const delta = (e.clientX - dragStartRef.current.x) / (dims.w * 0.55)
    rotationRef.current = dragStartRef.current.rotation - delta
    velocityRef.current = -(e.movementX || 0) / (dims.w * 0.55) * 0.15
    setRotation(rotationRef.current)
  }

  const handlePointerUp = () => setIsDragging(false)

  const getCardStyle = (offset: number): React.CSSProperties => {
    const abs = Math.abs(offset)
    const rotateY = offset * dims.angle
    const translateX = offset * (dims.w * 0.48)
    const translateZ = -abs * 38
    const scale = Math.max(0.8, 1 - abs * 0.048)
    const opacity = Math.max(0.55, 1 - abs * 0.07)

    return {
      position: "absolute",
      left: "50%",
      top: "50%",
      width: dims.w,
      height: dims.h,
      marginLeft: -dims.w / 2,
      marginTop: -dims.h / 2,
      transform: `translateX(${translateX}px) translateZ(${translateZ}px) rotateY(${rotateY}deg) scale(${scale})`,
      opacity,
      zIndex: Math.round(100 - abs * 10),
      transformStyle: "preserve-3d",
    }
  }

  const activeIndex = ((Math.round(rotation) % count) + count) % count

  const renderCard = (item: CarouselMediaItem, index: number) => {
    const offset = wrapOffset(index - rotation, count)
    if (Math.abs(offset) > 6) return null

    const isCenter = Math.abs(offset) < 0.5
    const style = getCardStyle(offset)
    const Icon = CATEGORY_ICONS[item.title] ?? ShoppingBag
    const showTopLabel = showCardLabels && Math.abs(offset) <= 4

    const card = (
      <article
        className={cn(
          "relative h-full w-full overflow-hidden rounded-[22px] bg-neutral-200 dark:bg-neutral-800",
          "shadow-[0_8px_30px_rgba(0,0,0,0.12)] dark:shadow-[0_8px_30px_rgba(0,0,0,0.45)] will-change-transform",
          "border border-white/10 dark:border-white/5",
          "transition-all duration-500 ease-out group-hover:border-orange-500/30 group-hover:shadow-[0_15px_40px_rgba(249,115,22,0.22)]"
        )}
      >
        {item.type === "video" ? (
          <video
            src={item.src}
            poster={item.poster}
            autoPlay
            muted
            loop
            playsInline
            className="h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-108"
          />
        ) : (
          <CarouselImage item={item} width={dims.w} height={dims.h} />
        )}

        {/* Iridescent luxury glass sheen overlay */}
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-tr from-transparent via-white/5 to-white/20 opacity-0 group-hover:opacity-100 transition-opacity duration-700 z-10" />

        {/* Elegant top category label tag */}
        {showTopLabel && (
          <div className="absolute left-3.5 top-3.5 z-20 flex items-center gap-2">
            <span className="flex h-7.5 w-7.5 items-center justify-center rounded-lg bg-white/80 dark:bg-black/60 shadow-sm backdrop-blur-md border border-white/20 dark:border-white/10 transition-all duration-300 group-hover:bg-orange-500 group-hover:text-white">
              <Icon className="h-4 w-4 text-orange-600 dark:text-orange-300 group-hover:text-white transition-colors duration-300" strokeWidth={2.25} />
            </span>
            <span className="text-[12.5px] font-bold tracking-wide text-white drop-shadow-[0_2px_4px_rgba(0,0,0,0.8)] backdrop-blur-[2px] bg-black/35 px-2.5 py-0.5 rounded-full border border-white/10 select-none">
              {item.title}
            </span>
          </div>
        )}

        {showLabels && isCenter && (
          <motion.div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/60 to-transparent p-4 z-20">
            <p className="text-sm font-bold text-white tracking-wide">{item.title}</p>
          </motion.div>
        )}
      </article>
    )

    if (item.href) {
      return (
        <Link
          key={item.id}
          href={item.href}
          style={style}
          className="block group"
          onClick={(e) => wasDragging && e.preventDefault()}
          draggable={false}
        >
          {card}
        </Link>
      )
    }

    return (
      <div key={item.id} style={style} className="group">
        {card}
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className={cn("relative w-full cursor-grab touch-none active:cursor-grabbing", className)}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerLeave={handlePointerUp}
      onPointerCancel={handlePointerUp}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div
        className="relative mx-auto w-full overflow-hidden"
        style={{
          height: dims.h + 48,
          perspective: `${perspective}px`,
          perspectiveOrigin: "50% 42%",
          WebkitMaskImage:
            "linear-gradient(to right, transparent 0%, black 12%, black 88%, transparent 100%)",
          maskImage:
            "linear-gradient(to right, transparent 0%, black 12%, black 88%, transparent 100%)",
        }}
      >
        <div
          className="absolute inset-0 flex items-center justify-center"
          style={{ transformStyle: "preserve-3d" }}
        >
          {items.map((item, index) => renderCard(item, index))}
        </div>

        <div
          className="pointer-events-none absolute inset-y-0 left-0 z-20 w-16 bg-gradient-to-r from-[var(--background)]/70 to-transparent md:w-24 dark:from-[#231E1C]/70"
          aria-hidden
        />
        <div
          className="pointer-events-none absolute inset-y-0 right-0 z-20 w-16 bg-gradient-to-l from-[var(--background)]/70 to-transparent md:w-24 dark:from-[#161413]/70"
          aria-hidden
        />
      </div>

      {showControls && (
        <div className="mt-4 flex justify-center gap-1.5">
          {items.map((item, i) => (
            <button
              key={item.id}
              type="button"
              aria-label={`Go to ${item.title}`}
              className={cn(
                "h-1 rounded-full transition-all duration-300",
                i === activeIndex ? "w-6 bg-neutral-800 dark:bg-orange-400" : "w-1 bg-neutral-300 dark:bg-neutral-600"
              )}
              onClick={() => {
                rotationRef.current = i
                velocityRef.current = 0
                setRotation(i)
              }}
            />
          ))}
        </div>
      )}
    </div>
  )
}
