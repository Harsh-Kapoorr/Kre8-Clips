export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-[#f5f4ef] px-6 py-20">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-4xl font-serif mb-8">Privacy Policy</h1>
        <p className="text-sm text-[#f5f4ef]/60 mb-8">Last updated: June 2026</p>
        
        <div className="space-y-6 text-[#f5f4ef]/80 leading-relaxed">
          <section>
            <h2 className="text-xl font-semibold text-[#f5f4ef] mb-3">1. Information We Collect</h2>
            <p className="mb-3">We collect the following information:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li><strong>Account Information:</strong> Email address, name, and profile information when you sign up via Google OAuth or email/password.</li>
              <li><strong>Usage Data:</strong> Information about how you use Kre8 Clips, including videos you process and clips you generate.</li>
              <li><strong>API Keys:</strong> Optional Deepgram and Gemini API keys you provide for transcription and analysis services.</li>
            </ul>
          </section>
          
          <section>
            <h2 className="text-xl font-semibold text-[#f5f4ef] mb-3">2. How We Use Your Information</h2>
            <p className="mb-3">We use your information to:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li>Provide and maintain the Kre8 Clips service</li>
              <li>Process videos and generate clips on your behalf</li>
              <li>Improve our service and user experience</li>
              <li>Communicate with you about your account</li>
            </ul>
          </section>
          
          <section>
            <h2 className="text-xl font-semibold text-[#f5f4ef] mb-3">3. Data Storage</h2>
            <p>Your data is stored securely in our database. YouTube video URLs and generated clips are stored temporarily and deleted after processing. Your account information is retained until you delete your account.</p>
          </section>
          
          <section>
            <h2 className="text-xl font-semibold text-[#f5f4ef] mb-3">4. Third-Party Services</h2>
            <p className="mb-3">We use third-party services to power Kre8 Clips:</p>
            <ul className="list-disc pl-6 space-y-1">
              <li><strong>Deepgram:</strong> For audio transcription and speaker diarization</li>
              <li><strong>Google Gemini:</strong> For AI-powered clip analysis</li>
              <li><strong>Google OAuth:</strong> For sign-in functionality</li>
              <li><strong>Vercel:</strong> For hosting and analytics</li>
            </ul>
            <p className="mt-3">These services have their own privacy policies.</p>
          </section>
          
          <section>
            <h2 className="text-xl font-semibold text-[#f5f4ef] mb-3">5. Cookies</h2>
            <p>We use cookies for authentication (refresh tokens stored in httpOnly cookies) and analytics. You can disable cookies, but some features may not work properly.</p>
          </section>
          
          <section>
            <h2 className="text-xl font-semibold text-[#f5f4ef] mb-3">6. Data Security</h2>
            <p>We implement industry-standard security measures to protect your data. However, no method of transmission over the internet is 100% secure.</p>
          </section>
          
          <section>
            <h2 className="text-xl font-semibold text-[#f5f4ef] mb-3">7. Your Rights</h2>
            <p>You have the right to:</p>
            <ul className="list-disc pl-6 mt-2 space-y-1">
              <li>Access your personal data</li>
              <li>Delete your account and associated data</li>
              <li>Export your data</li>
              <li>Opt out of analytics tracking</li>
            </ul>
          </section>
          
          <section>
            <h2 className="text-xl font-semibold text-[#f5f4ef] mb-3">8. Contact</h2>
            <p>For privacy-related questions, contact us through our website.</p>
          </section>
        </div>
      </div>
    </div>
  )
}
