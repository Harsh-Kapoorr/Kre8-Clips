# Editor System - Technology Comparison

## Overview

This document compares three technologies for building the post-generation video editor:
1. **Remotion** - React-based video rendering
2. **Editframe** - Cloud API video editing
3. **Hyperframes** - (to be researched)

## Comparison Matrix

| Feature | Remotion | Editframe | FFmpeg (Current) |
|---------|----------|-----------|------------------|
| **Cost** | Free (self-hosted) / $12/mo (cloud) | Pay-per-render | Free (built-in) |
| **Rendering** | Local/Cloud | Cloud only | Local |
| **Caption Animations** | Excellent (React) | Good | Basic |
| **Transitions** | Good | Good | Good |
| **Hook Detection** | Via AI + code | Via AI | Via code |
| **Complexity** | Medium | Low | Low |
| **Integration** | npm package | API key | Direct |
| **Custom Fonts** | Yes | Yes | Yes (complex) |
| **Export Speed** | Depends on hardware | Fast (cloud) | Depends on hardware |

## Remotion

### Pros
- Declarative React-based approach
- Excellent animation support
- Free for self-hosted
- Strong community (framecn/shadcn-labs)
- Familiar React dev experience

### Cons
- Self-hosted requires powerful hardware
- Cloud version costs money
- Separate rendering pipeline
- Bundle size

### Integration Path
```bash
npm install @remotion/cli @remotion/client
```

### Use Cases
- Caption rendering with complex animations
- Preview generation
- Complex transitions with keyframes

## Editframe

### Pros
- Professional cloud rendering
- No hardware required
- Simple API
- Built-in AI features
- Good for production

### Cons
- Per-render costs (~$0.05-0.10/minute)
- Cloud-dependent
- Limited customization
- Vendor lock-in

### Integration Path
```bash
npm install @editframe/editframe-js
```

### API Flow
1. User edits in browser
2. Send edit instructions to Editframe API
3. Editframe renders in cloud
4. Return video URL

## Hyperframes

### Status
- ✅ **RESOLVED - Recommended for Phase 2** (Apache 2.0, 22.1k stars, self-hosted, no per-render fees)

### What It Is
**Hyperframes** (https://github.com/heygen-com/hyperframes) is an open-source HTML-to-video framework from HeyGen.

| Attribute | Value |
|-----------|-------|
| License | Apache 2.0 |
| Stars | 22.1k |
| npm | `hyperframes` |
| Approach | HTML + CSS + GSAP animations → MP4 via headless Chrome + FFmpeg |

### Why It Fits Kre8 Clips's CapCut-Style Editor
1. **Free, self-hosted** — no per-render fees, no vendor lock-in
2. **Agent-native** — HTML is natural for LLMs to generate
3. **Frame-accurate GSAP** — unlike Remotion (wall-clock animations), Hyperframes seeks to frame/fps correctly
4. **Hyperframes Studio** — browser-based composition editor available
5. **Same source → preview and render** — what you see in browser is what renders

### Integration Path (Phase 2)
```bash
npm install hyperframes
```
- Create HTML composition from editor state (captions, clips, effects)
- Use `npx hyperframes preview` for live browser preview
- Use `npx hyperframes render --output clip.mp4` for final render
- Or use `@hyperframes/producer` programmatically

### Known Limitations
- Node.js 22+ required
- Requires headless Chrome + FFmpeg on render machine
- Newer project (less community than Remotion)
- No built-in cloud rendering (AWS Lambda only)

## FFmpeg (Current Backend)

### What We Have
- `core/clipper.py` - Basic clip generation with crop, transitions
- `core/caption_generator.py` - Caption burn-in
- `core/narrative.py` - Narrative assembly

### Extension Path
1. Create editor instruction API
2. Map editor actions to FFmpeg commands
3. Render on backend
4. Return output URL

## Recommended Architecture

### Phase 1: Quick Polish (Cheapest)
- Use existing FFmpeg backend
- Add editor UI for basic adjustments
- Canvas-based caption preview

### Phase 2: Enhanced Capabilities
- Add Remotion for caption animations
- Use for preview generation only
- Keep FFmpeg for final render (no extra cost)

### Phase 3: Cloud Rendering (Optional)
- Integrate Editframe for complex exports
- Pay per render for premium users

## Implementation Notes

### Caption Style System
All caption styles defined in `frontend/lib/editor/caption-engine.ts`:
- Font families (Google Fonts)
- Animation presets
- Preset styles (clean-bold, minimal-white, etc.)

### Editor Flow
1. User generates clip → sees results
2. Clicks "Edit" → opens editor at `/editor/[jobId]`
3. Makes adjustments (caption style, effects, transitions)
4. AI auto-suggestions for hooks, loops, transitions
5. Preview in real-time
6. Export (render via FFmpeg or Editframe)

### File Structure
```
frontend/
├── app/editor/[jobId]/page.tsx    # Main editor page
├── components/editor/
│   ├── caption-renderer.tsx        # Caption display/rendering
│   └── ...
├── lib/editor/
│   ├── caption-engine.ts          # Style definitions, fonts, animations
│   └── ...
├── store/useEditorStore.ts        # Editor state management
└── types/editor.ts                # TypeScript definitions
```

## Next Steps

1. **Test Remotion** - Create prototype caption renderer
2. **Test Editframe** - Set up API and test integration
3. **Research Hyperframes** - Find comparable open-source alternative
4. **Build intelligent backend** - Hook detection, loop points, transition suggestions
5. **Wire everything** - Connect UI to rendering pipeline