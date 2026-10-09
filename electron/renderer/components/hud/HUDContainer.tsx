import React, { HTMLAttributes, ReactNode } from 'react';

interface HUDContainerProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export const HUDContainer: React.FC<HUDContainerProps> = ({ children, className = '', ...props }) => {
  return (
    <div
      className={`relative w-full h-screen overflow-hidden bg-bg-primary text-text-primary ${className}`}
      {...props}
    >
      {/* Background Layers */}
      
      {/* 1. Deep Space Base Gradient */}
      <div
        className="absolute inset-0 z-0"
        style={{
          background: 'radial-gradient(circle at center, rgb(var(--color-bg-secondary) / 1) 0%, rgb(var(--color-bg-primary) / 1) 100%)',
        }}
      />
      
      {/* 2. Stars / Nebula subtle effect (CSS generated) */}
      <div
        className="absolute inset-0 z-0 mix-blend-screen pointer-events-none"
        style={{
          opacity: 'var(--theme-stars-opacity, 0.3)',
          backgroundImage: 'radial-gradient(circle at 25% 30%, rgb(255 255 255 / 0.3) 0.5px, transparent 1px), radial-gradient(circle at 70% 75%, rgb(255 255 255 / 0.2) 0.5px, transparent 1px)',
          backgroundSize: '113px 137px, 179px 193px',
        }}
      />
      
      {/* 3. Grid Overlay (The "Floor" or tactical map feel) */}
      <div
        className="absolute inset-0 bg-grid-pattern bg-grid [mask-image:linear-gradient(to_bottom,transparent,black)] z-0 pointer-events-none"
        style={{ opacity: 'var(--theme-grid-opacity, 0.2)' }}
      />

      {/* 4. Vignette for focus */}
      <div
        className="absolute inset-0 z-10 pointer-events-none"
        style={{
          background: 'radial-gradient(circle at center, transparent 50%, rgb(0 0 0 / var(--theme-vignette-alpha, 0.8)) 100%)',
        }}
      />

      {/* Scanlines are applied once by body::after, including over portals. */}

      {/* Decorative Corner HUD Elements (Fixed to screen) */}
      <div className="hud-corner absolute top-4 left-4 w-32 h-32 border-l border-t border-border-glow opacity-50 z-20 pointer-events-none hud-corner-top" />
      <div className="hud-corner absolute top-4 right-4 w-32 h-32 border-r border-t border-border-glow opacity-50 z-20 pointer-events-none hud-corner-top" />
      <div className="hud-corner absolute bottom-4 left-4 w-32 h-32 border-l border-b border-border-glow opacity-50 z-20 pointer-events-none" />
      <div className="hud-corner absolute bottom-4 right-4 w-32 h-32 border-r border-b border-border-glow opacity-50 z-20 pointer-events-none" />

      {/* Content Layer */}
      <div className="relative z-30 h-full w-full overflow-hidden flex flex-col">
        {children}
      </div>
    </div>
  );
};
