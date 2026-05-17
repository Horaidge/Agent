# Dzen.AI Voice Interface

A sophisticated, minimal voice-first AI agent interface built with Next.js, Framer Motion, and WebGL.

## Quick Start

1. **Install dependencies**
   ```bash
   pnpm install
   ```

2. **Set environment variables**
   Create `.env.local`:
   ```
   NEXT_PUBLIC_VAPI_PUBLIC_KEY=your_key
   NEXT_PUBLIC_VAPI_ASSISTANT_ID=your_assistant_id
   ```

3. **Run dev server**
   ```bash
   pnpm dev
   ```

4. **Open** `http://localhost:3000`

## Design Principles

### Minimalist Voice-First
- Central **Orb sphere** is the only primary UI
- Click to talk, naturally intuitive
- No navbar bloat, no landing sections
- Information panel slides in when requested

### Smooth, Calm Aesthetics
- Deep dark background (#05060A)
- Soft violet (#7C3AED) and cyan (#22D3EE) accents
- Gentle animations (0.3-0.4s transitions)
- No white flashes, no jarring interactions
- Fluid background responds to mouse with calm motion

### Clear State Feedback
- Sphere hue shifts by speaker (violet idle → cyan AI → purple user)
- Outer glow pulses based on activity (idle, connecting, speaking)
- Speaker indicator shows "YOU" or "AI" during calls
- Transcript visible during and after calls

## Architecture

**See `ARCHITECTURE.md` for detailed information.**

### Component Hierarchy
```
MainVoicePage (main.voice-page.tsx)
├── LiquidEther (background: z-0)
├── TopBar (header: z-20)
├── InfoPanel (info layer: z-15) ← shown when nav clicked
└── Main Content (z-10)
    ├── VoiceSphere (Orb component)
    ├── SpeakerIndicator
    ├── VoiceTranscriptHistory
    └── VideoOverlayPlayer
```

### Data Flow
1. **Click sphere** → `toggleCall()` → Vapi SDK connects
2. **Agent speaks** → Transcript updates, sphere glows cyan
3. **User speaks** → Speaker indicator shows, sphere pulses purple
4. **Agent calls `show_video`** → Video overlay opens, sphere scales down
5. **Click TopBar item** → InfoPanel opens with relevant content
6. **Click "Close"** → InfoPanel closes, returns to main mode

### State Management
- **activeBentoSection**: Which info panel is open (null, 'Platform', 'Use Cases', 'How It Works')
- **callStatus**: 'idle' | 'connecting' | 'in-call' | 'ended' | 'error'
- **activeSpeaker**: 'user' | 'assistant' | null
- **isVideoOpen**: Whether video overlay is visible

## Key Features

### Voice Calling (Vapi Integration)
- Real-time speech-to-text
- Agent speech generation
- Tool-call support (e.g., `show_video`, `hide_video`)
- Transcript history with partial updates
- Error handling and status display

### Interactive Background
- WebGL fluid simulation (LiquidEther)
- Responds to mouse movement
- Auto-animates when idle
- Soft, non-aggressive motion

### Responsive Information Layers
- **Platform**: Multi-agent system overview
- **Use Cases**: Enterprise applications
- **How It Works**: System architecture explanation
- Smooth in/out animations, distinct content per section

### Video Integration
- Agent can show videos via `show_video(videoId)` tool-call
- Inline HTML5 player with minimal controls
- Sphere scales down to accommodate video
- Agent can hide video with `hide_video()`

## Development

### Adding a New Tool-Call Handler
In `hooks/use-vapi-call.ts`, find the `[Vapi Integration]` section and add:

```typescript
case 'show_custom_ui':
  // Your custom logic
  break;
```

### Customizing Colors
Edit `app/globals.css`:
```css
--primary: #7C3AED;  /* Violet */
--accent-cyan: #22D3EE;  /* Cyan */
--background: #05060A;  /* Deep dark */
```

### Adjusting Animations
Global animation settings in `components/main-voice-page.tsx`:
- Duration: `0.3s` for micro-interactions, `0.4s` for panels
- Easing: Always `ease: 'easeOut'` for smooth, natural feel
- No jarring scale/opacity jumps

### Reducing Background Glow
In `components/main-voice-page.tsx`, tweak LiquidEther props:
```typescript
autoIntensity={1.5}  // Lower = calmer
mouseForce={12}      // Lower = less aggressive
```

## No White Flash on Click

All buttons have:
- `WebkitTapHighlightColor: 'transparent'`
- No bright `:focus` or `:active` backgrounds
- Soft violet/dark focus rings only
- Smooth scale animations instead of color flashes

## Vapi Configuration

### Required Env Vars
```
NEXT_PUBLIC_VAPI_PUBLIC_KEY=pk_xxx
NEXT_PUBLIC_VAPI_ASSISTANT_ID=a_xxx
```

### Tool Definitions in Vapi Dashboard
Define these tools in your Vapi assistant:

```
Tool: show_video
Parameters:
  - videoId (string): Video identifier

Tool: hide_video
Parameters: (none)
```

The frontend will automatically handle these calls via `useVapiCall` hook.

## Browser Support
- Chrome/Edge 90+
- Firefox 88+
- Safari 14+ (WebGL required for fluid background)

## Performance Tuning

### Reduce Frame Rate on Low-End Devices
```typescript
// In liquid-ether.tsx
resolution={0.5}  // Lower values reduce GPU load
```

### Disable Auto-Animation
```typescript
// In main-voice-page.tsx
autoDemo={false}  // Requires manual user interaction only
```

## Common Issues

### White Flash on Button Click
✓ Fixed — All buttons use `WebkitTapHighlightColor: 'transparent'` and soft focus styles.

### Jerky Animations
✓ Smooth transitions — All Framer Motion animations use `ease: 'easeOut'` with proper durations.

### Too Much Glow
✓ Reduced — Background `autoIntensity` lowered to 1.5, glow opacity capped at 0.35.

### Voice Call Not Working
→ Check `.env.local` has `NEXT_PUBLIC_VAPI_PUBLIC_KEY` and `NEXT_PUBLIC_VAPI_ASSISTANT_ID`
→ Open browser console for error messages
→ Ensure Vapi assistant is configured with required tools

## Files Structure

```
components/
  ├── top-bar.tsx              # Navigation header
  ├── info-panel.tsx           # Content panels (Platform/Use Cases/How It Works)
  ├── voice-sphere.tsx         # Main Orb sphere control
  ├── orb.tsx                  # WebGL 3D Orb rendering
  ├── liquid-ether.tsx         # WebGL fluid background
  ├── speaker-indicator.tsx    # Call status feedback
  ├── voice-transcript-history.tsx  # Conversation display
  ├── video-overlay-player.tsx # Video player
  └── main-voice-page.tsx      # Main page layout
hooks/
  ├── use-vapi-call.ts         # Vapi SDK integration
  ├── use-media-overlay.ts     # Video overlay state
  └── use-transcript-history.ts # Transcript management
app/
  ├── page.tsx                 # Entry point
  ├── layout.tsx               # Root layout
  └── globals.css              # Design tokens & theme
```

## Future Enhancements

- Audio-reactive sphere visualization
- Multi-turn context awareness
- Sentiment/emotion detection in transcript
- Customizable assistant themes
- Mobile voice input support
- Dark/light mode toggle
- Analytics integration

## License

MIT

## Support

For issues or questions about Vapi integration, see [Vapi Documentation](https://docs.vapi.ai).
