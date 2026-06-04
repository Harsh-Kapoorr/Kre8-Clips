import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent, act } from "@testing-library/react"
import { ClipCard } from "@/components/clip-card"

vi.mock("framer-motion", () => ({
  motion: new Proxy(
    {},
    {
      get: () => {
        const Comp = ({ children, ...rest }: any) => (
          <div {...rest}>{children}</div>
        )
        return Comp
      },
    }
  ),
  AnimatePresence: ({ children }: any) => <>{children}</>,
  useReducedMotion: () => false,
}))

const baseClip = {
  title: "Hook moment",
  duration_seconds: 30,
  output_file: "/.jobs/abc123/clip_1.mp4",
  viral_share_prob: 0.6,
  viral_save_prob: 0.5,
  viral_comment_prob: 0.4,
  viral_composite: 0.6,
}

function getVideo(): HTMLVideoElement {
  const v = document.querySelector("video") as HTMLVideoElement | null
  if (!v) throw new Error("video element not found")
  return v
}

describe("ClipCard scrub bar", () => {
  it("renders an accessible progress slider", () => {
    render(<ClipCard clip={baseClip} index={0} />)
    const slider = screen.getByRole("slider", { name: /progress/i })
    expect(slider).toBeInTheDocument()
    expect(slider).toHaveAttribute("aria-valuemin", "0")
    expect(slider).toHaveAttribute("aria-valuemax", "30")
    expect(slider).toHaveAttribute("aria-orientation", "horizontal")
  })

  it("seeks when the slider is clicked", () => {
    render(<ClipCard clip={baseClip} index={0} />)
    const slider = screen.getByRole("slider", { name: /progress/i })
    const video = getVideo()

    Object.defineProperty(video, "duration", {
      configurable: true,
      get: () => 30,
    })
    video.dispatchEvent(new Event("loadedmetadata"))

    const rectSpy = vi
      .spyOn(HTMLElement.prototype, "getBoundingClientRect")
      .mockReturnValue({
        x: 0,
        y: 0,
        left: 0,
        top: 0,
        right: 200,
        bottom: 8,
        width: 200,
        height: 8,
        toJSON: () => ({}),
      } as DOMRect)

    act(() => {
      fireEvent.click(slider, { clientX: 100 })
    })

    expect(video.currentTime).toBeCloseTo(15, 1)
    expect(
      screen.getByRole("slider", { name: /progress/i })
    ).toHaveAttribute("aria-valuenow", "15")

    rectSpy.mockRestore()
  })

  it("supports keyboard seeking: ArrowRight from 0 jumps 5s", () => {
    render(<ClipCard clip={baseClip} index={0} />)
    const video = getVideo()
    Object.defineProperty(video, "duration", { configurable: true, get: () => 30 })
    video.dispatchEvent(new Event("loadedmetadata"))
    const slider = screen.getByRole("slider", { name: /progress/i })
    slider.focus()
    act(() => {
      fireEvent.keyDown(slider, { key: "ArrowRight" })
    })
    expect(video.currentTime).toBeCloseTo(5, 1)
  })

  it("supports keyboard seeking: ArrowLeft clamps to 0", () => {
    render(<ClipCard clip={baseClip} index={0} />)
    const video = getVideo()
    Object.defineProperty(video, "duration", { configurable: true, get: () => 30 })
    video.dispatchEvent(new Event("loadedmetadata"))
    const slider = screen.getByRole("slider", { name: /progress/i })
    slider.focus()
    act(() => {
      fireEvent.keyDown(slider, { key: "ArrowLeft" })
    })
    expect(video.currentTime).toBe(0)
  })

  it("supports keyboard seeking: End jumps to duration", () => {
    render(<ClipCard clip={baseClip} index={0} />)
    const video = getVideo()
    Object.defineProperty(video, "duration", { configurable: true, get: () => 30 })
    video.dispatchEvent(new Event("loadedmetadata"))
    const slider = screen.getByRole("slider", { name: /progress/i })
    slider.focus()
    act(() => {
      fireEvent.keyDown(slider, { key: "End" })
    })
    expect(video.currentTime).toBeCloseTo(30, 1)
  })

  it("supports keyboard seeking: Home jumps to 0", () => {
    render(<ClipCard clip={baseClip} index={0} />)
    const video = getVideo()
    Object.defineProperty(video, "duration", { configurable: true, get: () => 30 })
    video.dispatchEvent(new Event("loadedmetadata"))
    const slider = screen.getByRole("slider", { name: /progress/i })
    slider.focus()
    act(() => {
      fireEvent.keyDown(slider, { key: "Home" })
    })
    expect(video.currentTime).toBe(0)
  })

  it("supports keyboard seeking: Space/Enter toggles play", () => {
    render(<ClipCard clip={baseClip} index={0} />)
    const video = getVideo()
    const playSpy = vi.spyOn(video, "play").mockResolvedValue(undefined)
    const slider = screen.getByRole("slider", { name: /progress/i })
    slider.focus()
    act(() => {
      fireEvent.keyDown(slider, { key: "Enter" })
    })
    expect(playSpy).toHaveBeenCalled()
  })

  it("updates progress as the video plays", () => {
    render(<ClipCard clip={baseClip} index={0} />)
    const video = getVideo()

    Object.defineProperty(video, "duration", {
      configurable: true,
      get: () => 30,
    })
    video.dispatchEvent(new Event("loadedmetadata"))

    act(() => {
      video.currentTime = 7.5
      video.dispatchEvent(new Event("timeupdate"))
    })

    expect(
      screen.getByRole("slider", { name: /progress/i })
    ).toHaveAttribute("aria-valuenow", "7.5")
  })
})
