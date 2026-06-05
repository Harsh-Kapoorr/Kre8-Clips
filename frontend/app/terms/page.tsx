export default function TermsPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-[#f5f4ef] px-6 py-20">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-4xl font-serif mb-8">Terms of Service</h1>
        <p className="text-sm text-[#f5f4ef]/60 mb-8">Last updated: June 2026</p>
        
        <div className="space-y-6 text-[#f5f4ef]/80 leading-relaxed">
          <section>
            <h2 className="text-xl font-semibold text-[#f5f4ef] mb-3">1. Acceptance of Terms</h2>
            <p>By accessing or using Kre8 Clips, you agree to be bound by these Terms of Service. If you do not agree, do not use the service.</p>
          </section>
          
          <section>
            <h2 className="text-xl font-semibold text-[#f5f4ef] mb-3">2. Description of Service</h2>
            <p>Kre8 Clips transforms long YouTube videos into short, shareable clips using AI analysis, speaker tracking, and automated editing.</p>
          </section>
          
          <section>
            <h2 className="text-xl font-semibold text-[#f5f4ef] mb-3">3. User Accounts</h2>
            <p>You are responsible for maintaining the confidentiality of your account credentials. You agree to accept responsibility for all activities under your account.</p>
          </section>
          
          <section>
            <h2 className="text-xl font-semibold text-[#f5f4ef] mb-3">4. Acceptable Use</h2>
            <p>You may not use Kre8 Clips to:</p>
            <ul className="list-disc pl-6 mt-2 space-y-1">
              <li>Create content that infringes on intellectual property rights</li>
              <li>Generate content for illegal purposes</li>
              <li>Attempt to gain unauthorized access to the service</li>
              <li>Interfere with the proper functioning of the service</li>
            </ul>
          </section>
          
          <section>
            <h2 className="text-xl font-semibold text-[#f5f4ef] mb-3">5. Content Ownership</h2>
            <p>You retain ownership of content you create using Kre8 Clips. However, you are responsible for ensuring you have the right to clip and share any content processed by our service.</p>
          </section>
          
          <section>
            <h2 className="text-xl font-semibold text-[#f5f4ef] mb-3">6. Limitation of Liability</h2>
            <p>Kre8 Clips is provided "as is" without warranties. We are not liable for any damages arising from your use of the service.</p>
          </section>
          
          <section>
            <h2 className="text-xl font-semibold text-[#f5f4ef] mb-3">7. Changes to Terms</h2>
            <p>We may update these terms at any time. Continued use of the service after changes constitutes acceptance of the new terms.</p>
          </section>
          
          <section>
            <h2 className="text-xl font-semibold text-[#f5f4ef] mb-3">8. Contact</h2>
            <p>For questions about these terms, contact us through our website.</p>
          </section>
        </div>
      </div>
    </div>
  )
}
