"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useVoiceStore } from "@/shared/voice-store";

const vertexShader = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const fragmentShader = /* glsl */ `
precision highp float;
varying vec2 vUv;
uniform float uTime;
uniform vec2 uResolution;
uniform vec2 uMouse;
uniform float uReactive;

float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  float a = hash(i);
  float b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0));
  float d = hash(i + vec2(1.0, 1.0));
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(a, b, u.x) + (c - a) * u.y * (1.0 - u.x) + (d - b) * u.x * u.y;
}

float fbm(vec2 p) {
  float v = 0.0;
  float a = 0.5;
  for (int i = 0; i < 5; i++) {
    v += a * noise(p);
    p = p * 2.02 + 17.0;
    a *= 0.5;
  }
  return v;
}

void main() {
  vec2 uv = vUv;
  vec2 m = uMouse - 0.5;
  uv += m * 0.045 * (1.0 + uReactive * 0.55);

  float t = uTime * 0.11;
  float aspect = max(uResolution.x / max(uResolution.y, 1.0), 0.0001);
  vec2 p = (uv - 0.5) * vec2(aspect, 1.0) * 1.35;

  float flow = fbm(p + vec2(t * 0.14, t * -0.08));
  float flow2 = fbm(p * 1.55 - vec2(t * 0.11, t * 0.17));
  float field = flow * 0.56 + flow2 * 0.44;

  float pulse = 0.5 + 0.5 * sin(uTime * (0.95 + uReactive * 1.8));
  float bands = smoothstep(0.18, 0.82, sin(field * 8.2 + t * 0.35) * 0.5 + 0.5);

  vec3 base = vec3(0.017, 0.018, 0.022);
  vec3 cool = vec3(0.42, 0.48, 0.58);
  vec3 depth = vec3(0.2, 0.23, 0.3);

  vec3 col = base;
  col = mix(col, depth, field * (0.32 + uReactive * 0.1));
  col += cool * bands * (0.065 + uReactive * 0.1) * pulse;

  vec2 pc = (uv - 0.5) * vec2(aspect, 1.0);
  float radial = length(pc);
  col *= 1.0 - radial * (0.26 - uReactive * 0.05);

  gl_FragColor = vec4(col, 1.0);
}
`;

function useHeroReactive(): number {
  const status = useVoiceStore((s) => s.status);
  const active = useVoiceStore((s) => s.activeSpeaker);
  if (status === "idle") return 0;
  if (status === "error") return 0.08;
  if (status === "connecting") return 0.22;
  if (status === "connected") return 0.38;
  if (status === "speaking") return active === "assistant" ? 0.88 : 0.62;
  return 0;
}

function FieldPlane({ reactive }: { reactive: number }) {
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const reactiveSmooth = useRef(0);
  const mouseSmooth = useRef(new THREE.Vector2(0.5, 0.5));
  const targetMouse = useRef(new THREE.Vector2(0.5, 0.5));
  const { width, height } = useThree((s) => s.viewport);

  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const w = Math.max(window.innerWidth, 1);
      const h = Math.max(window.innerHeight, 1);
      targetMouse.current.set(e.clientX / w, 1 - e.clientY / h);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, []);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uResolution: { value: new THREE.Vector2(1, 1) },
      uMouse: { value: new THREE.Vector2(0.5, 0.5) },
      uReactive: { value: 0 },
    }),
    [],
  );

  useFrame((state, delta) => {
    const mat = materialRef.current;
    if (!mat) return;
    const t = state.clock.elapsedTime;
    mat.uniforms.uTime.value = t;
    const w = Math.max(state.size.width, 1);
    const h = Math.max(state.size.height, 1);
    mat.uniforms.uResolution.value.set(w, h);

    const lambda = 1 - Math.pow(0.002, delta);
    reactiveSmooth.current = THREE.MathUtils.lerp(reactiveSmooth.current, reactive, lambda);
    mat.uniforms.uReactive.value = reactiveSmooth.current;

    const tx = targetMouse.current.x;
    const ty = targetMouse.current.y;
    mouseSmooth.current.x = THREE.MathUtils.lerp(mouseSmooth.current.x, tx, 1 - Math.pow(0.02, delta));
    mouseSmooth.current.y = THREE.MathUtils.lerp(mouseSmooth.current.y, ty, 1 - Math.pow(0.02, delta));
    mat.uniforms.uMouse.value.copy(mouseSmooth.current);
  });

  return (
    <mesh scale={[width, height, 1]} position={[0, 0, 0]}>
      <planeGeometry args={[1, 1]} />
      <shaderMaterial
        ref={materialRef}
        uniforms={uniforms}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        depthTest={false}
        depthWrite={false}
      />
    </mesh>
  );
}

function Scene({ reactive }: { reactive: number }) {
  return <FieldPlane reactive={reactive} />;
}

export function CinematicHero() {
  const reactive = useHeroReactive();

  return (
    <Canvas
      className="h-full w-full touch-none"
      dpr={[1, 2]}
      gl={{
        antialias: true,
        alpha: false,
        powerPreference: "high-performance",
      }}
      camera={{ position: [0, 0, 5], fov: 35, near: 0.1, far: 20 }}
      style={{ background: "#09090b" }}
    >
      <Scene reactive={reactive} />
    </Canvas>
  );
}
