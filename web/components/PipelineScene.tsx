"use client";
// One 3D scene, used well: a tunnel of four rings (INGEST → MINE → LABEL → NORMALIZE) with instanced
// particles flowing through. cyan = parsed, amber = quarantined, rose = injection flagged, violet = foundry.
import { Canvas, useFrame } from "@react-three/fiber";
import { Bloom, ChromaticAberration, EffectComposer } from "@react-three/postprocessing";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

export type SceneMix = { eps: number; bad: number; inj: number; foundry: boolean };

const MAX = 2600;
const SPAWN_Z = 3; // spawn inside the tunnel, well in front of the camera (z = 11)
const CA_OFFSET = new THREE.Vector2(0.0006, 0.0006);
const RING_Z = [4, -4, -12, -20];
const COLORS = {
  ok: new THREE.Color("#22D3EE"),
  bad: new THREE.Color("#FBBF24"),
  inj: new THREE.Color("#FB7185"),
  fdy: new THREE.Color("#8B5CF6"),
};

function Particles({ mix }: { mix: React.MutableRefObject<SceneMix> }) {
  const mesh = useRef<THREE.InstancedMesh>(null!);
  const data = useMemo(() => {
    const a = new Float32Array(MAX * 4); // z, angle, radius, speed
    for (let i = 0; i < MAX; i++) {
      a[i * 4] = SPAWN_Z - Math.random() * 33;
      a[i * 4 + 1] = Math.random() * Math.PI * 2;
      a[i * 4 + 2] = 0.3 + Math.random() * 2.1;
      a[i * 4 + 3] = 0.6 + Math.random() * 0.8;
    }
    return a;
  }, []);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const active = useRef(MAX);
  const fps = useRef<number[]>([]);

  const pick = () => {
    const m = mix.current;
    const r = Math.random();
    if (r < m.inj) return COLORS.inj;
    if (r < m.inj + m.bad) return COLORS.bad;
    if (m.foundry && r < m.inj + m.bad + 0.12) return COLORS.fdy;
    return COLORS.ok;
  };

  useEffect(() => {
    for (let i = 0; i < MAX; i++) mesh.current.setColorAt(i, COLORS.ok);
  }, []);

  useFrame((_, dt) => {
    // adapt particle count to frame rate (drop to 1/3 under 45 fps)
    const f = fps.current;
    f.push(1 / Math.max(dt, 1e-3));
    if (f.length > 60) {
      const avg = f.reduce((a, b) => a + b, 0) / f.length;
      active.current = avg < 45 ? Math.max(800, Math.floor(active.current * 0.8)) : Math.min(MAX, active.current + 50);
      f.length = 0;
    }
    const m = mix.current;
    const speed = 4 + Math.min(26, Math.log10(1 + m.eps) * 7);
    for (let i = 0; i < MAX; i++) {
      const k = i * 4;
      let z = data[k] - dt * speed * data[k + 3];
      let ang = data[k + 1] + dt * 0.15;
      if (z < -30) {
        z = SPAWN_Z;
        ang = Math.random() * Math.PI * 2;
        mesh.current.setColorAt(i, pick());
      }
      data[k] = z;
      data[k + 1] = ang;
      // funnel: particles converge towards the axis after NORMALIZE (one schema)
      const squeeze = z < -20 ? Math.max(0.15, 1 + (z + 20) / 12) : 1;
      const r = data[k + 2] * squeeze;
      dummy.position.set(Math.cos(ang) * r, Math.sin(ang) * r, z);
      const s = i < active.current ? 0.022 + (data[k + 3] - 0.6) * 0.02 : 0;
      dummy.scale.setScalar(s);
      dummy.updateMatrix();
      mesh.current.setMatrixAt(i, dummy.matrix);
    }
    mesh.current.instanceMatrix.needsUpdate = true;
    if (mesh.current.instanceColor) mesh.current.instanceColor.needsUpdate = true;
  });

  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, MAX]} frustumCulled={false}>
      <sphereGeometry args={[1, 8, 8]} />
      <meshBasicMaterial toneMapped={false} />
    </instancedMesh>
  );
}

function Rings() {
  const group = useRef<THREE.Group>(null!);
  useFrame(({ clock }) => {
    group.current.children.forEach((c, i) => {
      c.rotation.z = clock.elapsedTime * (0.08 + i * 0.03) * (i % 2 ? -1 : 1);
    });
  });
  const tints = ["#22D3EE", "#60A5FA", "#8B5CF6", "#34D399"];
  return (
    <group ref={group}>
      {RING_Z.map((z, i) => (
        <mesh key={z} position={[0, 0, z]}>
          <torusGeometry args={[2.9, 0.045, 16, 160]} />
          <meshStandardMaterial color={tints[i]} emissive={tints[i]} emissiveIntensity={2.2} toneMapped={false}
            transparent opacity={0.9} />
        </mesh>
      ))}
      {RING_Z.map((z, i) => (
        <mesh key={`g${z}`} position={[0, 0, z]}>
          <ringGeometry args={[2.3, 2.85, 96]} />
          <meshPhysicalMaterial color="#9fb4ff" transparent opacity={0.05} roughness={0.1} metalness={0.2}
            side={THREE.DoubleSide} />
        </mesh>
      ))}
    </group>
  );
}

function CameraRig() {
  const target = useRef({ x: 0, y: 0 });
  useEffect(() => {
    const on = (e: PointerEvent) => {
      target.current.x = (e.clientX / window.innerWidth - 0.5) * 1.4;
      target.current.y = (e.clientY / window.innerHeight - 0.5) * 0.9;
    };
    window.addEventListener("pointermove", on);
    return () => window.removeEventListener("pointermove", on);
  }, []);
  useFrame(({ camera, clock }) => {
    const t = clock.elapsedTime * 0.12;
    camera.position.x += (Math.sin(t) * 1.6 + target.current.x - camera.position.x) * 0.03;
    camera.position.y += (Math.cos(t * 0.8) * 0.8 - target.current.y - camera.position.y) * 0.03;
    camera.lookAt(1.2, 0, -14);
  });
  return null;
}

export default function PipelineScene({ mix }: { mix: SceneMix }) {
  const ref = useRef(mix);
  ref.current = mix;
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const on = () => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", on);
    return () => document.removeEventListener("visibilitychange", on);
  }, []);
  return (
    <Canvas frameloop={visible ? "always" : "never"} dpr={[1, 1.75]} camera={{ position: [0, 0, 11], fov: 55 }}
      gl={{ antialias: true, powerPreference: "high-performance" }}>
      <color attach="background" args={["#05070d"]} />
      <fog attach="fog" args={["#05070d", 14, 40]} />
      <ambientLight intensity={0.4} />
      {/* tunnel sits right of centre so the hero copy on the left stays readable */}
      <group position={[3.4, 0, 0]}>
        <Rings />
        <Particles mix={ref} />
      </group>
      <CameraRig />
      <EffectComposer>
        <Bloom intensity={0.8} luminanceThreshold={0.15} luminanceSmoothing={0.3} mipmapBlur />
        <ChromaticAberration offset={CA_OFFSET} />
      </EffectComposer>
    </Canvas>
  );
}
