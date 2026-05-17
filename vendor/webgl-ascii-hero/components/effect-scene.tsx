"use client"

import { Suspense, useEffect, useMemo, useRef, useState } from "react"
import type { ComponentPropsWithoutRef } from "react"
import { Canvas, useFrame, useThree } from "@react-three/fiber"
import { EffectComposer } from "@react-three/postprocessing"
import { Environment, OrbitControls, useGLTF } from "@react-three/drei"
import { Group, Mesh, MeshStandardMaterial, Vector2 } from "three"
import { AsciiEffect } from "./ascii-effect"

function UserModel(props: ComponentPropsWithoutRef<"group">) {
  const { scene } = useGLTF("/models/user-model.glb")

  const basicMat = useMemo(
    () =>
      new MeshStandardMaterial({
        color: "#917AFF",
        roughness: 0.12, // Lower = sharper highlights, more contrast
        metalness: 0,
        flatShading: false,
      }),
    []
  )

  useEffect(() => {
    scene.traverse((obj) => {
      const mesh = obj as Mesh
      if ((mesh as any).isMesh) {
        const originalMat = (mesh as any).material
        // Dispose original material if it exists and is different
        if (originalMat && originalMat.dispose && originalMat !== basicMat) {
          try {
            originalMat.dispose()
          } catch (e) {
            // Ignore disposal errors (context might be lost)
          }
        }
        ;(mesh as any).material = basicMat
      }
    })

    return () => {
      // Cleanup: dispose material when component unmounts
      // Wrap in try-catch to handle context loss gracefully
      try {
        if (basicMat && typeof basicMat.dispose === "function") {
          basicMat.dispose()
        }
      } catch (e) {
        // Ignore disposal errors (context might be lost or already disposed)
      }
    }
  }, [scene, basicMat])

  return <primitive object={scene} {...props} />
}

useGLTF.preload("/models/user-model.glb")

const AUTO_ROTATE_SPEED = 0.4
const HOVER_SPIN_MULTIPLIER = 2
const TILT_FORWARD = 0.3
const TILT_LEFT = -0.08

const CAMERA_BASE_Z = 4.5
const CAMERA_ZOOMED_Z = CAMERA_BASE_Z / 1.1

function DraggableUserModel({ isHovered = false }: { isHovered?: boolean }) {
  const groupRef = useRef<Group>(null)
  const [rotation, setRotation] = useState({ x: 0, y: 0 })
  const isDragging = useRef(false)
  const lastPointer = useRef({ x: 0, y: 0 })
  const autoY = useRef(0)

  const spinSpeed = isHovered ? AUTO_ROTATE_SPEED * HOVER_SPIN_MULTIPLIER : AUTO_ROTATE_SPEED

  useFrame((_, delta) => {
    if (!groupRef.current) return
    if (!isDragging.current) {
      autoY.current += delta * spinSpeed
    }
    groupRef.current.rotation.x = rotation.x + TILT_FORWARD
    groupRef.current.rotation.y = rotation.y + autoY.current
    groupRef.current.rotation.z = TILT_LEFT
  })

  useEffect(() => {
    const container = document.querySelector("[data-model-canvas-container]")
    if (!container) return

    const onPointerDown = (e: Event) => {
      const pe = e as PointerEvent
      if ((pe.target as HTMLElement).closest("canvas")) {
        isDragging.current = true
        lastPointer.current = { x: pe.clientX, y: pe.clientY }
      }
    }

    const onPointerMove = (e: Event) => {
      if (!isDragging.current) return
      const pe = e as PointerEvent
      const dx = (pe.clientX - lastPointer.current.x) * 0.005
      const dy = (pe.clientY - lastPointer.current.y) * 0.005
      lastPointer.current = { x: pe.clientX, y: pe.clientY }
      setRotation((r) => ({ x: r.x - dy, y: r.y + dx }))
    }

    const onPointerUp = () => {
      isDragging.current = false
    }

    container.addEventListener("pointerdown", onPointerDown as EventListener)
    window.addEventListener("pointermove", onPointerMove as EventListener)
    window.addEventListener("pointerup", onPointerUp)
    return () => {
      container.removeEventListener("pointerdown", onPointerDown as EventListener)
      window.removeEventListener("pointermove", onPointerMove as EventListener)
      window.removeEventListener("pointerup", onPointerUp)
    }
  }, [])

  return (
    <group ref={groupRef} position={[0, -0.8, 0]}>
      <UserModel scale={3} />
    </group>
  )
}

function CameraHoverZoom({ isHovered = false }: { isHovered?: boolean }) {
  const { camera } = useThree()
  useFrame(() => {
    const targetZ = isHovered ? CAMERA_ZOOMED_Z : CAMERA_BASE_Z
    camera.position.z += (targetZ - camera.position.z) * 0.08
    camera.position.x += (0 - camera.position.x) * 0.08
    camera.position.y += (0 - camera.position.y) * 0.08
  })
  return null
}

/** Mounts EffectComposer only after the first frame so WebGL context exists (avoids postprocessing addPass reading null .alpha) */
function SceneWithDelayedComposer({
  resolution,
  mousePos,
  enableZoom = true,
  isHovered = false,
}: {
  resolution: Vector2
  mousePos: Vector2
  enableZoom?: boolean
  isHovered?: boolean
}) {
  const { gl } = useThree()
  const [composerReady, setComposerReady] = useState(false)
  const frameCount = useRef(0)

  useFrame(() => {
    frameCount.current++
    // Wait for at least 3 frames before mounting composer
    if (frameCount.current >= 3 && !composerReady) {
      // Use setTimeout to defer to next event loop after frames have rendered
      setTimeout(() => {
        try {
          const context = gl.getContext()
          if (context && !(context as WebGLRenderingContext).isContextLost?.()) {
            setComposerReady(true)
          }
        } catch (e) {
          // Ignore errors
        }
      }, 100)
    }
  })

  return (
    <>
      <color attach="background" args={["#000000"]} />
      <Environment preset="studio" background={false} />
      <ambientLight intensity={0.08} />
      <directionalLight position={[2, 3.5, 6]} intensity={6} />
      <directionalLight position={[-2, 1.5, 4]} intensity={0.35} />
      <CameraHoverZoom isHovered={isHovered} />
      <Suspense fallback={null}>
        <DraggableUserModel isHovered={isHovered} />
      </Suspense>
      <OrbitControls enableRotate={false} enableZoom={enableZoom} enablePan={false} />
      {composerReady && (
        <EffectComposer>
          <AsciiEffect
            style="standard"
            cellSize={9}
            invert={true}
            color={true}
            characterSet="terminal"
            volumeShading={true}
            tintColor="#917AFF"
            resolution={resolution}
            mousePos={mousePos}
            postfx={{
              contrastAdjust: 1.8,
              brightnessAdjust: 0,
            }}
          />
        </EffectComposer>
      )}
    </>
  )
}

interface EffectSceneProps {
  className?: string
  /** Allow zoom with scroll wheel (default true). Set false on hero to block zoom. */
  enableZoom?: boolean
}

export function EffectScene({ className, enableZoom = true }: EffectSceneProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [isHovered, setIsHovered] = useState(false)
  const [mousePos] = useState(() => new Vector2(0, 0))
  const [resolution] = useState(() => new Vector2(1920, 1080))

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const updateResolution = () => {
      const rect = container.getBoundingClientRect()
      resolution.set(rect.width || 1920, rect.height || 1080)
    }

    const handleMouseMove = (e: MouseEvent) => {
      if (container) {
        const rect = container.getBoundingClientRect()
        const x = e.clientX - rect.left
        const y = rect.height - (e.clientY - rect.top)
        mousePos.set(x, y)
      }
    }

    updateResolution()
    const ro = new ResizeObserver(updateResolution)
    ro.observe(container)
    container.addEventListener("mousemove", handleMouseMove)

    return () => {
      ro.disconnect()
      container.removeEventListener("mousemove", handleMouseMove)
    }
  }, [mousePos, resolution])

  return (
    <div
      ref={containerRef}
      data-model-canvas-container
      className={className}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        width: "100%",
        height: className ? "100%" : "100vh",
        minHeight: className ? 300 : undefined,
      }}
    >
      <Canvas
        dpr={Math.min(typeof window !== "undefined" ? window.devicePixelRatio : 1, 1.5)}
        camera={{ position: [0, 0, CAMERA_BASE_Z], fov: 50 }}
        style={{ background: "#000000" }}
        onCreated={({ gl }) => {
          gl.toneMappingExposure = 0.6
          
          const handleContextLost = (event: Event) => {
            event.preventDefault()
            console.warn("WebGL context lost. Attempting to restore...")
          }
          
          const handleContextRestored = () => {
            console.log("WebGL context restored")
          }
          
          gl.domElement.addEventListener("webglcontextlost", handleContextLost)
          gl.domElement.addEventListener("webglcontextrestored", handleContextRestored)
          
          return () => {
            gl.domElement.removeEventListener("webglcontextlost", handleContextLost)
            gl.domElement.removeEventListener("webglcontextrestored", handleContextRestored)
          }
        }}
      >
        <SceneWithDelayedComposer
          resolution={resolution}
          mousePos={mousePos}
          enableZoom={enableZoom}
          isHovered={isHovered}
        />
      </Canvas>
    </div>
  )
}


