# Developer Guide — Understanding the Codebase

This guide walks through the key decision points and how to extend the interface.

## Understanding the Flow

### User Clicks the Sphere

```
User clicks VoiceSphere
    ↓
VoiceSphere.onClick() fires
    ↓
toggleCall() called (from useVapiCall)
    ↓
[Vapi Integration Point — SDK connects or disconnects]
    ↓
callStatus changes: idle → connecting → in-call
    ↓
uiState updates in MainVoicePage
    ↓
All child components re-render with new state
    ↓
VoiceSphere re-renders with new hue, animations
SpeakerIndicator appears
Transcript appears (if history exists)
```

### Agent Speaks

```
Vapi SDK receives speech_start event
    ↓
useVapiCall hook processes event
    ↓
activeSpeaker = 'assistant'
    ↓
VoiceSphere re-renders: hue → cyan (180)
    ↓
Outer glow pulse intensity increases
    ↓
Vapi SDK sends transcript_partial
    ↓
useVapiCall updates turns array
    ↓
VoiceTranscriptHistory re-renders with new text
    ↓
Vapi SDK sends transcript_final
    ↓
Turn is finalized, marked as complete
```

### Agent Calls a Tool: `show_video(videoId)`

```
Vapi SDK detects tool_use event
    ↓
useVapiCall hook processes event
    ↓
Checks if tool is 'show_video'
    ↓
onShowVideo(videoId) callback fired
    ↓
useMediaOverlay hook receives call
    ↓
Sets: isVideoOpen = true, activeVideo = video object
    ↓
MainVoicePage re-renders
    ↓
VoiceSphere scales down 50% (0.6s animation)
    ↓
VideoOverlayPlayer becomes visible with video
    ↓
User can close video or wait for agent to call hide_video()
```

### User Clicks TopBar Item (e.g., "Platform")

```
User clicks TopBar button
    ↓
onNavClick('Platform') fired
    ↓
setActiveBentoSection('Platform')
    ↓
MainVoicePage state updates
    ↓
TopBar re-renders with active indicator
    ↓
AnimatePresence mode="wait" detected
    ↓
InfoPanel animates in (y: -20 → 0, opacity: 0 → 1)
    ↓
Shows Platform content with 3 bullet points
    ↓
User can click "Close" button in InfoPanel
    ↓
setActiveBentoSection(null)
    ↓
InfoPanel animates out
```

## Key Hooks & Their Responsibilities

### useVapiCall
**Purpose**: Entire voice call lifecycle management

**Location**: `hooks/use-vapi-call.ts`

**What it does**:
1. Initializes Vapi SDK (requires env vars)
2. Manages call connect/disconnect
3. Processes speech events: start, partial transcript, final transcript
4. Handles tool-calls: checks tool name, fires callbacks
5. Maintains transcript history (anti-debouncing partial/final)
6. Updates call status state
7. Detects who's speaking (user vs. assistant)

**Integration Points** (search for `[Vapi Integration]` comments):
- SDK initialization block
- Tool-call handler switch statement
- Event listeners for speech/transcript

**How to extend**:
```typescript
// Add new tool handler
case 'my_custom_tool':
  console.log('Tool called with params:', data.toolCall.function.arguments);
  // Your custom logic here
  break;
```

### useMediaOverlay
**Purpose**: Video overlay state management

**Location**: `hooks/use-media-overlay.ts`

**What it does**:
1. Manages video visibility state
2. Stores active video object
3. Provides `showVideo(id)` callback
4. Provides `hideVideo()` callback
5. Maps video IDs to video registry

**How to extend**:
```typescript
// In use-media-overlay.ts, add custom handlers
const showVideo = (id: string) => {
  // Could add custom logic here, e.g., analytics
  setIsVideoOpen(true);
  // ... rest of logic
};
```

### useTranscriptHistory
**Purpose**: Clean transcript state management

**Location**: `hooks/use-transcript-history.ts`

**What it does**:
1. Merges partial and final transcripts
2. Prevents duplicate turns
3. Formats turns with timestamps
4. Returns clean turn array

## Component Responsibilities

### TopBar
- Renders fixed header with branding
- Shows nav items
- Calls `onNavClick` when item clicked
- Shows active indicator (layoutId for smooth animation)
- **No interaction with call state** — purely navigation

### InfoPanel
- Shows different content based on `section` prop
- Provides "Close" button to dismiss
- Animates in/out smoothly
- **Independent of call state** — can be open during call

### VoiceSphere
- Receives `uiState` with `callStatus` and `activeSpeaker`
- Renders 3D Orb with dynamic hue
- Shows outer glow pulse based on state
- Calls `onClick` prop to toggle call
- Scales based on `isVideoOpen` prop
- **Pure presentation** — all logic in parent

### SpeakerIndicator
- Shows "YOU" or "AI" based on `activeSpeaker`
- Only visible when `callStatus === "in-call"`
- No interaction
- **Pure feedback** — read-only

### VoiceTranscriptHistory
- Displays `turns` array
- Shows partial text with typing cursor
- Scrolls to bottom on new turns
- Only visible when `showTranscript` is true
- **Pure display** — no interactions

### VideoOverlayPlayer
- Shows video player when `isOpen` is true
- Calls `onClose` when user closes
- **Pure presentation** — all logic in parent

## State Flow Diagram

```
MainVoicePage (root state container)
│
├─ activeBentoSection (string | null)
│   ↓ triggers
│   TopBar & InfoPanel
│
├─ useVapiCall hook → uiState
│   ├─ callStatus
│   ├─ activeSpeaker
│   ├─ errorMessage
│   └─ turns (transcript history)
│       ↓ triggers
│       VoiceSphere, SpeakerIndicator, VoiceTranscriptHistory
│
└─ useMediaOverlay hook → mediaState
    ├─ isVideoOpen
    └─ activeVideo
        ↓ triggers
        VoiceSphere (scale), VideoOverlayPlayer
```

## Animation Patterns

### Smooth Entry
```typescript
initial={{ opacity: 0, y: -20 }}
animate={{ opacity: 1, y: 0 }}
exit={{ opacity: 0, y: -20 }}
transition={{ duration: 0.3, ease: 'easeOut' }}
```

### Scale Down
```typescript
animate={{ scale: isVideoOpen ? 0.5 : 1 }}
transition={{ duration: 0.6, ease: [0.32, 0.72, 0, 1] }}
```

### Pulsing Glow
```typescript
animate={{ opacity: [0.5, 0.9, 0.5], scale: [0.95, 1.1, 0.95] }}
transition={{ duration: 0.8, repeat: Infinity, ease: 'easeInOut' }}
```

**Key principle**: Durations are always explicit and smooth. Never use jarring easing like `cubic-in` or `linear` for visibility changes.

## Color System

All in `app/globals.css`:

```css
--background: #05060A          /* Deep dark background */
--primary: #7C3AED             /* Violet — idle, focus */
--accent-cyan: #22D3EE         /* Cyan — assistant active */
--foreground: #E8EAF0          /* Light gray text */
--muted-foreground: #5A6080    /* Dimmed text */
--card: #0C0D14                /* Card background */
--border: rgba(124, 58, 237, 0.12)  /* Soft violet border */
```

**Usage**:
- **Idle/focus**: Use `--primary` (#7C3AED)
- **Active/speaking**: Use `--accent-cyan` (#22D3EE)
- **Text**: Use `--foreground` or `--muted-foreground`
- **Borders**: Use `--border`
- **Cards**: Use `--card`

## Common Modifications

### Change the Voice Agent Prompt
→ Update your Vapi assistant configuration (not in this codebase)

### Add a New Info Section
1. Open `components/info-panel.tsx`
2. Add new key to `sections` object
3. Add to TopBar navItems in `top-bar.tsx`
4. Update ARCHITECTURE.md

### Customize Sphere Animations
→ Edit `components/voice-sphere.tsx` hue values or scale timings

### Adjust Background Intensity
→ Edit LiquidEther props in `main-voice-page.tsx`:
```typescript
autoIntensity={1.5}  // Lower = calmer
mouseForce={12}      // Lower = less reactive
```

### Add New Tool Handler
1. Open `hooks/use-vapi-call.ts`
2. Find `[Vapi Integration]` comment for tool-call section
3. Add new case to switch statement
4. Implement your logic

### Change Colors
→ Edit `app/globals.css` CSS variables

## Testing Tips

### Test Voice Call Without Vapi
Set `callStatus` manually in a dev component to simulate states:
```typescript
const [callStatus, setCallStatus] = useState('in-call');
```

### Test Video Overlay
Use the DEV toolbar at bottom (visible in dev mode):
- Click "show video" button to open overlay
- Click "hide video" button to close

### Test Animations
Slow down browser animations:
- DevTools → Rendering → Animations (slow down playback speed)

### Inspect Component State
Use React DevTools browser extension to inspect hook values and state changes in real-time.

## Debugging

### Voice Call Not Connecting
1. Check `.env.local` — both `NEXT_PUBLIC_VAPI_PUBLIC_KEY` and `NEXT_PUBLIC_VAPI_ASSISTANT_ID`
2. Open browser console for errors
3. Check network tab for failed requests
4. Verify Vapi API key is valid and not expired

### Transcript Not Updating
→ Check `turns` state in React DevTools
→ Add console.log in `useVapiCall` transcript handler
→ Verify `useTranscriptHistory` is anti-debouncing correctly

### Video Not Opening
→ Check if video ID is registered in `lib/video-registry.ts`
→ Verify agent is calling `show_video` tool with correct ID
→ Check `useMediaOverlay` state in React DevTools

### Animations Janky
→ Check Framer Motion transition settings (should be 0.3-0.4s)
→ Verify easing is `easeOut` not `linear` or `cubic-in`
→ Reduce LiquidEther resolution if GPU is bottleneck

## Next Steps

1. **Read ARCHITECTURE.md** for system overview
2. **Read README.md** for setup & features
3. **Explore `main-voice-page.tsx`** — main component with extensive comments
4. **Review `use-vapi-call.ts`** — Vapi integration points
5. **Customize colors in `app/globals.css`**
6. **Deploy to Vercel** — one-click from dashboard

Happy coding!
