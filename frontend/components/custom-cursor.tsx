"use client"

import { useEffect, useState } from "react"
import { motion, useSpring } from "framer-motion"

export function CustomCursor() {
  const [isVisible, setIsVisible] = useState(false)
  const [isHovering, setIsHovering] = useState(false)

  const dotX = useSpring(0, { stiffness: 1000, damping: 50 })
  const dotY = useSpring(0, { stiffness: 1000, damping: 50 })
  const ringX = useSpring(0, { stiffness: 300, damping: 25 })
  const ringY = useSpring(0, { stiffness: 300, damping: 25 })

  useEffect(() => {
    const handleMove = (e: MouseEvent) => {
      dotX.set(e.clientX)
      dotY.set(e.clientY)
      ringX.set(e.clientX)
      ringY.set(e.clientY)
      if (!isVisible) setIsVisible(true)
    }

    const handleEnterInteractive = () => setIsHovering(true)
    const handleLeaveInteractive = () => setIsHovering(false)

    window.addEventListener("mousemove", handleMove)

    const addListeners = () => {
      document
        .querySelectorAll("a, button, input, textarea, [role='button']")
        .forEach((el) => {
          el.addEventListener("mouseenter", handleEnterInteractive)
          el.addEventListener("mouseleave", handleLeaveInteractive)
        })
    }

    addListeners()
    const interval = setInterval(addListeners, 5000)

    return () => {
      window.removeEventListener("mousemove", handleMove)
      clearInterval(interval)
    }
  }, [dotX, dotY, ringX, ringY, isVisible])

  if (typeof window !== "undefined" && "ontouchstart" in window) {
    return null
  }

  return (
    <>
      {/* Dot */}
      <motion.div
        className="pointer-events-none fixed z-[9999] rounded-full bg-[#0057ff]"
        style={{
          left: dotX,
          top: dotY,
          x: "-50%",
          y: "-50%",
          width: isHovering ? 6 : 8,
          height: isHovering ? 6 : 8,
          opacity: isVisible ? 1 : 0,
        }}
        transition={{ width: { type: "spring", stiffness: 500, damping: 30 }, height: { type: "spring", stiffness: 500, damping: 30 } }}
      />
      {/* Ring */}
      <motion.div
        className="pointer-events-none fixed z-[9998] rounded-full border border-[rgba(0,87,255,0.35)]"
        style={{
          left: ringX,
          top: ringY,
          x: "-50%",
          y: "-50%",
          width: isHovering ? 36 : 28,
          height: isHovering ? 36 : 28,
          opacity: isVisible ? 1 : 0,
        }}
        transition={{ width: { type: "spring", stiffness: 300, damping: 20 }, height: { type: "spring", stiffness: 300, damping: 20 } }}
      />
    </>
  )
}
