"use client";

import { useEffect, useRef } from "react";
import { Mesh, Program, Renderer, Triangle } from "ogl";

type ThreadsProps = {
  color?: [number, number, number];
  amplitude?: number;
  distance?: number;
  flow?: number;
  pulse?: number;
  complexity?: number;
  orbOrigin?: [number, number];
  orbInfluence?: number;
  orbWarp?: number;
  orbRadius?: number;
  className?: string;
};

const vertexShader = /* glsl */ `
attribute vec2 position;
attribute vec2 uv;
varying vec2 vUv;

void main() {
  vUv = uv;
  gl_Position = vec4(position, 0.0, 1.0);
}
`;

const fragmentShader = /* glsl */ `
precision highp float;

uniform float iTime;
uniform vec3 iResolution;
uniform vec3 uColor;
uniform float uAmplitude;
uniform float uDistance;
uniform float uFlow;
uniform float uPulse;
uniform float uComplexity;
uniform vec2 uOrbOrigin;
uniform float uOrbInfluence;
uniform float uOrbWarp;
uniform float uOrbRadius;
uniform vec2 uMouse;

#define PI 3.1415926538

const int u_line_count = 40;
const float u_line_width = 7.0;
const float u_line_blur = 10.0;

float Perlin2D(vec2 P) {
  vec2 Pi = floor(P);
  vec4 Pf_Pfmin1 = P.xyxy - vec4(Pi, Pi + 1.0);
  vec4 Pt = vec4(Pi.xy, Pi.xy + 1.0);
  Pt = Pt - floor(Pt * (1.0 / 71.0)) * 71.0;
  Pt += vec2(26.0, 161.0).xyxy;
  Pt *= Pt;
  Pt = Pt.xzxz * Pt.yyww;
  vec4 hash_x = fract(Pt * (1.0 / 951.135664));
  vec4 hash_y = fract(Pt * (1.0 / 642.949883));
  vec4 grad_x = hash_x - 0.49999;
  vec4 grad_y = hash_y - 0.49999;
  vec4 grad_results = inversesqrt(grad_x * grad_x + grad_y * grad_y)
    * (grad_x * Pf_Pfmin1.xzxz + grad_y * Pf_Pfmin1.yyww);
  grad_results *= 1.4142135623730950;
  vec2 blend = Pf_Pfmin1.xy * Pf_Pfmin1.xy * Pf_Pfmin1.xy
             * (Pf_Pfmin1.xy * (Pf_Pfmin1.xy * 6.0 - 15.0) + 10.0);
  vec4 blend2 = vec4(blend, vec2(1.0 - blend));
  return dot(grad_results, blend2.zxzx * blend2.wwyy);
}

float pixel(float count, vec2 resolution) {
  return (1.0 / max(resolution.x, resolution.y)) * count;
}

float lineFn(vec2 st, float width, float perc, vec2 mouse, float time, float amplitude, float distance) {
  float amplitude_strength = mix(0.35, 0.8, perc);
  float finalAmplitude = amplitude_strength * amplitude * (1.0 + (mouse.y - 0.5) * 0.16);

  float time_scaled = (time / 10.0) * uFlow + (mouse.x - 0.5) * 0.45;
  float blur = mix(0.15, 1.0, perc);

  float xnoise = mix(
      Perlin2D(vec2(time_scaled, st.x + perc) * 2.5),
      Perlin2D(vec2(time_scaled * (1.1 + perc * 0.8), st.x * (2.3 + perc * 2.2))) / 1.25,
      0.45 + 0.3 * sin(time_scaled * 0.5 + perc * PI)
  );

  float crossing = sin(st.x * (7.0 + perc * 6.0) + time_scaled * (0.35 + perc * 0.35) + perc * PI);
  float y = 0.5 + (perc - 0.5) * distance + xnoise / 2.0 * finalAmplitude + crossing * 0.02 * uComplexity;

  // Localized space distortion around the orb: nearby threads bend toward/around it.
  vec2 toOrb = st - uOrbOrigin;
  float ellipseDistance = length(vec2(toOrb.x, toOrb.y * 1.25));
  float localizedInfluence = exp(-pow(ellipseDistance / max(uOrbRadius, 0.001), 2.0)) * uOrbWarp;
  float orbitalWave = sin(time_scaled * 0.42 + perc * PI * 2.0) * 0.012;
  y += (-toOrb.y * 0.18 + orbitalWave) * localizedInfluence;

  float line_start = smoothstep(
    y + (width / 2.0) + (u_line_blur * pixel(1.0, iResolution.xy) * blur),
    y,
    st.y
  );

  float line_end = smoothstep(
    y,
    y - (width / 2.0) - (u_line_blur * pixel(1.0, iResolution.xy) * blur),
    st.y
  );

  float localDensityBoost = 1.0 + localizedInfluence * 0.4;
  return clamp(
    (line_start - line_end) * (1.0 - smoothstep(0.0, 1.0, pow(perc, 0.3))) * localDensityBoost,
    0.0,
    1.0
  );
}

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
  vec2 uv = fragCoord / iResolution.xy;
  vec2 uvCentered = uv - 0.5;

  float line_strength = 1.0;
  for (int i = 0; i < u_line_count; i++) {
    float p = float(i) / float(u_line_count);
    line_strength *= (1.0 - lineFn(
      uv,
      u_line_width * pixel(1.0, iResolution.xy) * (1.0 - p),
      p,
      uMouse,
      iTime,
      uAmplitude,
      uDistance
    ));
  }

  float colorVal = 1.0 - line_strength;
  float orbDistance = distance(uv, uOrbOrigin);
  float orbGlow = smoothstep(0.6, 0.03, orbDistance) * uOrbInfluence;
  float vignette = smoothstep(1.05, 0.1, length(vec2(uvCentered.x, uvCentered.y * 1.25)));
  float boosted = clamp(colorVal * (1.25 + uPulse * 0.9), 0.0, 1.0);
  vec3 tint = uColor * (0.9 + boosted * 0.85);
  tint += uColor * orbGlow * 0.7;

  float alpha = clamp(boosted * (0.88 + orbGlow * 0.5), 0.0, 1.0);
  alpha *= mix(0.72, 1.0, vignette);
  fragColor = vec4(tint * boosted, alpha);
}

void main() {
  mainImage(gl_FragColor, gl_FragCoord.xy);
}
`;

export default function Threads({
  color = [0.91, 0.78, 0.62],
  amplitude = 2.5,
  distance = 0.7,
  flow = 1,
  pulse = 0.08,
  complexity = 1,
  orbOrigin = [0.5, 0.35],
  orbInfluence = 0.25,
  orbWarp = 0.14,
  orbRadius = 0.22,
  className = "",
}: ThreadsProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const animationFrameIdRef = useRef<number | null>(null);
  const colorRef = useRef<[number, number, number]>([color[0] ?? 0.91, color[1] ?? 0.78, color[2] ?? 0.62]);
  const amplitudeRef = useRef(amplitude);
  const distanceRef = useRef(distance);
  const flowRef = useRef(flow);
  const pulseRef = useRef(pulse);
  const complexityRef = useRef(complexity);
  const orbOriginRef = useRef<[number, number]>([orbOrigin[0] ?? 0.5, orbOrigin[1] ?? 0.35]);
  const orbInfluenceRef = useRef(orbInfluence);
  const orbWarpRef = useRef(orbWarp);
  const orbRadiusRef = useRef(orbRadius);

  useEffect(() => {
    colorRef.current = [color[0] ?? 0.91, color[1] ?? 0.78, color[2] ?? 0.62];
    amplitudeRef.current = amplitude;
    distanceRef.current = distance;
    flowRef.current = flow;
    pulseRef.current = pulse;
    complexityRef.current = complexity;
    orbOriginRef.current = [orbOrigin[0] ?? 0.5, orbOrigin[1] ?? 0.35];
    orbInfluenceRef.current = orbInfluence;
    orbWarpRef.current = orbWarp;
    orbRadiusRef.current = orbRadius;
  }, [color, amplitude, distance, flow, pulse, complexity, orbOrigin, orbInfluence, orbWarp, orbRadius]);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const renderer = new Renderer({
      alpha: true,
      antialias: false,
      dpr: Math.min(window.devicePixelRatio || 1, 1.5),
    });
    const gl = renderer.gl;
    gl.clearColor(0, 0, 0, 0);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    const canvas = gl.canvas as HTMLCanvasElement;
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    canvas.style.display = "block";
    root.appendChild(canvas);

    const geometry = new Triangle(gl);
    const uniforms = {
      iTime: { value: 0 },
      iResolution: { value: new Float32Array([1, 1, 1]) },
      uColor: { value: new Float32Array(colorRef.current) },
      uAmplitude: { value: amplitudeRef.current },
      uDistance: { value: distanceRef.current },
      uFlow: { value: flowRef.current },
      uPulse: { value: pulseRef.current },
      uComplexity: { value: complexityRef.current },
      uOrbOrigin: { value: new Float32Array(orbOriginRef.current) },
      uOrbInfluence: { value: orbInfluenceRef.current },
      uOrbWarp: { value: orbWarpRef.current },
      uOrbRadius: { value: orbRadiusRef.current },
      uMouse: { value: new Float32Array([0.5, 0.5]) },
    };

    const program = new Program(gl, {
      vertex: vertexShader,
      fragment: fragmentShader,
      uniforms,
    });
    const mesh = new Mesh(gl, { geometry, program });

    const resize = () => {
      const width = root.clientWidth || 1;
      const height = root.clientHeight || 1;
      renderer.setSize(width, height);
      uniforms.iResolution.value[0] = width;
      uniforms.iResolution.value[1] = height;
      uniforms.iResolution.value[2] = width / Math.max(height, 1);
    };

    const ro = new ResizeObserver(resize);
    ro.observe(root);
    resize();

    const loop = (time: number) => {
      uniforms.uMouse.value[0] = 0.5;
      uniforms.uMouse.value[1] = 0.5;
      uniforms.uColor.value[0] += (colorRef.current[0] - uniforms.uColor.value[0]) * 0.035;
      uniforms.uColor.value[1] += (colorRef.current[1] - uniforms.uColor.value[1]) * 0.035;
      uniforms.uColor.value[2] += (colorRef.current[2] - uniforms.uColor.value[2]) * 0.035;
      uniforms.uAmplitude.value += (amplitudeRef.current - uniforms.uAmplitude.value) * 0.022;
      uniforms.uDistance.value += (distanceRef.current - uniforms.uDistance.value) * 0.022;
      uniforms.uFlow.value += (flowRef.current - uniforms.uFlow.value) * 0.022;
      uniforms.uPulse.value += (pulseRef.current - uniforms.uPulse.value) * 0.024;
      uniforms.uComplexity.value += (complexityRef.current - uniforms.uComplexity.value) * 0.022;
      uniforms.uOrbOrigin.value[0] += (orbOriginRef.current[0] - uniforms.uOrbOrigin.value[0]) * 0.018;
      uniforms.uOrbOrigin.value[1] += (orbOriginRef.current[1] - uniforms.uOrbOrigin.value[1]) * 0.018;
      uniforms.uOrbInfluence.value += (orbInfluenceRef.current - uniforms.uOrbInfluence.value) * 0.022;
      uniforms.uOrbWarp.value += (orbWarpRef.current - uniforms.uOrbWarp.value) * 0.022;
      uniforms.uOrbRadius.value += (orbRadiusRef.current - uniforms.uOrbRadius.value) * 0.022;
      uniforms.iTime.value = time * 0.001;
      renderer.render({ scene: mesh });
      animationFrameIdRef.current = window.requestAnimationFrame(loop);
    };

    const suspendLoop = () => {
      if (animationFrameIdRef.current !== null) {
        window.cancelAnimationFrame(animationFrameIdRef.current);
        animationFrameIdRef.current = null;
      }
    };

    const resumeLoop = () => {
      if (animationFrameIdRef.current === null) {
        animationFrameIdRef.current = window.requestAnimationFrame(loop);
      }
    };

    const syncVisibilityLoop = () => {
      if (document.visibilityState === "hidden") {
        suspendLoop();
      } else {
        resumeLoop();
      }
    };

    document.addEventListener("visibilitychange", syncVisibilityLoop);
    resumeLoop();

    return () => {
      document.removeEventListener("visibilitychange", syncVisibilityLoop);
      suspendLoop();
      ro.disconnect();
      mesh.setParent(null);
      geometry.remove();
      program.remove();
      gl.getExtension("WEBGL_lose_context")?.loseContext();
      canvas.remove();
    };
  }, []);

  return <div ref={rootRef} className={className} aria-hidden />;
}

