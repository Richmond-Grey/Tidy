import { loadFont } from "@remotion/google-fonts/Fredoka";
import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const { fontFamily } = loadFont("normal", {
  weights: ["500", "600"],
  subsets: ["latin"],
});

// Bear theme palette (matches ui/theme.py "bear")
const COLORS = {
  cream: "#FAF5EC",
  honey: "#F4B942",
  honeyDeep: "#D99A2B",
  fur: "#A8693A",
  furShade: "#8A5129",
  innerEar: "#E8B98A",
  muzzle: "#F2DCC0",
  ink: "#2A1D15",
  muted: "#7A6857",
  blush: "#F09A8A",
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** Spring progress (0 → 1) that starts at `delay` seconds. */
const useSpringAt = (delay: number, config = { damping: 12, mass: 0.8 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - delay * fps, fps, config });
};

const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill
      style={{
        // Flat cream = the app's own background, so the intro hands over seamlessly
        // (and the frames compress far better than a full-screen gradient)
        backgroundColor: COLORS.cream,
      }}
    >
      {/* Honey glow that swells behind the bear */}
      <div
        style={{
          position: "absolute",
          left: 360 - 190,
          top: 129 - 190,
          width: 380,
          height: 380,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${COLORS.honey}66 0%, ${COLORS.honey}00 70%)`,
          scale: interpolate(frame, [0, 1.2 * fps], [0.4, 1], {
            ...clamp,
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
          opacity: interpolate(frame, [0, 0.8 * fps], [0, 1], clamp),
        }}
      />
    </AbsoluteFill>
  );
};

const Bear: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const rise = useSpringAt(0.15, { damping: 11, mass: 0.9 });
  const earWiggle =
    Math.sin((frame / fps) * 9) *
    interpolate(frame, [0.5 * fps, 1.4 * fps], [8, 0], clamp);

  // Blink twice: once on arrival, once as a wink-ish double blink near the end
  const blink = (at: number) =>
    interpolate(
      frame,
      [at * fps, (at + 0.06) * fps, (at + 0.14) * fps],
      [1, 0.1, 1],
      clamp,
    );
  const eyeScale = Math.min(blink(1.05), blink(2.35), blink(2.6));
  const happy = interpolate(frame, [1.7 * fps, 2.1 * fps], [0, 1], clamp);
  const headTilt = interpolate(
    frame,
    [1.7 * fps, 2.1 * fps, 2.6 * fps],
    [0, -6, 0],
    {
      ...clamp,
      easing: Easing.bezier(0.45, 0, 0.55, 1),
    },
  );

  const y = interpolate(rise, [0, 1], [190, 0]);
  return (
    <g
      transform={`translate(360 ${170 + y}) rotate(${headTilt}) scale(${0.6 + rise * 0.4})`}
    >
      {/* Ears */}
      <g transform={`rotate(${-earWiggle} -50 -58)`}>
        <circle cx={-50} cy={-58} r={26} fill={COLORS.fur} />
        <circle cx={-50} cy={-58} r={14} fill={COLORS.innerEar} />
      </g>
      <g transform={`rotate(${earWiggle} 50 -58)`}>
        <circle cx={50} cy={-58} r={26} fill={COLORS.fur} />
        <circle cx={50} cy={-58} r={14} fill={COLORS.innerEar} />
      </g>
      {/* Head */}
      <ellipse cx={0} cy={0} rx={78} ry={70} fill={COLORS.fur} />
      <ellipse
        cx={0}
        cy={18}
        rx={70}
        ry={50}
        fill={COLORS.furShade}
        opacity={0.18}
      />
      {/* Muzzle */}
      <ellipse cx={0} cy={26} rx={36} ry={27} fill={COLORS.muzzle} />
      {/* Eyes */}
      {[-28, 28].map((x) => (
        <g key={x} transform={`translate(${x} -8) scale(1 ${eyeScale})`}>
          <circle r={8} fill={COLORS.ink} />
          <circle cx={2.5} cy={-3} r={2.6} fill="#fff" />
        </g>
      ))}
      {/* Cheeks */}
      <ellipse
        cx={-46}
        cy={18}
        rx={11}
        ry={7}
        fill={COLORS.blush}
        opacity={0.25 + happy * 0.45}
      />
      <ellipse
        cx={46}
        cy={18}
        rx={11}
        ry={7}
        fill={COLORS.blush}
        opacity={0.25 + happy * 0.45}
      />
      {/* Nose and smile */}
      <ellipse cx={0} cy={14} rx={12} ry={8.5} fill={COLORS.ink} />
      <ellipse cx={-3} cy={11} rx={3.5} ry={2} fill="#fff" opacity={0.5} />
      <path
        d={`M0 22 L0 30 M0 30 Q-9 ${38 + happy * 4} -17 ${32 - happy * 2} M0 30 Q9 ${38 + happy * 4} 17 ${32 - happy * 2}`}
        stroke={COLORS.ink}
        strokeWidth={3.5}
        strokeLinecap="round"
        fill="none"
      />
    </g>
  );
};

type FileCardProps = {
  label: string;
  color: string;
  from: [number, number];
  to: [number, number];
  delay: number;
  spin: number;
};

const FileCard: React.FC<FileCardProps> = ({
  label,
  color,
  from,
  to,
  delay,
  spin,
}) => {
  const p = useSpringAt(delay, { damping: 15, mass: 0.7 });
  // Fly along an arc rather than a straight line
  const x = interpolate(p, [0, 1], [from[0], to[0]]);
  const y =
    interpolate(p, [0, 1], [from[1], to[1]]) -
    Math.sin(Math.min(p, 1) * Math.PI) * 90;
  const rotation = interpolate(p, [0, 1], [spin, spin * 0.12]);
  return (
    <g
      transform={`translate(${x} ${y}) rotate(${rotation})`}
      opacity={p > 0.001 ? 1 : 0}
    >
      <path
        d="M-23 -29 H11 L23 -17 V29 H-23 Z"
        fill="#FFFDF8"
        stroke="#E2D3BC"
        strokeWidth={2}
      />
      <path
        d="M11 -29 V-17 H23"
        fill="#EFE3D0"
        stroke="#E2D3BC"
        strokeWidth={2}
        strokeLinejoin="round"
      />
      <rect x={-17} y={-2} width={34} height={14} rx={4} fill={color} />
      <text
        x={0}
        y={9}
        textAnchor="middle"
        fontFamily={fontFamily}
        fontWeight={600}
        fontSize={10}
        fill="#fff"
      >
        {label}
      </text>
      <rect x={-15} y={17} width={22} height={3} rx={1.5} fill="#E2D3BC" />
    </g>
  );
};

const Folder: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = useSpringAt(0.35, { damping: 13, mass: 0.8 });
  // Little bounce each time files land
  const bounce =
    interpolate(frame, [1.3 * fps, 1.4 * fps, 1.55 * fps], [0, 5, 0], clamp) +
    interpolate(frame, [1.55 * fps, 1.65 * fps, 1.8 * fps], [0, 4, 0], clamp);
  return (
    <g transform={`translate(360 ${282 + bounce}) scale(${pop})`}>
      <ellipse
        cx={0}
        cy={62}
        rx={118}
        ry={10}
        fill={COLORS.ink}
        opacity={0.08}
      />
      {/* Back panel with tab */}
      <path
        d="M-95 -38 Q-95 -46 -87 -46 H-40 L-30 -36 H87 Q95 -36 95 -28 V48 H-95 Z"
        fill={COLORS.honeyDeep}
      />
      {/* Files go between the panels */}
      <g transform="translate(-360 -282)">{children}</g>
      {/* Front panel */}
      <path
        d="M-102 -16 Q-103 -24 -95 -24 H95 Q103 -24 102 -16 L95 50 Q94 56 87 56 H-87 Q-94 56 -95 50 Z"
        fill={COLORS.honey}
      />
      <rect
        x={-34}
        y={8}
        width={68}
        height={8}
        rx={4}
        fill="#fff"
        opacity={0.45}
      />
      {/* Bear paws gripping the folder */}
      {[-70, 70].map((px) => (
        <g key={px} transform={`translate(${px} -22)`}>
          <ellipse rx={20} ry={14} fill={COLORS.fur} />
          {[-8, 0, 8].map((tx) => (
            <circle key={tx} cx={tx} cy={-5} r={3} fill={COLORS.furShade} />
          ))}
        </g>
      ))}
    </g>
  );
};

const Sparkle: React.FC<{
  x: number;
  y: number;
  delay: number;
  size: number;
}> = ({ x, y, delay, size }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = useSpringAt(delay, { damping: 8, mass: 0.5 });
  const twinkle = 1 + Math.sin((frame / fps) * 6 + x) * 0.08;
  const r = size;
  const star = `M0 ${-r} Q${r * 0.18} ${-r * 0.18} ${r} 0 Q${r * 0.18} ${r * 0.18} 0 ${r} Q${-r * 0.18} ${r * 0.18} ${-r} 0 Q${-r * 0.18} ${-r * 0.18} 0 ${-r} Z`;
  return (
    <path
      d={star}
      fill={COLORS.honey}
      transform={`translate(${x} ${y}) rotate(${interpolate(p, [0, 1], [-60, 0])}) scale(${p * twinkle})`}
    />
  );
};

const Letter: React.FC<{ char: string; delay: number }> = ({ char, delay }) => {
  const p = useSpringAt(delay, { damping: 10, mass: 0.6 });
  return (
    <span
      style={{
        display: "inline-block",
        translate: `0px ${interpolate(p, [0, 1], [40, 0])}px`,
        scale: interpolate(p, [0, 1], [0.6, 1]),
        opacity: interpolate(p, [0, 0.4], [0, 1], clamp),
      }}
    >
      {char}
    </span>
  );
};

export const BearIntro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={{ fontFamily }}>
      <Background />
      <AbsoluteFill>
        <svg viewBox="0 0 720 450" width="100%" height="100%">
          <g transform="translate(0 -36)">
            <Bear />
            <Folder>
              <FileCard
                label="PDF"
                color="#D9534F"
                from={[-60, 80]}
                to={[318, 262]}
                delay={0.6}
                spin={-120}
              />
              <FileCard
                label="JPG"
                color="#4A90C2"
                from={[790, 50]}
                to={[346, 254]}
                delay={0.72}
                spin={140}
              />
              <FileCard
                label="MKV"
                color="#8E6CC9"
                from={[-50, 430]}
                to={[374, 258]}
                delay={0.84}
                spin={-160}
              />
              <FileCard
                label="ZIP"
                color="#4E9A5B"
                from={[780, 420]}
                to={[402, 252]}
                delay={0.96}
                spin={110}
              />
            </Folder>
            <Sparkle x={236} y={92} delay={1.9} size={14} />
            <Sparkle x={488} y={78} delay={2.0} size={18} />
            <Sparkle x={512} y={214} delay={2.1} size={10} />
            <Sparkle x={214} y={228} delay={2.2} size={11} />
          </g>
        </svg>
      </AbsoluteFill>
      <AbsoluteFill
        style={{
          alignItems: "center",
          justifyContent: "flex-end",
          paddingBottom: 30,
        }}
      >
        <div
          style={{
            fontSize: 64,
            fontWeight: 600,
            color: COLORS.ink,
            letterSpacing: 1,
            lineHeight: 1,
          }}
        >
          <Letter char="T" delay={1.7} />
          <Letter char="i" delay={1.78} />
          <Letter char="d" delay={1.86} />
          <Letter char="y" delay={1.94} />
        </div>
        <div
          style={{
            marginTop: 8,
            fontSize: 20,
            fontWeight: 500,
            color: COLORS.muted,
            opacity: interpolate(frame, [2.2 * fps, 2.6 * fps], [0, 1], clamp),
            translate: `0px ${interpolate(
              frame,
              [2.2 * fps, 2.6 * fps],
              [10, 0],
              {
                ...clamp,
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              },
            )}px`,
          }}
        >
          Your files, neatly sorted.
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
