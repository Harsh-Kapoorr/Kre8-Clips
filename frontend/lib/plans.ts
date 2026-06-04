export type PlanType = "free" | "byok" | "pro"

export interface Plan {
  id: PlanType
  name: string
  clips_limit: number | null
  price_usd: number | null
  features: string[]
  requires_keys: boolean
  badge?: string
}

export const PLANS: Record<PlanType, Plan> = {
  free: {
    id: "free",
    name: "Free",
    clips_limit: 1,
    price_usd: null,
    features: ["generate"],
    requires_keys: false,
  },
  byok: {
    id: "byok",
    name: "Bring Your Own Key",
    clips_limit: null,
    price_usd: 0,
    features: ["generate", "multi_ratio", "speaker_tracking", "captions", "smart_narrative"],
    requires_keys: true,
  },
  pro: {
    id: "pro",
    name: "Pro",
    clips_limit: 100,
    price_usd: 19,
    features: ["generate", "multi_ratio", "speaker_tracking", "captions", "smart_narrative", "api_access"],
    requires_keys: false,
    badge: "PRO",
  },
}

export function canUseFeature(plan: PlanType, feature: string): boolean {
  return PLANS[plan].features.includes(feature)
}

export function isLockedOut(plan: PlanType, clips_used: number): boolean {
  const p = PLANS[plan]
  if (plan === "free") return clips_used >= 1
  if (p.clips_limit === null) return false
  return clips_used >= p.clips_limit
}

export function getUpgradeMessage(plan: PlanType, clips_used: number): string | null {
  if (!isLockedOut(plan, clips_used)) return null
  if (plan === "free") return "You've used your free clip. Upgrade to Pro or BYOK to continue."
  return "You've reached your clip limit for this month."
}