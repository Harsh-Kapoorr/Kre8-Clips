export interface Word {
  word: string
  start: number
  end: number
  speaker: string | null
  confidence: number
}

export interface TranscriptEntry {
  start: number
  end: number
  text: string
  speaker: string | null
  words?: Word[]
}

export interface PlatformMatch {
  tiktok: number
  linkedin: number
  youtube_shorts: number
}

export interface AISegment {
  start: number
  end: number
  hook_score: number
  emotion_score: number
  curiosity_score: number
  authority_score: number
  story_score: number
  shareability_score: number
  clarity_score: number
  platform_match: PlatformMatch
  emotional_tone: string
  topic: string
  main_speaker: string
  contains_cta: boolean
  contains_hook_phrase: boolean
  viral_indicators: string[]
}

export interface EmotionalDensity {
  time: number
  score: number
  type: "spike" | "medium" | "low"
}

export interface AIAnalysis {
  segments: AISegment[]
  beat_timestamps: number[]
  emotional_density: EmotionalDensity[]
}

export interface ClipSegmentRef {
  start: string
  end: string
  segment_role: string
}

export interface ContextNeeded {
  start: string
  end: string
  reason: string
}

export interface GeneratedClip {
  id: string
  title: string
  segments: ClipSegmentRef[]
  priority: number
  hook_score: number
  emotional_tone: string
  main_speaker: string
  topic: string
  reason: string
  quote_potential: string
  hashtags: string[]
  context_needed?: ContextNeeded
}

export interface CreatorProfile {
  caption_style: string
  transition_style: string
  pacing_preference: string
  preferred_hook_types: string[]
  aspect_ratio_priority: string[]
  meme_usage: boolean
  broll_style: string
}

export interface ViralHeatmapEntry {
  time: number
  score: number
  type: string
}

export interface BrollSuggestion {
  time: number
  keyword: string
  suggestions: string[]
  confidence: number
}

export interface ClipVariation {
  variant_id: string
  style: string
  hook_start_override?: string
  context_included?: boolean
  emotional_climax_highlighted?: boolean
  removed_silence?: boolean
}

export interface PlatformExport {
  aspect_ratio: string
  caption_style: string
  cta_enabled: boolean
}

export interface MultiPlatformExports {
  [clipId: string]: {
    tiktok?: PlatformExport
    linkedin?: PlatformExport
    youtube_shorts?: PlatformExport
  }
}

export interface JobData {
  job_id: string
  url: string
  video_title: string
  video_duration: number
  created_at: string
  transcript: TranscriptEntry[]
  ai_analysis: AIAnalysis
  generated_clips: GeneratedClip[]
  creator_profile: CreatorProfile
  viral_heatmap: ViralHeatmapEntry[]
  broll_suggestions: BrollSuggestion[]
  clip_variations: { [clipId: string]: ClipVariation[] }
  multi_platform_exports: MultiPlatformExports
}