# Dzen.AI Voice Interface — Architecture

## Overview
This is a **voice-first AI interface** for Dzen.AI. The primary interaction is a central **Orb sphere** that users click to talk to an AI agent. The interface is minimal, sophisticated, and focused on voice as the primary modality.

---

## UI Layer Structure

### 1. **LiquidEther Background** (`components/liquid-ether.tsx`)
- WebGL-based fluid simulation that responds to mouse movement
- Uses soft violet (#7C3AED) and cyan (#22D3EE) with deep dark background
- Auto-animates when idle, interactive on hover
- **Config**: `mouseForce=12`, `autoIntensity=1.5` for calm, non-aggressive animation
- **Purpose**: Creates ambient, interactive atmosphere without distraction

### 2. **TopBar** (`components/top-bar.tsx`)
- Fixed header with "Dzen.AI" branding
- Navigation links: Platform, Use Cases, How It Works
- Active state indicator (soft violet underline)
- **No white focus/tap flashes** — uses transparent highlight colors
- **Purpose**: Main entry point for info sections

### 3. **InfoPanel** (`components/info-panel.tsx`)
- **Distinct content per section:**
  - **Platform**: Multi-agent system, knowledge base, agent capabilities
  - **Use Cases**: Enterprise scenarios, customer support, document processing
  - **How It Works**: Router Agent, Knowledge Agent, Skill Agent, RAG architecture
- Animates in/out smoothly with 0.3s duration
- Has explicit "Close" button to return to main mode
- **Purpose**: Educational layer explaining Dzen.AI

### 4. **VoiceSphere** (`components/voice-sphere.tsx`)
- Central interactive element — **THE main UI**
- Renders using **Orb component** (WebGL-based 3D sphere)
- Dynamic hue shifting based on speaker (violet idle → cyan assistant → purple user)
- Responds to call state: idle, connecting, in-call
- Scales down when video overlay is open
- **Purpose**: Primary interaction point for voice calls

### 5. **SpeakerIndicator** (`components/speaker-indicator.tsx`)
- Shows who is speaking: "YOU" or "AI"
- Only visible during active call
- Minimalist, non-intrusive design
- **Purpose**: Call flow feedback

### 6. **VoiceTranscriptHistory** (`components/voice-transcript-history.tsx`)
- Displays conversation turns (user → AI)
- Shows partial transcript during speech with cursor
- Scrollable history
- Only visible when call is active or history exists
- **Purpose**: Conversation visibility and debugging

### 7. **VideoOverlayPlayer** (`components/video-overlay-player.tsx`)
- Inline HTML5 video player
- Opens ONLY when agent calls `tool_use.show_video(videoId)`
- Minimal controls, close button
- Scales sphere down when open
- **Purpose**: Video results from agent tool-calls

---

## State Management

### Main State (`MainVoicePage`)
```typescript
activeBentoSection: string | null  // Controls which info panel is open
// Values: null | 'Platform' | 'Use Cases' | 'How It Works'
```

### Call State (from `useVapiCall` hook)
```typescript
callStatus: 'idle' | 'connecting' | 'in-call' | 'ended' | 'error'
activeSpeaker: 'user' | 'assistant' | null
errorMessage: string | null
turns: Turn[]  // Transcript history
```

### Media State (from `useMediaOverlay` hook)
```typescript
isVideoOpen: boolean
activeVideo: Video | null
videoId: string | null
```

---

## Data Flow

### User Clicks Sphere
1. Click → `VoiceSphere.onClick()` → `toggleCall()`
2. `useVapiCall` hook manages Vapi SDK connection
3. Call status changes: `idle` → `connecting` → `in-call`
4. Sphere hue shifts from violet to cyan/purple

### Agent Speaks
1. Vapi events: `speech-start` → `transcript-partial` → `transcript-final`
2. `useVapiCall` updates state and stores turns
3. SpeakerIndicator shows "AI", transcript updates
4. Sphere pulses with cyan glow

### User Speaks
1. Browser captures audio, sends to Vapi
2. Speech detection: `activeSpeaker = 'user'`
3. Sphere shows purple tint, transaction visual feedback
4. Transcript shows partial user input with cursor

### Agent Calls Tool: `show_video(videoId)`
1. Vapi tool-call event received by `useVapiCall`
2. `onShowVideo(videoId)` callback fired
3. `useMediaOverlay` hook opens video overlay
4. Sphere scales down 50%, video appears inline
5. User can close video or agent calls `hide_video()`

### User Clicks TopBar Item (Platform, Use Cases, etc.)
1. Click → `setActiveBentoSection('Platform')`
2. `InfoPanel` animates in with relevant content
3. TopBar shows active indicator under selected item
4. User can click "Close" or TopBar item again to dismiss

### Return to Main Mode
1. Click "Close" in InfoPanel → `setActiveBentoSection(null)`
2. InfoPanel animates out
3. Sphere returns to center focus
4. TopBar indicator removes

---

## Animation Philosophy

- **Duration**: 0.3s for micro-interactions, 0.4s for panel transitions
- **Easing**: Smooth ease-out curves, no jarring scale/opacity changes
- **Layers**: Smooth cascading of component animations
- **No Flash**: All focus/tap states use soft, dark colors (transparent/muted)
- **Smooth Transitions**: All layout changes use Framer Motion for physics-based smoothness

---

## Color Palette

- **Background**: `#05060A` (almost black)
- **Primary Violet**: `#7C3AED` (idle state, focus accent)
- **Accent Cyan**: `#22D3EE` (assistant speaking, active accent)
- **Text**: `#E8EAF0` (light gray-white)
- **Muted**: `rgba(232, 234, 240, 0.4)` (secondary text)
- **Border**: `rgba(124, 58, 237, 0.12)` (soft violet border)
- **Glow**: Very subtle (max opacity 0.35 for violet, 0.2 for cyan)

---

## Hooks & Integration

### `useVapiCall(options)` (`hooks/use-vapi-call.ts`)
- **Manages**: Vapi SDK initialization, call lifecycle, transcript events
- **Provides**: `uiState`, `turns`, `toggleCall()` function
- **Callbacks**: `onShowVideo`, `onHideVideo` for tool-calls
- **Setup**: Requires `NEXT_PUBLIC_VAPI_PUBLIC_KEY` and `NEXT_PUBLIC_VAPI_ASSISTANT_ID` env vars
- **Marked sections**: Search for `[Vapi Integration]` comment to see where to connect SDK

### `useTranscriptHistory()` (`hooks/use-transcript-history.ts`)
- Manages partial ↔ final transcript merging
- Prevents duplicate turns in history
- Returns formatted transcript turns

### `useMediaOverlay()` (`hooks/use-media-overlay.ts`)
- Manages video overlay state and visibility
- `showVideo(id)` — opens video, sets active video
- `hideVideo()` — closes overlay
- Returns `mediaState` and callbacks

---

## Key Implementation Notes

### No White Flash on Click
- `WebkitTapHighlightColor: 'transparent'` on all buttons
- Focus styles use soft violet/dark backgrounds, never white or bright colors
- Tap animations use `scale` instead of flashing backgrounds

### Smooth Animations
- All transitions use `ease: 'easeOut'` or Framer Motion presets
- Duration never jarring (min 0.25s, typical 0.3-0.4s)
- Layout animations use `layoutId` for smooth reflow

### Reduced Glow
- LiquidEther: `mouseForce=12`, `autoIntensity=1.5` (vs. previous 18 and 3)
- Card glows: max opacity 0.35 (violet) and 0.2 (cyan)
- Border glows: `rgba(..., 0.12)` very subtle
- No pulsing halos or aggressive lighting

### Architecture Clarity
- Each component has a clear purpose documented in this file
- Hooks are self-contained and composable
- State flows top-down from `MainVoicePage`
- Tool-calls and events are handled explicitly

---

## Environment Variables Required

```
NEXT_PUBLIC_VAPI_PUBLIC_KEY=your_key_here
NEXT_PUBLIC_VAPI_ASSISTANT_ID=your_assistant_id_here
```

These enable the Vapi voice agent functionality. Without them, the sphere works visually but cannot make actual calls.

---

## Future Extension Points

1. **Audio Reactive Sphere**: Connect Web Audio API to sphere hue/scale
2. **More Tool-Calls**: Add additional tool handlers (e.g., `show_text`, `navigate_to`)
3. **Mobile Layout**: Add responsive top bar nav drawer
4. **Theme Toggle**: Add light/dark mode picker
5. **Multi-Turn Context**: Enhance transcript with sentiment, entities, etc.

