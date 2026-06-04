import type { Metadata, Viewport } from "next"
import { Inter, Instrument_Serif, JetBrains_Mono } from "next/font/google"
import { CustomCursor } from "@/components/custom-cursor"
import { AuthInitializer } from "@/components/auth-initializer"
import { ToastProvider } from "@/components/toast-provider"
import "./globals.css"

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
  display: "swap",
  weight: ["300", "400", "500", "600", "700", "800"],
})

const instrumentSerif = Instrument_Serif({
  variable: "--font-serif",
  subsets: ["latin"],
  display: "swap",
  weight: ["400"],
  style: ["normal", "italic"],
})

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  display: "swap",
})

export const metadata: Metadata = {
  title: "Kre8 Clips — Long videos into viral moments.",
  description:
    "Paste a YouTube URL. Get platform-ready clips in 90 seconds. AI analysis, speaker tracking, narrative assembly.",
  icons: {
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>✂️</text></svg>",
  },
}

export const viewport: Viewport = {
  themeColor: "#0a0a0a",
  width: "device-width",
  initialScale: 1,
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body
        className={`${inter.variable} ${instrumentSerif.variable} ${jetbrainsMono.variable} grain min-h-screen bg-[#0a0a0a] text-[#f5f4ef] antialiased font-sans`}
      >
        <CustomCursor />
        <AuthInitializer />
        <ToastProvider>
          {children}
        </ToastProvider>
      </body>
    </html>
  )
}
