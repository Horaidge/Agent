# Quick Reference — Key Concepts

## Component Tree

```
MainVoicePage
├── LiquidEther (background, z-0)
├── TopBar (header, z-20)
│   └── onNavClick → sets activeBentoSection
├── InfoPanel (z-15, when activeBentoSection !== null)
│   └── onClose → clears activeBentoSection
└── Main Content (z-10)
    ├── VoiceSphere
    │   └── onClick → toggleCall() from useVapiCall
    ├── SpeakerIndicator (visible in-call)
    ├── VoiceTranscriptHistory (visible in-call or with history)
    └── VideoOverlayPlayer (visible when isVideoOpen)
```

## State Variables

| Variable | Type | Values | Managed By |
|----------|------|--------|-----------|
| `activeBentoSection` | string \| null | null, 'Platform', 'Use Cases', 'How It Works' | useState in MainVoicePage |
| `callStatus` | string | 'idle', 'connecting', 'in-call', 'ended', 'error' | useVapiCall |
| `activeSpeaker` | string \| null | null, 'user', 'assistant' | useVapiCall |
| `isVideoOpen` | boolean | true, false | useMediaOverlay |
| `turns` | Turn[] | [...] | useVapiCall (via useTranscriptHistory) |

## Key Events

### Click Sphere
```
onClick → toggleCall() → Vapi SDK → callStatus changes
```

### Click TopBar Item
```
onClick → onNavClick(item) → setActiveBentoSection(item) → InfoPanel appears
```

### Agent Speaks
```
Vapi event → useVapiCall hook → activeSpeaker = 'assistant' → Sphere hue cyan
```

### Agent Shows Video
```
Vapi tool_use 'show_video' → onShowVideo(id) → isVideoOpen = true → VoiceSphere scales down
```

## Colors

| Name | Hex | Usage |
|------|-----|-------|
| Background | `#05060A` | Deep dark |
| Primary (Violet) | `#7C3AED` | Idle, focus, accents |
| Accent (Cyan) | `#22D3EE` | Active, assistant speaking |
| Foreground | `#E8EAF0` | Primary text |
| Muted | `#5A6080` | Secondary text |
| Card | `#0C0D14` | Card backgrounds |
| Border | `rgba(124,58,237,0.12)` | Subtle violet borders |

## Animation Durations

| Action | Duration | Easing |
|--------|----------|--------|
| Button hover | 0.25s | easeOut |
| Panel in/out | 0.3s | easeOut |
| Sphere scale | 0.6s | cubic-bezier(0.32, 0.72, 0, 1) |
| Fade transitions | 0.3-0.4s | easeOut |
| Pulse/glow | 0.8-1.2s | easeInOut |

## Hooks

### useVapiCall
```typescript
const { uiState, turns, toggleCall } = useVapiCall({
  onShowVideo: showVideo,    // callback when agent calls show_video
  onHideVideo: hideVideo     // callback when agent calls hide_video
});

// uiState = { callStatus, activeSpeaker, errorMessage }
// turns = [{ id, text, role: 'user'|'assistant', complete }]
// toggleCall() = function to start/stop call
```

### useMediaOverlay
```typescript
const { mediaState, showVideo, hideVideo } = useMediaOverlay();

// mediaState = { isVideoOpen, activeVideo }
// showVideo(id) = function to open video with id
// hideVideo() = function to close video
```

### useTranscriptHistory
```typescript
const { turns } = useTranscriptHistory();
// Manages partial↔final merging
```

## Focus States (No White Flash)

```typescript
// All buttons have:
WebkitTapHighlightColor: 'transparent'
focus:outline-none
focus-visible:ring-2 ring-[#7C3AED]  // Soft violet only
```

## Adding New Tool Handler

1. Open `hooks/use-vapi-call.ts`
2. Find `[Vapi Integration]` comment in tool-call handler
3. Add case:
```typescript
case 'my_tool':
  console.log('Tool data:', data.toolCall.function.arguments);
  // Your logic here
  break;
```

## Accessing Environment Variables

```typescript
// Required for Vapi integration:
NEXT_PUBLIC_VAPI_PUBLIC_KEY
NEXT_PUBLIC_VAPI_ASSISTANT_ID

// Set in .env.local (dev) or Vercel settings (prod)
```

## File Locations

| What | Where |
|------|-------|
| Main layout | `components/main-voice-page.tsx` |
| Navigation | `components/top-bar.tsx` |
| Info panels | `components/info-panel.tsx` |
| Voice sphere | `components/voice-sphere.tsx` |
| Vapi integration | `hooks/use-vapi-call.ts` |
| Video overlay | `hooks/use-media-overlay.ts` |
| Design tokens | `app/globals.css` |
| Architecture docs | `ARCHITECTURE.md` |
| Developer guide | `DEVELOPER_GUIDE.md` |

## Common Tasks

### Change Primary Color
```css
/* app/globals.css */
--primary: #your-color;
```

### Adjust Background Glow
```typescript
// components/main-voice-page.tsx
<LiquidEther
  autoIntensity={1.5}  // Lower = calmer
  mouseForce={12}      // Lower = less reactive
/>
```

### Add New Info Section
1. Edit `components/info-panel.tsx` → add to `sections` object
2. Edit `components/top-bar.tsx` → add to `navItems` array
3. Test by clicking TopBar

### Debug Call State
```typescript
// Add to MainVoicePage during development
console.log('[DEBUG] callStatus:', callStatus);
console.log('[DEBUG] activeSpeaker:', activeSpeaker);
console.log('[DEBUG] turns:', turns);
```

### Slow Down Animations
```typescript
// DevTools → Rendering → Animations → set playback speed to 25%
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Call not connecting | Check env vars: `NEXT_PUBLIC_VAPI_PUBLIC_KEY`, `NEXT_PUBLIC_VAPI_ASSISTANT_ID` |
| Janky animations | Ensure duration is 0.3-0.4s, easing is `easeOut` |
| White flash on click | Verify `WebkitTapHighlightColor: 'transparent'` in button styles |
| Too bright background | Reduce `autoIntensity` in LiquidEther config |
| Transcript not updating | Check `useVapiCall` tool-call handler, verify turns array updates |
| Video not opening | Verify video ID registered in tool handler, check `useMediaOverlay` state |

## Dev-Only Features

- **DEV toolbar** at bottom (shows in development mode)
  - "show video" button — test video overlay
  - "hide video" button — close video
  - Only visible when `NODE_ENV === 'development'`

## Performance Tips

- Reduce LiquidEther resolution for low-end devices: `resolution={0.3}`
- Disable auto-animation: `autoDemo={false}`
- Check GPU usage: DevTools → Rendering → check for slowdown

## Documentation

- **ARCHITECTURE.md** — Full system design
- **README.md** — Setup & features
- **DEVELOPER_GUIDE.md** — Flows & modification guide
- **IMPROVEMENTS.md** — What was changed
- **QUICK_REFERENCE.md** — This file

---

**Start here**: Read ARCHITECTURE.md, then explore components with comments.
