# Next.js hero section with animated rotating object in ASCII style

A beautiful Next.js project boilerplate with a hero page WebGL demo featuring a 3D GLTF model rendered with React Three Fiber and post-processed into an animated ASCII art effect using custom shaders.

## Features

- **Real-time ASCII conversion** - Custom GLSL shader converts 3D scene to ASCII art
- **Interactive 3D model** - Drag to rotate, hover to zoom
- **Post-processing effects** - CRT-style scanlines, vignette, and glow effects
- **Mouse-reactive** - Mouse position affects glow and visual effects
- **Responsive** - Works on desktop and mobile devices

## Tech Stack

- [Next.js](https://nextjs.org/) - React framework
- [React Three Fiber](https://docs.pmnd.rs/react-three-fiber) - React renderer for Three.js
- [Three.js](https://threejs.org/) - 3D graphics library
- [Postprocessing](https://github.com/pmndrs/postprocessing) - Post-processing effects
- [@react-three/drei](https://github.com/pmndrs/drei) - Useful helpers for R3F
- [TypeScript](https://www.typescriptlang.org/) - Type safety

## Getting Started

### Prerequisites

- Node.js 18+ 
- npm, yarn, pnpm, or bun

### Installation

```bash
# Clone the repository
git clone https://github.com/egorshest/webgl-ascii-hero.git
cd webgl-ascii-hero

# Install dependencies
npm install

# Run the development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to see the effect.

## Project Structure

```
webgl-ascii-hero/
├── app/
│   ├── layout.tsx      # Root layout
│   ├── page.tsx        # Home page
│   └── globals.css     # Global styles
├── components/
│   ├── hero.tsx        # Hero component (main page)
│   ├── effect-scene.tsx # 3D scene setup
│   └── ascii-effect.tsx # ASCII post-processing shader
└── public/
    └── models/
        └── user-model.glb   # 3D model (GLTF format) - DEMO ONLY, replace with your own
```

## Customization

### Adding Your Own 3D Model

⚠️ **Important:** The included `user-model.glb` model is for **demonstration purposes only**. Please remove it and use your own model.

**Steps to add your own model:**

1. **Download a GLB model** from any source (make sure you have the rights to use it):
   - [Sketchfab](https://sketchfab.com/3d-models?features=downloadable&sort_by=-likeCount&q=cc0) - Filter by CC0 license for free models
   - [Poly Haven](https://polyhaven.com/models) - CC0 models
   - [glTF Sample Models](https://github.com/KhronosGroup/glTF-Sample-Models) - Various licenses
   - Or create your own using Blender, Maya, etc.

2. **Replace the demo model** with your own GLB file:
   ```bash
   # Simply replace the demo file with your own model
   # Make sure your file is named "user-model.glb" and placed in public/models/
   # The code already references "/models/user-model.glb", so no code changes needed!
   ```

3. **Adjust the scale** if needed in `components/effect-scene.tsx` (line 124):
   ```tsx
   <UserModel scale={8} />  // Change the number to adjust size
   ```

4. **Update the component name** from `UserModel` to match your model (optional, for clarity).

### Adjust ASCII Effect

Modify the `AsciiEffect` props in `components/effect-scene.tsx`:

```tsx
<AsciiEffect
  cellSize={9}              // Size of ASCII cells
  invert={true}             // Invert brightness
  color={true}              // Enable color
  characterSet="terminal"   // Character set
  volumeShading={true}      // 3D depth effect
  tintColor="#917AFF"       // Tint color
  postfx={{
    contrastAdjust: 1.8,    // Contrast
    brightnessAdjust: 0,   // Brightness
  }}
/>
```

### Modify Scene Lighting

Edit lighting in `components/effect-scene.tsx`:

```tsx
<ambientLight intensity={0.08} />
<directionalLight position={[2, 3.5, 6]} intensity={6} />
<directionalLight position={[-2, 1.5, 4]} intensity={0.35} />
```

## Building for Production

```bash
npm run build
npm start
```

## License

MIT License - feel free to use this project for your own purposes.

## Credits

- ASCII shader inspiration: Classic terminal art and CRT displays
- Built with [React Three Fiber](https://docs.pmnd.rs/react-three-fiber), [Three.js](https://threejs.org/), and [Next.js](https://nextjs.org/)
