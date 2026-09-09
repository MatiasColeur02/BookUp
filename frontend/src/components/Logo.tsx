type LogoProps = { className?: string };

/** Símbolo del libro abierto: dos "páginas" giradas + lomo, según el handoff de diseño. */
export function Logo({ className }: LogoProps) {
  return (
    <span className={`logo-mark${className ? ` ${className}` : ""}`}>
      <span className="logo-page logo-page-left" />
      <span className="logo-page logo-page-right" />
      <span className="logo-spine" />
    </span>
  );
}
