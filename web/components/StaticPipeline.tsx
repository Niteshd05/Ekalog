"use client";
// CSS-only stand-in for the 3D hero (no WebGL, reduced motion, or while three.js loads).
/** Static fallback for low-end machines / reduced motion / no WebGL. */
export function StaticPipeline() {
  return (
    <div className="absolute inset-0 overflow-hidden bg-[radial-gradient(ellipse_at_center,#0c1633,#05070d_70%)]">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="absolute left-1/2 top-1/2 rounded-full border-2"
          style={{
            width: `${340 - i * 70}px`, height: `${340 - i * 70}px`, transform: "translate(-50%,-50%)",
            borderColor: ["#22D3EE", "#60A5FA", "#8B5CF6", "#34D399"][i], opacity: 0.35 + i * 0.12,
            boxShadow: `0 0 30px ${["#22D3EE", "#60A5FA", "#8B5CF6", "#34D399"][i]}55`,
          }} />
      ))}
    </div>
  );
}
