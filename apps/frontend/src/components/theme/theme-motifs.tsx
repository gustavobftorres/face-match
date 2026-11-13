export function DaisyMark({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      {[0, 45, 90, 135, 180, 225, 270, 315].map((angle) => (
        <ellipse
          key={angle}
          cx="32"
          cy="14"
          rx="6.2"
          ry="11"
          fill="#FFFDF8"
          stroke="#211E1D"
          strokeWidth="2"
          transform={`rotate(${angle} 32 32)`}
        />
      ))}
      <circle cx="32" cy="32" r="9.5" fill="#F7B519" stroke="#211E1D" strokeWidth="2" />
    </svg>
  );
}

export function SquiggleUnderline({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 260 18"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <path
        d="M3 12C45 4 86 15 130 9C174 3 216 14 257 7"
        stroke="#F7B519"
        strokeWidth="6"
        strokeLinecap="round"
      />
      <path
        d="M8 12C50 5 90 15 132 9C175 4 214 14 253 8"
        stroke="#E6511A"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function WaveHorizon({ className = "" }: { className?: string }) {
  return (
    <div className={`relative w-full overflow-hidden select-none pointer-events-none ${className}`}>
      <svg
        viewBox="0 0 1440 130"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-14 sm:h-20 md:h-24 block"
        preserveAspectRatio="none"
      >
        <path
          d="M0 72C210 24 410 112 680 62C950 12 1170 88 1440 42V130H0V72Z"
          fill="#F7B519"
        />
        <path
          d="M0 88C240 44 470 118 760 72C1040 28 1220 96 1440 58V130H0V88Z"
          fill="#F383AA"
        />
        <path
          d="M0 100C280 64 520 122 830 84C1110 50 1280 106 1440 74V130H0V100Z"
          fill="#BA78D3"
        />
        <path
          d="M0 112C320 84 590 126 910 96C1180 72 1320 116 1440 92V130H0V112Z"
          fill="#E6511A"
        />
        <path
          d="M0 121C380 104 680 130 1020 112C1250 100 1360 122 1440 108V130H0V121Z"
          fill="#6D238E"
        />
      </svg>
    </div>
  );
}
