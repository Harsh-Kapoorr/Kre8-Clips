export type JobStatus = "pending" | "running" | "done" | "error"

export interface AISegmentScores {
  hook_score: number
  emotion_score: number
  curiosity_score: number
  authority_score: number
  story_score: number
  shareability_score: number
  clarity_score: number
  platform_match: {
    tiktok: number
    linkedin: number
    youtube_shorts: number
  }
  emotional_tone: string
  topic: string
  main_speaker: string
  contains_cta: boolean
  contains_hook_phrase: boolean
  viral_indicators: string[]
}

export interface AIGramSegment {
  start: number
  end: number
  scores: AISegmentScores
  beat_synced: boolean
}

export interface EmotionalDensity {
  time: number
  score: number
  type: "spike" | "medium" | "low"
}

export interface TranscriptSegment {
  start: number
  end: number
  text: string
  speaker: string | null
  words?: Array<{
    word: string
    start: number
    end: number
    speaker: string | null
    confidence: number
  }>
}

export interface ClipSegment {
  start: string
  end: string
  start_seconds: number
  end_seconds: number
  duration: number
  segment_role: "hook" | "body" | "payoff"
  viral_potential: number
  opening_strength: number
  closing_strength: number
}

export interface ContextReference {
  start: string
  end: string
  reason: string
}

export interface GeneratedClip {
  id: string
  title: string
  original_title: string
  priority: number
  hook_score: number
  emotional_tone: string
  main_speaker: string
  topic: string
  reason: string
  quote_potential: string
  hashtags: string[]
  segments: ClipSegment[]
  reliability_score?: number
  context_needed?: ContextReference
  output_path: string
  duration_seconds: number
  viral_share_prob?: number
  viral_save_prob?: number
  viral_comment_prob?: number
  viral_composite?: number
  viral_model_version?: string
  boundary_confidence?: number
  boundary_start_reason?: string
  boundary_end_reason?: string
  render_error?: string
  render_traceback?: string
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

export interface BrollSuggestion {
  time: number
  keyword: string
  suggestions: string[]
  confidence: number
}

export interface ClipVariation {
  variant_id: string
  style: "aggressive_hook" | "storytelling" | "emotional" | "fast_paced"
  hook_start_override?: string
  context_included: boolean
  emotional_climax_highlighted: boolean
  removed_silence: boolean
}

export interface PlatformExportConfig {
  aspect_ratio: string
  caption_style: string
  cta_enabled: boolean
  title_modifier: string
  hashtag_count: number
}

export interface Job {
  id: string
  url: string
  status: JobStatus
  progress: number
  step: string
  step_detail: string
  output_files: string[]
  error?: string
  started_at: string
  ended_at?: string
  options: GenerationOptions
  // Timing fields emitted by utils/progress.py and propagated by the API
  // route / SSE stream. ``eta_s`` is null when too little progress has been
  // observed to extrapolate; the UI must treat null as "don't show".
  eta_s?: number | null
  elapsed_s?: number | null
  eta_capped?: boolean
  // Wall-clock time (ms since epoch) when ``eta_s`` was sampled. Lets the UI
  // tick the displayed remaining time down between sidecar updates instead of
  // freezing on a stale value while a long step is in flight.
  eta_reported_at?: number
  video_title?: string
  video_duration?: number
  transcript?: TranscriptSegment[]
  ai_analysis?: {
    segments: AIGramSegment[]
    beat_timestamps: number[]
    emotional_density: EmotionalDensity[]
  }
  generated_clips?: GeneratedClip[]
  creator_profile?: CreatorProfile | null
  viral_heatmap?: EmotionalDensity[]
  broll_suggestions?: BrollSuggestion[]
  clip_variations?: Record<string, ClipVariation[]>
  clip_multi_platform_exports?: Record<string, {
    tiktok: PlatformExportConfig
    linkedin: PlatformExportConfig
    youtube_shorts: PlatformExportConfig
  }>
}

export interface GenerationOptions {
  prompt: string
  aspect_ratio: "9:16" | "16:9" | "1:1" | "4:5"
  min_duration: number
  max_duration: number
  num_clips: number
  speaker_tracking: boolean
  captions: boolean
  caption_style?: "pop" | "fade" | "typewriter" | "none"
  narrative: boolean
  smart_narrative: boolean
}

export interface Clip {
  id: string
  title: string
  priority: number
  hook_score: number
  reliability_score?: number
  duration_seconds: number
  emotional_tone: string
  main_speaker: string
  topic: string
  segments: ClipSegment[]
  quote_potential?: string
  hashtags?: string[]
  output_file?: string
}

export interface SSEEvent {
  type: "progress" | "complete" | "error" | "heartbeat"
  data: ProgressData | CompleteData | ErrorData
}

export interface ProgressData {
  step: string
  progress: number
  step_detail: string
  // Timing fields written by utils/progress.py. eta_s is null when too little
  // progress has been observed to extrapolate a meaningful remaining time.
  eta_s?: number | null
  elapsed_s?: number | null
  eta_capped?: boolean
  eta_reported_at?: number
}

export interface CompleteData {
  status: "done"
  output_files: string[]
}

export interface ErrorData {
  status: "error"
  error: string
}

