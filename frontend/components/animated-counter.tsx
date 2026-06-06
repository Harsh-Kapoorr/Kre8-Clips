"use client"

import { useEffect, useRef, useState } from "react"
import { useInView } from "framer-motion"

interface AnimatedCounterProps {
  value: string
  label: string
  delay?: number
}

function parseCounterValue(value: string): { prefix: string; num: number; suffix: string; isText: boolean } {
  const match = value.match(/^([^0-9]*)([0-9]+(?:\.[0-9]+)?)(.*)$/)
  if (!match) return { prefix: "", num: 0, suffix: value, isText: true }
  return { prefix: match[1], num: parseFloat(match[2]), suffix: match[3], isText: false }
}

export function AnimatedCounter({ value, label, delay = 0 }: AnimatedCounterProps) {
  const ref = useRef<HTMLDivElement>(null)
  const isInView = useInView(ref, { once: true, amount: 0.5 })
  const [count, setCount] = useState(0)
  const { prefix, num, suffix, isText } = parseCounterValue(value)

  useEffect(() => {
    if (!isInView) return
    const duration = 1500
    const steps = 60
    const stepDuration = duration / steps
    let current = 0
    const increment = num / steps
    const timeout = setTimeout(() => {
      const interval = setInterval(() => {
        current += increment
        if (current >= num) {
          setCount(num)
          clearInterval(interval)
        } else {
          setCount(current)
        }
      }, stepDuration)
      return () => clearInterval(interval)
    }, delay)
    return () => clearTimeout(timeout)
  }, [isInView, num, delay])

  if (isText) {
    return (
      <div ref={ref} className="text-center">
        <div className="text-[44px] font-semibold leading-none tracking-[-0.03em] text-[#f5f4ef] sm:text-[56px]" style={{ fontFamily: "var(--font-serif)" }}>
          {value}
        </div>
        <div className="mt-3 text-[12.5px] leading-relaxed text-[#8a8880]">{label}</div>
      </div>
    )
  }

  const display = num % 1 === 0 ? Math.floor(count) : count.toFixed(1)

  return (
    <div ref={ref} className="text-center">
      <div className="text-[44px] font-semibold leading-none tracking-[-0.03em] text-[#f5f4ef] sm:text-[56px]" style={{ fontFamily: "var(--font-serif)" }}>
        {prefix}{display}{suffix}
      </div>
      <div className="mt-3 text-[12.5px] leading-relaxed text-[#8a8880]">{label}</div>
    </div>
  )
}
