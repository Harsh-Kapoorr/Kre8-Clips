"use client"

const COLUMNS = [
  {
    title: "Product",
    links: [
      { label: "How it works", href: "/#how" },
      { label: "Capabilities", href: "/#product" },
      { label: "Pricing", href: "/pricing" },
 ],
  },
  {
    title: "Resources",
    links: [
      { label: "GitHub", href: "https://github.com/Harsh-Kapoorr/Kre8-Clips" },
      { label: "API Docs", href: "/#docs" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "Twitter / X", href: "https://twitter.com/kre8clips" },
      { label: "GitHub", href: "https://github.com/Harsh-Kapoorr/Kre8-Clips" },
    ],
  },
  {
    title: "Legal",
    links: [
      { label: "Terms of Service", href: "/terms" },
      { label: "Privacy Policy", href: "/privacy" },
    ],
  },
]

const GithubIcon = (props: React.SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" {...props}>
    <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.11.79-.25.79-.56v-2.13c-3.2.7-3.87-1.36-3.87-1.36-.52-1.32-1.27-1.67-1.27-1.67-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.02 1.75 2.68 1.24 3.34.95.1-.74.4-1.24.72-1.53-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.18-3.1-.12-.29-.51-1.46.11-3.05 0 0 .96-.31 3.15 1.18a10.96 10.96 0 0 1 5.74 0c2.19-1.49 3.15-1.18 3.15-1.18.62 1.59.23 2.76.11 3.05.74.81 1.18 1.84 1.18 3.1 0 4.42-2.69 5.39-5.25 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.68.8.56C20.21 21.39 23.5 17.08 23.5 12 23.5 5.65 18.35.5 12 .5Z" />
  </svg>
)

const TwitterIcon = (props: React.SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" {...props}>
    <path d="M18.244 2H21.5l-7.5 8.57L23 22h-6.93l-5.43-6.97L4.4 22H1.14l8.04-9.19L1 2h7.1l4.92 6.49L18.244 2Zm-1.22 18h1.92L7.06 4h-2.1l12.06 16Z" />
  </svg>
)

export function SiteFooter() {
  return (
    <footer className="border-t border-white/[0.06]">
      <div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 sm:py-20">
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div>
            <a href="#top" className="inline-flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-md bg-[#ff5722]">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="#0a0a0a" aria-hidden="true">
                  <polygon points="6 4 20 12 6 20 6 4" />
                </svg>
              </span>
              <span className="text-[15px] font-semibold tracking-tight text-[#f5f4ef]">
                Kre<span style={{ color: "#ff5722" }}>8</span>{" "}
                <span className="text-[#8a8880] font-normal">Clips</span>
              </span>
            </a>
            <p
              className="mt-5 max-w-xs text-[15px] leading-relaxed text-[#8a8880]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Long videos into{" "}
              <span className="serif-italic text-[#ff5722]">viral moments</span>.
              Built for the way creators actually ship.
            </p>
            <div className="mt-7 flex items-center gap-2">
              <a
                href="https://github.com/Harsh-Kapoorr/Kre8-Clips"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="GitHub"
                className="flex h-9 w-9 items-center justify-center rounded-md border border-white/[0.08] text-[#8a8880] transition-colors hover:border-[#ff5722] hover:text-[#ff5722]"
              >
                <GithubIcon className="h-4 w-4" />
              </a>
              <a
                href="https://twitter.com/kre8clips"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Twitter"
                className="flex h-9 w-9 items-center justify-center rounded-md border border-white/[0.08] text-[#8a8880] transition-colors hover:border-[#ff5722] hover:text-[#ff5722]"
              >
                <TwitterIcon className="h-4 w-4" />
              </a>
            </div>
          </div>

          {COLUMNS.map((col) => (
            <div key={col.title}>
              <h4 className="eyebrow mb-5">{col.title}</h4>
              <ul className="space-y-3">
                {col.links.map((link) => (
                  <li key={link.label}>
                    <a
                      href={link.href}
                      className="text-[14px] text-[#b8b6b0] transition-colors hover:text-[#f5f4ef]"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-16 flex flex-col items-start justify-between gap-3 border-t border-white/[0.06] pt-6 sm:flex-row sm:items-center">
          <p className="text-[12.5px] text-[#555550]">
            © {new Date().getFullYear()} Kre8 Clips. All rights reserved.
          </p>
          <p className="text-[12.5px] text-[#555550]">
            <span className="serif-italic">Designed in-house.</span> Built for the long form.
          </p>
        </div>
      </div>
    </footer>
  )
}
