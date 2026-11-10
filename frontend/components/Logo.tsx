export default function Logo({ size = 44 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" role="img" aria-label="Empório da Música">
      <defs>
        <linearGradient id="logo-ring" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FC0065" />
          <stop offset="0.55" stopColor="#8B3DFF" />
          <stop offset="1" stopColor="#22D3EE" />
        </linearGradient>
      </defs>
      <circle cx="24" cy="24" r="22" fill="#0D1634" stroke="url(#logo-ring)" strokeWidth="3" />
      <circle cx="24" cy="24" r="14" fill="none" stroke="#FFFFFF" strokeOpacity="0.12" strokeWidth="1" />
      <circle cx="24" cy="24" r="8" fill="none" stroke="#FFFFFF" strokeOpacity="0.12" strokeWidth="1" />
      <g fill="none" stroke="#FFFFFF" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 31V16l10-2v15" />
        <circle cx="17.5" cy="31" r="2.6" fill="#FC0065" stroke="none" />
        <circle cx="27.5" cy="29" r="2.6" fill="#22D3EE" stroke="none" />
      </g>
    </svg>
  );
}
